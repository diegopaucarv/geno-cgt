# TECH_DEBT.md — Deuda Técnica de Parámetros Hardcodeados

> **Extraído de:** `Documentacion/cgt_alignment/1-Refaccion open coding.md` §10
>
> **Propósito:** Catálogo centralizado de valores hardcodeados que deben migrarse a configuración, columnas de BD, o variables de entorno. Ordenado por prioridad de refactorización.
>
> **Última actualización:** 2026-06-16

---

## 🔴 Críticos (bloquean multi-tenancy o causan drift semántico)

### TD-01: `DEFAULT_POPULATION_ASSUMPTION` hardcodeado

| Campo | Valor |
|-------|-------|
| **Ubicación** | `backend/app/models/domain/project.py` L9-13 |
| **Valor actual** | `"hábitos hipotéticos de comportamiento que procesan preocupaciones similares o más amplias en la vida diaria del entrevistado"` |
| **Valor deseado** | Leer de `backend/app/core/config.py` como `DEFAULT_POPULATION_ASSUMPTION` (variable de entorno con fallback al valor actual) |
| **Impacto** | Cada proyecto creado sin especificar supuesto poblacional hereda este texto. Si cambia la población de estudio, hay que cambiar el código. |
| **Esfuerzo** | Bajo — mover la constante a `config.py` y referenciarla |
| **Referencias** | `workers/heavy/tasks.py` L107-115 (`_get_population_assumption`), `workers/heavy/agents_b.py` L41-48 |

### TD-02: `object_of_study` default "concern" disperso

| Campo | Valor |
|-------|-------|
| **Ubicaciones** | `backend/app/models/domain/project.py` L65 (`default="concern"`), `workers/heavy/tasks.py` L551 (`"concern"` fallback) |
| **Valor actual** | `"concern"` hardcodeado en 2 lugares |
| **Valor deseado** | Un solo default en `config.py` → `DEFAULT_OBJECT_OF_STUDY = "concern"`. La columna `proyectos.object_of_study` (F0.3.5) ya existe pero el fallback en tasks.py sigue hardcodeado. |
| **Impacto** | Si se cambia el default (ej. "behavior" para ciertos proyectos), hay que buscar todos los `"concern"` sueltos. |
| **Esfuerzo** | Bajo — centralizar en `config.py`, actualizar 2 referencias |

### TD-03: `coding_styles` default `["gerundio", "in_vivo"]` sin propagación automática

| Campo | Valor |
|-------|-------|
| **Ubicación** | `backend/app/core/coding_styles.py` L249-251 (`get_default_styles()`), `backend/app/models/domain/project.py` L55 (comentario en docstring de `population_assumption`) |
| **Valor actual** | `["gerundio", "in_vivo"]` |
| **Valor deseado** | Al crear proyecto, compilar `coding_style_instruction` (F0.3.4) desde los estilos elegidos y guardarla en la columna. Los agentes deben leer de `proyectos.coding_style_instruction`, no recalcular. |
| **Impacto** | Los agentes actualmente recalculan la instrucción cada vez (llamando `get_combined_instruction()`). Con la columna nueva, esto es redundante. |
| **Esfuerzo** | Medio — requiere modificar `workers/heavy/agents_b.py` y `tasks.py` para leer de la columna |

---

## 🟡 Importantes (causan inconsistencia pero no bloquean)

### TD-04: "main_concern" como string literal disperso en 8+ ubicaciones

| Campo | Valor |
|-------|-------|
| **Ubicaciones** | `workers/heavy/tasks.py` L1401, L1696, L1771, L1854, L1857, L1922, L1930; `backend/app/agents/transitions.py` `hitl_gate()` |
| **Valor actual** | `"main_concern"` como string literal en múltiples archivos |
| **Valor deseado** | Constante `GATE_MAIN_CONCERN = "main_concern"` en `transitions.py` o `config.py`. La unificación terminológica (F1.1) renombrará el concepto a "pattern_of_interest" en labels y docs, pero el gate name se mantiene por compatibilidad con BD. |
| **Impacto** | Typo en un string literal rompe el pipeline silenciosamente. Sin constante, no hay autocompletado ni refactor seguro. |
| **Esfuerzo** | Bajo — crear constantes en `transitions.py` y reemplazar |

### TD-05: Las "4 preguntas de Glaser" hardcodeadas en prompts, no en código

| Campo | Valor |
|-------|-------|
| **Ubicación** | `backend/app/prompts/deepseek_flash/incident_extractor.md` (dentro del prompt) |
| **Valor actual** | 4 preguntas escritas directamente en el prompt markdown |
| **Valor deseado** | Las preguntas deben parametrizarse: la pregunta 4 depende de `object_of_study`. Si `object_of_study="emotion"`, la pregunta 4 debe ser sobre emociones, no preocupaciones. |
| **Impacto** | El `incident_extractor` (F2.2) debe recibir las preguntas como variables del template, no leerlas del prompt fijo. |
| **Esfuerzo** | Medio — requiere refactorizar el prompt para aceptar `{pregunta_4}` como variable |

### TD-06: `population_generalizer` no existe — se hardcodea el output

| Campo | Valor |
|-------|-------|
| **Ubicación** | No implementado (F1.2) |
| **Valor actual** | El campo `population_assumption` se llena manualmente sin validación ni generalización |
| **Valor deseado** | Al crear proyecto, `population_generalizer` (FLASH) transforma la descripción cruda en población generalizada + infiere `spatial_frame` y `temporal_frame` |
| **Impacto** | Sin generalización, el alcance teórico es arbitrario. La validez de la teoría depende de esto. |
| **Esfuerzo** | Medio — crear `workers/fast/population_generalizer.py`, prompt, y endpoint |

---

## 🟢 Futuro (nice to have, no bloquean)

### TD-07: `max_tokens=1024` hardcodeado en segmentación

| Campo | Valor |
|-------|-------|
| **Ubicación** | `workers/nlp/tasks.py` L192-198 (`segmentar_documento` signature default) |
| **Valor actual** | `max_tokens: int = 1024` |
| **Valor deseado** | Leer de `proyectos.config_segmentacion.max_tokens` (ya existe la columna JSONB, pero no se usa en el worker NLP) |
| **Impacto** | Diferentes tipos de documentos (entrevistas largas vs. tweets) necesitan diferentes tamaños de ventana |
| **Esfuerzo** | Bajo — leer de la BD en vez del default |

### TD-08: `SPACY_MODEL = "es_core_news_lg"` hardcodeado

| Campo | Valor |
|-------|-------|
| **Ubicación** | `workers/nlp/config.py`, `docker-compose.yml` L218 |
| **Valor actual** | `"es_core_news_lg"` |
| **Valor deseado** | Variable de entorno `SPACY_MODEL` (ya existe en docker-compose). Solo verificar que no haya fallback hardcodeado en el código. |
| **Impacto** | Si se cambia el modelo (ej. `es_core_news_trf`), hay que tocar docker-compose y código |
| **Esfuerzo** | Bajo — verificar que `config.py` lea de `os.getenv` |

### TD-09: Formato del "jot" no documentado como estándar

| Campo | Valor |
|-------|-------|
| **Ubicación** | `backend/app/prompts/deepseek_flash/incident_extractor.md` |
| **Valor actual** | El formato del jot (gerundio + what_is_this_about + etc.) está implícito en el prompt |
| **Valor deseado** | Documentar el formato canónico del jot en `AGENTES.md` o en un documento de estándares. El output schema del prompt debe ser la fuente de verdad. |
| **Impacto** | Si otro agente consume jots con formato inconsistente, falla silenciosamente |
| **Esfuerzo** | Bajo — documentar |

---

## 📊 Resumen

| Prioridad | Cantidad | Esfuerzo total estimado |
|-----------|----------|------------------------|
| 🔴 Crítico | 3 (TD-01 a TD-03) | ~3 horas |
| 🟡 Importante | 3 (TD-04 a TD-06) | ~4 horas |
| 🟢 Futuro | 3 (TD-07 a TD-09) | ~2 horas |
| **Total** | **9** | **~9 horas** |

> **Nota:** Varios de estos items se resuelven automáticamente al implementar las fases del checklist:
> - TD-01 → F1.1.3 (unificar DEFAULT_POPULATION_ASSUMPTION)
> - TD-06 → F1.2 (crear population_generalizer)
> - TD-04 → F1.1.1 (unificación terminológica)
> - TD-03 → F0.3.4 + F4.1 (leer de columna `coding_style_instruction`)
