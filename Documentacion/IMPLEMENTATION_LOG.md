# Registro de Implementación — Pipeline CGT + RAG

> Finalizado: 2026-06-16. Arquitectura dual-path (Celery default + Graph opt-in).
> **32 completados | 0 pendientes | 1 experimental (graph)**

---

## ✅ COMPLETADO (32 ítems)

### Infraestructura base

| # | Ítem | Archivo |
|---|---|---|
| 1-3 | Columnas (estado, tipo_dato_glaser, config_segmentacion) | `document.py`, `segment.py`, `project.py` |
| 4 | HITL API (5 endpoints) | `api/v1/hypotheses.py` |
| 5 | Bi-encoder Cache (Redis) | `core/bi_encoder_cache.py` |
| 6 | GraphRAG extraction (3 tareas) | `workers/fast/tasks.py` |
| 7 | SaturationCalculator (centroide móvil) | `workers/nlp/saturation.py` |
| 8 | Upload → pipeline A1→A2→A3 | `documents.py`, `tasks.py` |
| 9 | B2.5 grounding | `agents_b.py` |

### Formato de prompts

| # | Ítem | Archivo |
|---|---|---|
| B4-B6 | Formato unificado `.md` YAML + parser dual + `AGENT_FILES` | `llm_client.py` |
| B7 | B2 Critic (SAT/MOD/FORCED) | `deepseek_pro/b2_critic.md` |
| B8 | Map Synthesis (intra-doc) | `deepseek_pro/map_synthesis.md` |
| B9 | Reduce Synthesis (inter-doc) | `deepseek_pro/reduce_synthesis.md` |
| B10 | Incident Extractor PRO | `deepseek_pro/incident_extractor.md` |
| B11 | Clusterizador A04 (6 pasos) | `deepseek_pro/clusterizador_informado.md` |
| B12 | B3 enriquecido (related_codes) | `deepseek_pro/b3_hypothesis_generator.md` |
| A16 | Interchangeability Tester | `deepseek_pro/a16_interchangeability_tester.md` |
| B2a | Indicator Extractor (FLASH) | `deepseek_flash/b2a_extract_indicators.md` |
| B2b | Code Generator (PRO) | `deepseek_pro/b2b_generate_codes.md` |

### Cableado del pipeline

| # | Ítem | Archivo |
|---|---|---|
| B17 | SaturationCalculator cableado | `tasks.py` |
| B18 | Prototype cache rebuild | `tasks.py` |
| B19 | GraphRAG extraction cableado | `tasks.py` |
| B20 | Batch → Incremental (ProcessingState gate) | `tasks.py` |
| B23 | Agentes huérfanos wrappers (A14, A15, A16) | `tasks.py` |

### Adopciones del sistema antiguo

| # | Ítem | Origen | Archivos |
|---|---|---|---|
| A1 | ParadigmState + SQL check | `category saturator.json` | `synthesis.py`, `tasks.py`, `saturation.py`, `paradigm_integrator.md` |
| A2 | Anchor-based reconstruction | `Open Coder - Document.json` (Hacedor de texto) | `segment.py`, `segmentador.py`, `tasks.py` |
| A4 | Agrupador A07 | `My workflow 2.json` | `agrupador.md`, `tasks.py` |
| A5 | Tríada ENRICH/SUBDIVIDE/DIVIDE | `Recategorización.json` | `enums.py`, `algorithmic_checks.py`, `recategorization_decider.md` |
| A6 | TheoSampler SQL | `ur mom.json` | `category.py`, `tasks.py` |
| A7 | Evidence Map | `My workflow 4.json` | `tasks.py` |
| A8 | Mem CP + Mem LP | `Open Coder - Document.json` | `workflow.py` |
| A9 | Dynamic Schema Generator | `My workflow 2.json` (Parser6) | `core/dynamic_schema.py` |
| A10 | Main Concern 3 preguntas | `Selective Coder.json` (Core Concern Finder) | `main_concern_proposer.md` |
| A11 | Hypothesis Evidence Counter | `category saturator.json` (Code1) | `algorithmic_checks.py`, `evidence_classifier.md` |

### Arquitectura

| # | Ítem | Archivo |
|---|---|---|
| B21 | StateGraph (10 nodos, 3 routing, PostgresSaver) | `workflow.py`, `tasks.py` |
| B22 | WebSocket/SSE notificaciones | `api/v1/events.py`, `main.py` |
| — | Flag `ORCHESTRATION_MODE=celery|graph` | `documents.py` |
| — | Migraciones 008 + 009 | `migrations/versions/008_*.py`, `009_*.py` |

---

## ⚠️ EXPERIMENTAL — Graph mode (B21 partial)

El StateGraph tiene 10 nodos implementados. En modo `ORCHESTRATION_MODE=graph`:

| Nodo | Estado | Qué hace |
|---|---|---|
| segment_and_index | ✅ | `_ensure_segmented()` síncrono |
| extract_entities | ✅ | `batch_extract_graph` fire-and-forget |
| batch_code | ✅ | `b2_open_code` + `b2_5_assign` directos |
| map_synthesize | ✅ | `process_synthesis_agents_b` vía Celery con timeout |
| reduce_synthesize | ✅ | No-op (delegado a map) |
| find_core_concern | ✅ | `task_a14_main_concern` directo |
| generate_hypotheses | ✅ | `b3_generate_hypotheses` directo (o usa output de map) |
| calculate_saturation | ✅ | `update_saturation` fire-and-forget |
| hitl_review | ✅ | `interrupt()` — pausa el grafo |
| final_report | ⚠️ | Placeholder (Fase 14) |

**Default: `ORCHESTRATION_MODE=celery` (probado). `graph` es experimental.**

---

## 🔧 Bugs resueltos esta sesión

| Bug | Archivo | Fix |
|---|---|---|
| `JSONB` no importado en `category.py` | `category.py:7` | Añadido `from sqlalchemy.dialects.postgresql import JSONB` |
| `Boolean` no importado en `synthesis.py` | `synthesis.py:6` | Añadido `Boolean` al import de sqlalchemy |
| `TimestampMixin` no importado en `synthesis.py` | `synthesis.py:4` | Añadido `TimestampMixin` al import de base |
| `ParadigmState` sin timestamps | `synthesis.py:132` | Cambiado `Base` → `Base, TimestampMixin` |
| Migración 009 con tipos incorrectos | `009_paradigm_states.py` | `DateTime()` → `DateTime(timezone=True)`, nullable corregido |
