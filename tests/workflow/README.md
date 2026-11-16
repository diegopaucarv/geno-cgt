# Workflow tests

End-to-end and contract tests for the per-document pipeline:

```
crudo ──Preprocesar──▶ preprocesado ──Clasificar──▶ clasificado
      ──Segmentar (hereda el tag de cada tramo)──▶ segmentado
      ──Extraer incidentes──▶ incidentes_extraidos
```

Clasificar va **antes** de segmentar (classify-first): el clasificador etiqueta
el texto completo sin crear segmentos, y `segmentar_documento` los crea
aplicando a cada uno el `tipo_dato_glaser` de su tramo de origen.

These tests run **from the host** against a live `docker compose` stack. The
containers do not ship pytest, and the frontend reaches the API through the
rsbuild proxy, so host-run HTTP tests exercise exactly the surface the UI uses.

## Prerequisites

```bash
docker compose up -d
# frontend: http://localhost:3000  (proxy -> fastapi)
```

The fixtures mint a JWT with `app.core.security.create_access_token` inside the
`fastapi` container, so no credentials are stored in the repo.

## Run

```bash
python -m pytest tests/workflow -v                # fast, no LLM calls
python -m pytest tests/workflow -v --run-slow     # includes E2E pipeline
python -m pytest tests/workflow -v --run-slow -m slow
```

Useful overrides:

```bash
python -m pytest tests/workflow -v --base-url http://localhost:3000
python -m pytest tests/workflow -v --project-id <uuid>
```

`GENO_BASE_URL`, `GENO_PROJECT_ID`, and `GENO_USER_ID` are also honoured.

The suite is intentionally read-mostly. The E2E test creates its own project
and uploads its own document, then deletes both, so it does not touch the
project you are manually testing.

## What each file proves

| File                         | Scope                                                                                      | Needs stack       |
| ---------------------------- | ------------------------------------------------------------------------------------------ | ----------------- |
| `test_api_documents.py`      | Route contracts for `documents.py`: auth, 404/400, `{status, task_id}` shape               | yes               |
| `test_api_pipeline.py`       | `pipeline/run-agent`, `run-stage`, status/log contracts                                    | yes               |
| `test_workers_tasks.py`      | Static contracts on `workers/*/tasks.py` (task names, re-raise, return shapes)             | no                |
| `test_e2e_workflow.py`       | Real `crudo → preprocesado → segmentado → clasificado` transitions on an ephemeral project | yes, `--run-slow` |
| `test_frontend_i18n.py`      | Every `t("project.X")` in `Project.tsx` exists in all four locales                         | no                |
| `test_segment_classifier.py` | Segment-first classifier units: contiguity merge, per-batch ordinals, degraded fallback    | no                |

## Design notes

- Mutating tests use an **ephemeral project** (`temp_project` fixture) that is
  deleted afterwards. The seeded project is only read.
- Coverage of the actual bug that made the UI look stale
  (`changes_made:false` but `estado` advancing) lives in
  `test_e2e_workflow.py::test_punctuate_advances_estado_even_without_changes`.
- `punctuate` and `classify-glaser` are **async**: they return
  `{"status": "dispatched", "task_id": ...}` and the caller must poll
  `GET /api/v1/documents/tasks/{task_id}`.
- `estado` is a free-form varchar. Always `.strip()` before comparing. Path: `crudo` → `preprocesando` → `preprocesado` → `clasificando` → `clasificado` → `segmentando` → `segmentado` → `procesando` → `extrayendo` → `incidentes_extraidos`, plus the legacy `procesado`, `listo`, `codificado` and the terminal `error`.
- `test_segment_classifier.py` loads `workers/heavy/segment_classifier.py`
  straight from the source tree (stdlib + SQLAlchemy only), so it runs in the
  fast pass without a docker stack.
- Classify-first: `crudo`/`preprocesado` → `clasificando` → `clasificado` → `segmentando` → `segmentado`; `segmentar_documento` inherits `tipo_dato_glaser` from `metadatos.glaser_blocks` via `backend/app/services/glaser_inheritance.py`, and an unmatched segment stays `NULL` (never `baseline_data`).
- Legacy Glaser labels (`processual_data`, `contextual_data`) are still normalised deterministically to the canonical taxonomy by `normalizar_etiquetas_legacy` (unit-tested in `test_segment_classifier.py`); incident extraction reads `baseline_data` only.
