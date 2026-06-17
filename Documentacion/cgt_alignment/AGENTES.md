# AGENTES.md — Registro Canónico de Agentes CGT

> **Fuente única de verdad.** Este documento es la referencia autoritativa para tiers, estados, inputs/outputs, y prompts de todos los agentes del sistema. Los demás documentos (kb.md, 1-Refaccion, 4-Patrones, 5-Adaptacion) referencian este registro.

---

## Leyenda

| Símbolo | Significado |
|---------|-------------|
| 🟣 PRO | Modelo de razonamiento profundo. Outputs multi-párrafo. Síntesis, generación, análisis cualitativo complejo. |
| 🟡 FLASH | Modelo rápido. Outputs de hasta ~1 párrafo. Tareas estructuradas: clasificación, evaluación, extracción simple. |
| ⚙️ ALG | Algorítmico (sin LLM). Regex, heurísticas, SQL, embedding math. |
| ⚙️+🟡 | Híbrido: capa algorítmica para ~90% de casos + FLASH solo para borderline. |
| 🟢 | Implementado con 4 patrones (P1-P4) |
| 🟡 | Implementado parcialmente |
| 🔴 | Pendiente |

---

## Fase A: Open Coding (por documento)

| Agente | Tier | Estado | Prompt | Input | Output | Corre | Consume | Alimenta |
|--------|------|--------|--------|-------|--------|-------|---------|----------|
| `population_generalizer` | 🟡 FLASH | 🔴 | `deepseek_flash/population_generalizer.md` | `raw_population_description` | `{generalized_population, spatial_frame, temporal_frame}` | Al crear proyecto | Población cruda del investigador | `proyectos.population_assumption` |
| `glaser_data_classifier` | ⚙️+🟡 FLASH | 🟡 | `deepseek_flash/glaser_data_classifier.md` | `segmento.texto`, `interview_type` | `{data_type, rationale, confidence}` | Por segmento, pre-codificación | Solo el segmento | `segmentos.tipo_dato_glaser` → A1 |
| `incident_extractor` | 🟡 FLASH | 🔴 | `deepseek_flash/incident_extractor.md` | `segmento.texto` (baseline), `object_of_study`, `coding_style` | `{jot, what_is_this_about, what_category, what_is_happening, participants_pattern, confidence, keep_moving}` | Por segmento baseline | NADA (aislado) | `extracted_incidents` → B1 |
| `core_pattern_extractor` | 🟣 PRO | 🔴 | `deepseek_pro/incident_extractor.md` (per-doc) | `incidents[]` del documento, `object_of_study` | `{pattern_description, evidence_quotes[], confidence}` | Por documento | Solo incidentes del doc actual | `document_processes.pattern_of_interest` → A4 |
| `core_pattern_verifier` | 🟣 PRO | 🔴 | `deepseek_pro/core_pattern_verifier.md` | `pattern_of_interests[]` (últimos 3 docs), `population_context` | `{convergence_assessment, converging[], diverging[], recommendation}` | Cada 3 documentos | Patrones individuales de A2 | 🛑 HITL gate |
| `a1_population_context` | 🟣 PRO | 🟡 | `deepseek_pro/a1_population_context.md` | `segmentos` del doc, `population_context` anterior | `{surprising_details, language_patterns, data_production_context}` | Por documento | Segmentos del doc actual + contexto acumulado | `population_contexts` |
| `a2_process_identifier` | 🟣 PRO | 🟡 | `deepseek_pro/a2_process_identifier.md` | `segmentos` del doc, `object_of_study` | `{process_description, similarity_to_previous}` | Por documento | Segmentos del doc | `document_processes` |

## Fase B: Síntesis Cross-Document

| Agente | Tier | Estado | Prompt | Input | Output | Corre | Consume | Alimenta |
|--------|------|--------|--------|-------|--------|-------|---------|----------|
| `incident_comparator` (B1) | 🟣 PRO | 🔴 | `deepseek_pro/incident_comparator.md` | `extracted_incidents[]` de TODOS los docs | `{incident_groups[], ungrouped[]}` | ≥3 docs listos | Solo incidentes. NO ve categorías. | `incident_groups` → B2 |
| `pattern_labeler` (B2) | 🟣 PRO | 🔴 | `deepseek_pro/pattern_labeler.md` | `incident_groups[]` de B1, `object_of_study` | `{proposed_labels[], anomalies[]}` | Después de B1 | Solo grupos de B1 | B3 (critic) |
| `label_critic` (B3) | 🟡 FLASH | 🔴 | `deepseek_flash/label_critic.md` | `proposed_labels[]` de B2 + incidentes fuente | `{evaluations[] (verdict, rationale, suggested_improvement)}` | Después de B2 (bucle máx 3 its) | Etiquetas de B2 + incidentes | B2 (si MOD) o DB (si SAT) |
| `evidence_retriever` (B4) | ⚙️ ALG | 🟡 | (RAG sin LLM — TEI embeddings) | `category_name`, `category_definition` | `[{segment_text, document_name, similarity_score}]` top-K | Después de B3 (por categoría aprobada) | Corpus completo de segmentos | `code_document_summaries` |

## Fase 5b-A: Core Category Detection (Selective Coding)

| Agente | Tier | Estado | Prompt | Input | Output | Corre | Consume | Alimenta |
|--------|------|--------|--------|-------|--------|-------|---------|----------|
| `main_concern_proposer` | 🟣 PRO | 🟡 | `deepseek_pro/main_concern_proposer.md` | `categorias[]`, `memos[]`, `population_context` | `{candidates[] (gerundio, rationale, supporting_codes, orphan_patterns)}` | Inicio de selective coding | Sistema completo de categorías + memos | 🛑 HITL gate |
| `main_concern_critic` | 🟣 PRO | 🟡 | `deepseek_pro/main_concern_critic.md` | `candidates[]` del proposer | `{evaluations[] (verdict: SAT\|MOD\|FORCED, grounding, coverage, abstraction)}` | Después del proposer | Candidatos del proposer | 🛑 HITL gate |
| `core_emergence_proposer` | 🟣 PRO | 🟡 | `deepseek_pro/core_emergence_proposer.md` | `categorias[]` (sistema reducido), `pattern_of_interest` confirmado | `{candidates[] (centralidad, poder_unificador, grab_teórico)}` | Después de HITL main_concern | Categorías del sistema reducido | 🛑 HITL gate |
| `core_emergence_critic` | 🟡 FLASH | 🟡 | `deepseek_pro/core_emergence_critic.md` | `candidates[]` + incidentes fuente | `{evaluations[] (verdict: valid\|refine\|split, intercambiabilidad)}` | Después del proposer | Candidatos + incidentes | 🛑 HITL gate |

## Fase 5b-B: Selective Reduction

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `selective_reduction_proposer` | 🟣 PRO | 🟡 | `deepseek_pro/selective_reduction_proposer.md` | `categorias[]`, `pattern_of_interest` | `{kept[], merged[], discarded[] (con rationale)}` |
| `selective_reduction_critic` | 🟣 PRO | 🟡 | `deepseek_pro/selective_reduction_critic.md` | `reduction_plan` del proposer | `{evaluations[] (false_positives, false_negatives)}` |

## Fase 5b-C: Core Saturation Loop

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `core_saturation_proposer` | 🟣 PRO | 🔴 | `deepseek_pro/core_saturation_proposer.md` | `categoria.paradigm_state`, `incidentes_nuevos[]` del doc | `{expansions[] (propiedad\|dimension\|condicion\|consecuencia)}` |
| `core_saturation_critic` | 🟡 FLASH | 🔴 | `deepseek_flash/core_saturation_critic.md` | `expansions[]` + `paradigm_state` actual | `{verdict: SAT\|MOD\|FORCED, did_state_expand}` |
| `rename_detector` | ⚙️ ALG | 🟢 | (SQL heuristics) | `category_id` | `{needs_rename: bool, reason}` |
| `rename_suggester` | 🟣 PRO | 🟢 | `deepseek_pro/rename_suggester.md` | `categoria`, `definition_versions` | `{suggestions[] (conservador\|moderado\|transformador)}` |
| `SaturationGapAnalyzer` | ⚙️ ALG | 🟢 | (4 señales sin LLM) | `proyecto_id` | `{gaps[{category_id, signal, detail}]}` |
| `EmergentSampler` (TheoSampler) | 🟣 PRO | 🟡 | `deepseek_pro/property_sampler.md` | `categoria.paradigm_state`, `corpus` | `{relevant_segments[], sampling_recommendation}` |

## Fase 5b-D: Database A/B

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `database_a_proposer` | 🟣 PRO | 🟡 | `deepseek_pro/database_a_proposer.md` | `categorias[]` saturadas, `core_category` | `{nodes[] (label, entity_type, definition, is_core)}` |
| `database_a_critic` | 🟣 PRO | 🟡 | `deepseek_pro/database_a_critic.md` | `nodes[]` del proposer | `{verdict, issues[]}` |
| `database_b_proposer` | 🟣 PRO | 🟡 | `deepseek_pro/database_b_proposer.md` | `nodes[]`, `conceptual_relationships`, `hypotheses` | `{edges[] (source, target, relationship_type, evidence)}` |
| `database_b_critic` | 🟣 PRO | 🟡 | `deepseek_pro/database_b_critic.md` | `edges[]` del proposer | `{verdict, issues[]}` |

## Theoretical Playground (Fase 6b)

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `conceptual_elaborator` | 🟣 PRO | 🟢 | `deepseek_pro/conceptual_elaborator.md` | `blob_a`, `blob_b`, `theoretical_code` | `{converging_evidence[], diverging_evidence[], relationship}` |
| `memo_theoretical_tagger` | 🟡 FLASH | 🔴 | `deepseek_flash/memo_theoretical_tagger.md` | `memo.contenido` | `{family_affinities[{family, score}]}` |
| `cross_family_synthesizer` | 🟣 PRO | 🔴 | (pendiente) | `sorting_attempts[]` | `{integrated_families, recommendation}` |
| `ghost_blob_mapper` | 🟣 PRO | 🟢 | `deepseek_pro/ghost_blob_mapper.md` | `memo`, `categorias[]` | `{suggested_category, confidence}` |
| `ecosystem_gap_detector` | ⚙️ ALG | 🟢 | (grafo + heurísticas) | `blobs[]`, `tendrils[]` | `{gaps[{type, detail}]}` |

## Fase 6a: Redacción Natural

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `natural_writer` | 🟣 PRO | 🔴 | `deepseek_pro/natural_writer.md` | `memos[]` ordenados (sorting group) | `{draft, citations[], concepts[]}` |
| `writing_critic` | 🟣 PRO | 🔴 | `deepseek_pro/writing_critic.md` | `draft`, `memos[]` fuente | `{verdict: SAT\|MOD\|FORCED, issues[{type, location, suggestion}]}` |
| `gap_feeler` | 🟡 FLASH | 🔴 | `deepseek_flash/gap_feeler.md` | `draft`, `project_id` | `{gaps[{type, description, severity}]}` |

## Fase 6c: Diálogo con Literatura

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `literature_comparer` | 🟣 PRO | 🔴 | `deepseek_pro/literature_comparer.md` | `teoría` (cats + hyps + props), `literature_fragments[]` | `{table[{category, extends, modifies, integrates, transcends}]}` |
| `literature_critic` | 🟣 PRO | 🔴 | `deepseek_pro/literature_critic.md` | `comparison_table` | `{verdict, issues[]}` |

## Fase 6d: Aplicabilidad

| Agente | Tier | Estado | Prompt | Input | Output |
|--------|------|--------|--------|-------|--------|
| `applicability_engine` | 🟣 PRO | 🔴 | `deepseek_pro/applicability_engine.md` | `teoría` completa | `{control_variables[], access_variables[], guidelines[], implications[]}` |
| `applicability_critic` | 🟣 PRO | 🔴 | `deepseek_pro/applicability_critic.md` | `guidelines[]`, `teoría` | `{verdict, issues[]}` |

## Transversales

| Agente | Tier | Estado | Descripción |
|--------|------|--------|-------------|
| `ReSpecAgent` | 🟣 PRO | 🔴 | Monitorea señales de re-especificación (incidentes ambiguos, etiquetas rechazadas, divergencias sin resolver, memos huérfanos). Sugiere bajar de nivel para re-examinar. |
| `HITLModificationAgent` (P5) | 🟡 FLASH + 🟣 PRO + 🟣 PRO | 🟢 | 5 fases: FLASH filter → PRO planner → ReactRunner execution → PRO evaluator → apply. |
| `OrchestratorRuleEngine` | ⚙️ ALG | 🟢 | Reglas determinísticas (90%) + fallback FLASH (10%) para routing del pipeline. |
| `ContextWindowManager` | ⚙️ ALG | 🔴 | Tool genérica para procesamiento iterativo con presupuesto de contexto. Ver `6-ContextWindowManager.md`. |

---

## Principio de Selección de Tier

> **FLASH** cuando: (a) el output es ≤1 párrafo (~200-300 palabras), (b) la tarea es estructurada (clasificación, evaluación, diff, extracción simple), (c) el volumen de llamadas es alto (cientos por proyecto). **Fundamento:** nuestro FLASH produce outputs de hasta ~1 párrafo con alta precisión para tareas específicas.
>
> **PRO** cuando: (a) el output requiere razonamiento multi-párrafo, (b) la tarea implica síntesis cualitativa, generación creativa, o análisis profundo, (c) el volumen de llamadas es bajo (decenas por proyecto).
>
> **⚙️ ALG** cuando: la tarea es determinística y no requiere juicio cualitativo (regex, SQL, math, graph traversal).

---

> **Última actualización:** 2026-06-16 — Refleja resoluciones de auditoría C1-C7.
