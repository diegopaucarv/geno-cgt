# Workflow tests

End-to-end and contract tests for the per-document pipeline:

```
crudo ──Preprocesar──▶ preprocesado ──Clasificar──▶ clasificado
      ──Segmentar──▶ segmentado ──Extraer incidentes──▶ incidentes_extraidos
```

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
python -m pytest tests/workflow -v                 # fast contract/static tests
python -m pytest tests/workflow -v --run-slow      # + LLM-backed E2E
python -m pytest tests/workflow -v --run-slow -m slow
```

Overrides:

```bash
python -m pytest tests/workflow \
  --base-url http://localhost:3000 \
  --project-id 5ab006b2-62fe-4e10-b45a-8f6fdb8c216f
```

`--base-url`, `--project-id`, and `GENO_USER_ID` can also be set through the
environment (`GENO_BASE_URL`, `GENO_PROJECT_ID`, `GENO_USER_ID`).

## What each file proves

| File | Scope | Needs stack |
| --- | --- | --- |
| `test_api_documents.py` | Route contracts for `documents.py`: auth, 404/400, `{status, task_id}` shape | yes |
| `test_api_pipeline.py` | `pipeline/run-agent`, `run-stage`, status/log contracts | yes |
| `test_workers_tasks.py` | Static contracts on `workers/*/tasks.py` (task names, re-raise, return shapes) | no |
| `test_e2e_workflow.py` | Real `crudo → preprocesado → clasificado` transitions on an ephemeral project | yes, `--run-slow` |
| `test_frontend_i18n.py` | Every `t("project.X")` in `Project.tsx` exists in all four locales | no |

## Design notes

- Mutating tests use an **ephemeral project** (`temp_project` fixture) that is
  deleted afterwards. The seeded project is only read.
- Coverage of the actual bug that made the UI look stale
  (`changes_made:false` but `estado` advancing) lives in
  `test_e2e_workflow.py::test_punctuate_advances_estado_even_without_changes`.
- `punctuate` and `classify-glaser` are **async**: they return
  `{"status": "dispatched", "task_id": ...}` and the caller must poll
  `GET /api/v1/documents/tasks/{task_id}`.
- `estado` is a free-form varchar. Always `.strip()` before comparing; the
  allowed values include `crudo, preprocesando, preprocesado, clasificando,
  clasificado, segmentando, segmentado, procesando, incidentes_extraidos,
  procesado, listo, codificado, error`.
