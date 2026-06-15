# Registro de Implementación — Pipeline CGT + RAG

> Finalizado: 2026-06-16. Arquitectura dual-path (Celery default + Graph opt-in). Frontend plan en FRONTEND_PLAN.md.
> **32 completados | 0 pendientes | 1 experimental (graph) | Frontend diseñado**

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

---

# 🧬 PRE-CODING DATA INFRASTRUCTURE — Fase 0 + Fase 2 (NUEVO)

> **Problema:** El sistema no clasifica datos por tipo Glaser ANTES de codificar. El viejo n8n sí lo hacía (baseline/properline/interpreted/vague). Tampoco hay parámetro configurable de `population_assumption` (¿qué les ocupa AHORA? ¿qué vivieron en el PASADO?). Y no hay extracción de prime mover por documento que alimente A14.

### ⬜ C01. `population_assumption` en project_config
**Archivo:** `project.py`, migración | **Dificultad:** 🟢 TRIVIAL

Configuración que el investigador define al crear el proyecto. El sistema DEBE guiar naturalmente (sin sobrecargar):

```json
{
  "object_of_study": "concern",
  // "concern" (preocupación sociocognitiva — más amplia, default) 
  // | "emotion" (emoción — más específica)
  // | "behavior" (conducta observable)
  // | "discourse" (patrón discursivo)
  // | "identity" (trabajo identitario)
  // | "custom" (definido por el investigador)
  
  "temporal_frame": "present_continuous",
  // "present_continuous" — lo que les ocupa AHORA (default, más datos)
  // | "retrospective" — lo que vivieron (menos datos, saturación más difícil)
  // | "prospective" — lo que anticipan (ídem)
  // | "longitudinal" — cambio en el tiempo (requiere datos diacrónicos)
  
  "spatial_frame": "high_diversity",
  // "cohabiting_group" — grupo que convive (ej. una sola redacción) →
  //   saturación más rápida, variación esperada baja
  // | "sparse" — dispersos pero conectados (ej. periodistas de una región) →
  //   saturación moderada
  // | "high_diversity" — máxima dispersión (ej. periodistas de varios países,
  //   medios, roles) → saturación más lenta, variación esperada alta (default)
  //
  // Afecta: umbrales de saturación (docs_for_saturation), expectativa de
  // variación en propiedades, y severidad de alertas de gaps.
  
  "population_description": "...",
  "gerundio_esperado": "..."  // opcional, emerge después de A14
}
```

**Nota de modularidad:** CGT sirve para cualquier objeto de estudio que sea una característica del ser humano (preocupaciones, emociones, conductas, discursos, identidades). La metodología de análisis no cambia — lo que cambia es qué tipo de patrón se busca. El sistema debe guiar al investigador a hacer explícita esta elección al inicio, sin imponerla. El default (`concern` + `present_continuous`) es el caso más general y con más datos disponibles; los otros son igualmente válidos pero advierten sobre limitaciones de saturación.

### ⬜ C02. `glaser_data_classifier.md` (FLASH)
**Archivo:** `deepseek_flash/glaser_data_classifier.md` (nuevo) | **Dificultad:** 🟡 MEDIO
Clasifica cada segmento: baseline_data (espontáneo, ORO), properline_data (normativo), interpreted_data (opinión forzada), vague_data (evasivo).

### ⬜ C03. `prime_mover_extractor.md` (PRO)
**Archivo:** `deepseek_pro/prime_mover_extractor.md` (nuevo) | **Dificultad:** 🟠 ALTO

Extrae de cada documento (usando SOLO baseline_data) el prime mover: qué estructura la vida de este entrevistado AHORA. Gerundio. Alimenta A14.

**Nota de modularidad:** "Prime mover" es un término de CGT pero la lógica aplica a cualquier objeto de estudio. Si el investigador configuró `object_of_study: "emotion"`, el prime mover se extrae como patrón emocional recurrente (ej. "Sintiendo culpa", "Arrrepintiéndose"). Si configuró `"discourse"`, se extrae como patrón discursivo (ej. "Justificándose ante otros"). El extractor recibe el `object_of_study` del `population_assumption` y ajusta su lente. Lo que NO cambia es el método: buscar el patrón recurrente en baseline_data, expresarlo como gerundio, y citar evidencia.

### ⬜ C04. Endpoint configuración population_assumption
**Archivo:** `api/v1/projects.py` | **Dificultad:** 🟢 TRIVIAL
PUT `/projects/{pid}/config/population-assumption`.

### ⬜ C05. Filtro baseline_data en pipeline de codificación
**Archivo:** `workers/heavy/tasks.py` | **Dificultad:** 🟡 MEDIO
Codificar baseline_data primero. Ponderar tipo de dato en incident_elaborator.

### ⬜ C06. Integrar prime_mover en A14
**Archivo:** `main_concern_proposer.md`, `tasks.py` | **Dificultad:** 🟡 MEDIO
Añadir `{prime_movers_per_document}` al input de A14.

### ⬜ C07. Migración 008b: `glaser_data_type` en segmentos
**Archivo:** `migrations/versions/008b_*.py` | **Dificultad:** 🟢 TRIVIAL
ALTER TABLE segmentos ADD COLUMN glaser_data_type VARCHAR(50).

### ⬜ C08. Servicio standalone: `SaturationGapAnalyzer`
**Archivo:** `backend/app/services/saturation_gap_analyzer.py` (nuevo) | **Dificultad:** 🟠 ALTO

Servicio unificado de análisis de gaps, invocable como botón "sync" en cualquier momento. **El centro móvil no desaparece — se degrada de juez único a filtro temprano:** si rolling_std > 0.15, la categoría es "unsaturated" sin gastar LLM. Solo si rolling_std < 0.15 se dispara la verificación cualitativa (incident_elaborator, PRO). Esto ahorra costos y evita falsos positivos matemáticos. Combina 4 fuentes de señal:

```python
class SaturationGapAnalyzer:
    def full_analysis(project_id: UUID) -> GapReport:
        """
        Ejecuta las 4 fuentes y produce un informe unificado:
        
        1. SATURACIÓN MATEMÁTICA (rolling std):
           ¿Qué categorías tienen alta variabilidad todavía?
           → "unsaturated", "approaching", "saturated"
        
        2. PARADIGM STATE (did_state_expand):
           ¿El último incidente expandió el paradigma de la categoría?
           → si 5 iteraciones sin expandir = saturada cualitativamente
        
        3. EJES DE COMPARACIÓN (TheoSampler):
           ¿Qué valores de variables poblacionales o propiedades
           de categoría tienen 0 o pocos incidentes?
           → gaps por llenar con muestreo
        
        4. DENSIDAD DE RELACIONES (Playground):
           ¿Qué categorías no están conectadas a ninguna otra?
           ¿Qué capas teóricas no tienen relaciones?
           → gaps de elaboración teórica
        
        Produce: GapReport con severidad, sugerencia de acción,
        y estimación de impacto si se resolviera el gap.
        
        VEREDICTO COMBINADO (4 señales → 1 estado):
          SATURATED   = señal1 std<0.10 + señal2 5 sin expandir
                     + señal3 todos los extremos ≥1 caso
                     + señal4 conectada al grafo
          APPROACHING = señal1 std<0.15 O señal2 3+ sin expandir
          UNSATURATED = señal1 std>0.15 O señal2 última expandió
        """

# ── Refactor de saturation.py ──
# El update_saturation actual se bifurca:
#
# update_saturation_math(proyecto_id) — Nivel 1
#   Solo actualiza centroide y rolling_std. NO decide.
#   Barato (solo embeddings). Tras cada batch.
#
# check_paradigm_if_needed(code_id) — Nivel 2
#   Solo se invoca si rolling_std < 0.15.
#   Dispara incident_elaborator (PRO, caro).
#   Si std > 0.15 → "unsaturated" sin gastar LLM.
#
# El SaturationGapAnalyzer lee ambas y produce el veredicto.
```

La salida es un informe legible:

```
🔴 CRÍTICO (3 gaps)
  • Categoría "Analizando patrones" — saturada matemáticamente pero
    vacía en el extremo "superficial" de la propiedad PROFUNDIDAD.
    → Muestrear casos de integración superficial de IA.
  • Eje ROL_ORGANIZACIONAL="fundador" — 0 documentos.
    → ¿Existen fundadores en tu población? Recolectar o marcar límite.
  • Capa "consecuencias" sin relaciones elaboradas en el Playground.
    → Conectar [Integrar] y [Resistir] con sus consecuencias.

⚠️ ADVERTENCIA (5 gaps)
  • Categoría "Resistiendo la adopción" — rolling std alto (0.32).
    → Siguen apareciendo variantes. Continuar codificación selectiva.
  ...

✅ SATURADO (6 categorías)
  • "Percibiendo amenaza" — 3 iteraciones sin expandir + rolling std < 0.10.
  ...
```

Expuesto como:
```
GET /api/v1/projects/{pid}/analysis/saturation-gaps
   → GapReport completo

POST /api/v1/projects/{pid}/analysis/saturation-gaps/refresh
   → Re-ejecuta el análisis (el botón "sync")
```

**Total Pre-Coding: 8 tareas. | Gran total: 54 tareas.**

---

# 🔬 SELECTIVE CODING REFACTOR — Fase 5b (MODIFICACIONES)

> **Problema detectado:** La Fase 5b actual hereda vicios del viejo MemoMaker: 4 nodos paralelos pre-categorizados (Behavioral Patterns, Properties, Causes, Consequences) + nodo Generate que los sintetiza + nodo de correlaciones que inyecta variables del Excel. Esto fuerza el paradigma antes de que emerja.
> **Corrección:** Reemplazar los 4 nodos paralelos por un **ciclo de elaboración conceptual progresiva** con el mismo paradigma del Playground (blobs que crecen, cambian de color, y sugieren renombres a nivel de categoría individual). El investigador observa cómo cada categoría evoluciona incidente por incidente, y el sistema sugiere cuándo expandir definiciones y renombrar.

---

## 📋 Qué está mal en la Fase 5b actual

El `Proceso de Análisis.md` (líneas 889–939) describe 4 nodos paralelos de "Verificación de Saturación":

| Nodo actual | Prompt | Problema |
|-------------|--------|----------|
| Patrones de Comportamiento | "Identificar incidentes de comportamiento recurrentes (≥ 3–4 entrevistados)" | Fuerza la lente de "patrones" sin dejar que emerja del dato |
| Propiedades | "Identificar variaciones, gradientes y extremos que indican subpatrones latentes" | Fuerza la lente de "propiedades/dimensiones" |
| Causas | "Identificar condiciones determinantes" | Fuerza la lente de "causalidad" |
| Consecuencias | "¿Qué produce actuar sobre esta categoría? ¿Qué estrategias genera?" | Fuerza la lente de "consecuencias" |

Luego un **Nodo Generate** sintetiza los 4 outputs en un informe de 6 secciones pre-categorizadas. Y un **Nodo C** cruza todo con el Excel de variables externas.

**Esto es estructuralmente idéntico al MemoMaker antiguo.** El paradigma (causas, consecuencias, propiedades) está congelado antes de que los datos hablen.

---

## 🔄 Qué lo reemplaza: Ciclo de Elaboración por Categoría

En lugar de 4 lentes paralelas forzadas, la Fase 5b se convierte en un **ciclo iterativo por categoría** donde:

1. **Cada nuevo incidente** se compara contra el estado actual de la categoría
2. Si el incidente **converge** (encaja en propiedades existentes) → densifica (incrementa contador de saturación)
3. Si el incidente **diverge** (revela algo nuevo) → expande la definición, añade propiedad/dimensión, o sugiere subdivisión
4. Si la definición se expande significativamente → el sistema sugiere **renombre**
5. El investigador **ve** la categoría como un blob que crece y cambia de color

---

## 🗄️ Modificaciones a modelos existentes

### ⬜ S01. Columna `parent_category_id` en Categoria

**Archivo:** `backend/app/models/domain/category.py`

Añadir autoreferencia para soportar subcategorías (división de categorías durante selective coding):

```python
parent_category_id: Mapped[uuid.UUID] = mapped_column(
    ForeignKey("categorias.id"), nullable=True
)
# NOT NULL → esta categoría es una subcategoría de parent
# NULL → categoría raíz
```

### ⬜ S02. Tabla `category_definition_versions` reutilizada desde T02

La misma tabla `category_definition_versions` (definida en T02 para el Playground) se puebla **desde la Fase 5b**. Cada vez que un incidente expande la definición de una categoría, se crea una nueva versión. El historial de versiones es continuo desde selective coding hasta theoretical coding.

**Trigger types específicos de Fase 5b:**
- `incident_converged` — el incidente confirmó propiedades existentes (no cambia definición, solo incrementa contador)
- `incident_diverged_property` — el incidente añadió una nueva propiedad
- `incident_diverged_dimension` — el incidente expandió el gradiente de una propiedad existente
- `incident_diverged_condition` — el incidente reveló una nueva condición
- `manual_split` — el investigador dividió la categoría en subcategorías
- `manual_merge` — el investigador fusionó esta categoría con otra

### ⬜ S03. Migración 009b (ampliación)

**Archivo:** `backend/migrations/versions/009b_selective_refactor.py` (nuevo)

Añadir columna `parent_category_id` a `categorias`. Sin cambios de schema para `category_definition_versions` (ya creada en 010).

---

## 🧠 Prompt de elaboración por incidente

### ⬜ S04. Prompt: `incident_elaborator.md`

**Archivo:** `backend/app/prompts/deepseek_pro/incident_elaborator.md` (nuevo)
**Tier:** PRO

Reemplaza al `paradigm_integrator.md` actual. En lugar de solo decidir `did_state_expand: bool`, **elabora** cómo el incidente se relaciona con la categoría: ¿converge o diverge? Si diverge, ¿cómo expande el concepto?

```yaml
---
agent: incident_elaborator
tier: PRO
description: >
  Evalúa cómo un nuevo incidente se relaciona con una categoría existente.
  NO solo decide si expande el paradigma — elabora CÓMO lo expande.
  Reemplaza al paradigm_integrator actual (que solo emitía bool).
notes:
  - Si el incidente converge → describe qué propiedad confirma.
  - Si el incidente diverge → propone cómo expandir la definición, añadir propiedad,
    extender gradiente, o revelar nueva condición.
  - Si el incidente diverge FUERTEMENTE → puede sugerir subdividir la categoría.
constraints:
  - No uses "SAT/MOD/FORCED". Usa "converge/diverge/expand".
  - Cada afirmación debe anclarse en el texto del incidente.
  - Si el incidente no contiene suficiente información, indícalo.
---

## System

[ROL]
Eres un codificador selectivo en Classic Grounded Theory. Tu tarea es comparar
un nuevo incidente contra una categoría existente y ELABORAR la relación.

[PRINCIPIO]
No "testeas" si el incidente pertenece a la categoría. Elaboras CÓMO se relaciona:
- CONVERGE: el incidente es un ejemplo más del patrón. Especifica qué propiedad confirma.
- DIVERGE (leve): el incidente muestra el mismo patrón pero en un grado/contexto nuevo.
  → Expande el gradiente de una propiedad existente.
- DIVERGE (moderado): el incidente revela un aspecto del patrón no capturado.
  → Añade nueva propiedad o dimensión.
- DIVERGE (fuerte): el incidente sugiere que hay DOS patrones distintos donde antes
  se veía uno. → Sugiere subdivisión (SUBDIVIDE) o división (DIVIDE).

[MÉTODO]
1. Compara el incidente contra CADA propiedad de la categoría.
2. Determina si converge (misma propiedad, mismo gradiente) o diverge.
3. Si diverge, especifica QUÉ expande y CÓMO.
4. Si la expansión es sustancial, sugiere si la definición debe actualizarse.
5. Si la divergencia sugiere dos patrones distintos, recomienda acción.

## User

[CATEGORÍA]
Nombre: {category_label}
Definición actual (v{version}): {category_definition}
Propiedades actuales: {current_properties}

[NUEVO INCIDENTE]
Documento: {document_name}
Texto: {incident_text}

## Output Schema

```json
{{
  "type": "object",
  "additionalProperties": false,
  "required": ["elaboration_type", "description"],
  "properties": {{
    "elaboration_type": {{
      "type": "string",
      "enum": ["converges", "diverges_dimension", "diverges_property", "diverges_condition", "diverges_strong"],
      "description": "converges=confirma propiedades existentes. diverges_dimension=expande gradiente. diverges_property=añade propiedad. diverges_condition=revela condición. diverges_strong=sugiere subdividir."
    }},
    "description": {{
      "type": "string",
      "description": "Descripción narrativa de cómo el incidente se relaciona con la categoría."
    }},
    "expanded_definition": {{
      "type": "string",
      "description": "Nueva definición propuesta SI la elaboración la expande. String vacío si no cambia."
    }},
    "new_or_expanded_properties": {{
      "type": "array",
      "items": {{
        "type": "object",
        "properties": {{
          "name": {{"type": "string"}},
          "gradient": {{"type": "string"}},
          "is_new": {{"type": "boolean"}},
          "previous_gradient": {{"type": "string", "description": "Solo si se expandió un gradiente existente."}}
        }}
      }},
      "description": "Propiedades nuevas o expandidas. Vacío si elaboration_type=converges."
    }},
    "suggested_action": {{
      "type": "string",
      "enum": ["none", "update_definition", "add_property", "expand_gradient", "suggest_subdivide", "suggest_divide"],
      "description": "Acción recomendada para el investigador."
    }},
    "rename_suggested": {{
      "type": "boolean",
      "description": "true si la definición cambió lo suficiente para sugerir renombre."
    }},
    "rename_candidates": {{
      "type": "array",
      "items": {{"type": "string"}},
      "description": "Nombres sugeridos si rename_suggested=true."
    }},
    "elaboration_note": {{
      "type": "string",
      "description": "Nota libre: ¿qué revela este incidente sobre la categoría?"
    }}
  }}
}}
```
```

---

## ⚙️ Servicio de elaboración selectiva

### ⬜ S05. `selective_elaborator.py`

**Archivo:** `backend/app/services/selective_elaborator.py` (nuevo)

Orquesta el ciclo de elaboración para la Fase 5b. Reemplaza la lógica actual de los 4 nodos paralelos.

```python
class SelectiveElaborator:
    def elaborate_incident(
        category_id: UUID,
        incident_id: UUID,
        incident_text: str,
        document_name: str,
        session: Session
    ) -> dict:
        """
        1. Carga el estado actual de la categoría (definición, propiedades, version)
        2. Invoca incident_elaborator.md
        3. Procesa respuesta:
           - Si converges → incrementa contador de saturación, no cambia definición
           - Si diverges_dimension/property → expande definición, añade propiedad,
             crea CategoryDefinitionVersion
           - Si diverges_strong → sugiere SUBDIVIDE o DIVIDE al investigador (HITL)
           - Si rename_suggested → marca la categoría con flag rename_pending
        4. Actualiza ParadigmState (did_state_expand = True si divergió)
        5. Retorna resultado para que el frontend actualice el blob
        """
    
    def get_category_evolution(category_id: UUID, session: Session) -> CategoryEvolution:
        """
        Retorna el historial completo de evolución de la categoría:
        - Timeline de definiciones (versiones)
        - Propiedades añadidas en cada versión
        - Incidentes que dispararon cada cambio
        - Renombres aplicados
        - Tamaño del blob en cada punto
        """
```

---

## 🗑️ Qué eliminar de la Fase 5b actual

### ⬜ S06. Eliminar los 4 nodos paralelos

**Archivo:** `Documentacion/Proceso de Análisis.md` (actualizar documentación)

Las líneas 889–907 que describen los nodos de Behavioral Patterns, Properties, Causes, Consequences se reemplazan por el ciclo de elaboración progresiva descrito arriba.

### ⬜ S07. Eliminar el nodo de correlaciones con Excel

**Archivo:** `Documentacion/Proceso de Análisis.md`

Las líneas 931–938 (Nodo C: búsqueda de correlaciones con hoja de cálculo de metadatos) se eliminan por completo. Las variables externas no se inyectan en la codificación selectiva. Solo entran las propiedades y dimensiones que emergen de los incidentes.

### ⬜ S08. Eliminar/migrar lógica de `ParadigmState`

**Archivo:** `backend/app/services/selective_elaborator.py`

El `ParadigmState` actual (A1) se conserva como registro histórico, pero su lógica de `did_state_expand: bool` es absorbida por `incident_elaborator.md` que produce una elaboración más rica (no solo bool, sino cómo expande).

---

## 🎨 Visualización: Blobs en Selective Coding

### ⬜ S09. Componente `SelectiveCodingCanvas`

**Archivo:** `frontend/src/components/selective/SelectiveCodingCanvas.tsx` (nuevo)

Versión reducida del EcosystemCanvas para la Fase 5b. Muestra:
- **Blobs más pequeños** (categorías en formación, menos incidentes)
- **Sin tendriles todavía** (las relaciones entre categorías se elaboran en Fase 6b)
- **Blobs que crecen** en tiempo real con cada incidente nuevo
- **Blobs que cambian de color** cuando su definición se expande
- **Blobs que se dividen** (animación de estrangulamiento cuando se sugiere SUBDIVIDE)
- **Blobs que se fusionan** (animación de atracción cuando el sistema detecta intercambiabilidad)
- **Shimmer** cuando se sugiere renombre

**Diferencia clave con el Playground:**
- En Selective Coding, los blobs representan categorías **individuales** evolucionando
- En el Playground, los blobs representan categorías **saturadas** relacionándose
- La física es más simple (no hay tendriles, solo atracción entre blobs intercambiables)

### ⬜ S10. Panel de evolución de categoría

**Archivo:** `frontend/src/components/selective/CategoryEvolutionPanel.tsx` (nuevo)

Al hacer clic en un blob durante selective coding:
- Timeline de versiones de definición
- Propiedades acumuladas (con indicador de cuál incidente añadió cada una)
- Gráfico de crecimiento (incidentes vs. tiempo)
- Sugerencia de renombre (si aplica)
- Botones HITL: "Expandir definición", "Aceptar renombre", "Subdividir", "Fusionar con..."

---

## 📊 Resumen de tareas de Selective Coding

| # | Tarea | Archivos | Dificultad |
|---|-------|----------|------------|
| S01 | Columna parent_category_id en Categoria | `category.py` | 🟢 TRIVIAL |
| S02 | Reutilizar category_definition_versions | `theory.py` (ya creado en T02) | 🟢 TRIVIAL |
| S03 | Migración 009b | `migrations/versions/009b_*.py` | 🟢 TRIVIAL |
| S04 | Prompt incident_elaborator | `deepseek_pro/incident_elaborator.md` | 🟠 ALTO |
| S05 | Servicio selective_elaborator | `services/selective_elaborator.py` | 🟠 ALTO |
| S06 | Eliminar 4 nodos paralelos (documentación) | `Proceso de Análisis.md` | 🟢 TRIVIAL |
| S07 | Eliminar nodo correlaciones Excel (documentación) | `Proceso de Análisis.md` | 🟢 TRIVIAL |
| S08 | Migrar lógica ParadigmState | `selective_elaborator.py` | 🟡 MEDIO |
| S09 | Componente SelectiveCodingCanvas | `components/selective/SelectiveCodingCanvas.tsx` | 🟠 ALTO |
| S10 | Panel CategoryEvolutionPanel | `components/selective/CategoryEvolutionPanel.tsx` | 🟡 MEDIO |

**Total Selective Coding: 10 tareas adicionales.**

**Gran total del plan: 38 tareas (28 Playground + 10 Selective Coding).**

---

# 🧪 THEORETICAL PLAYGROUND — Fase 6b (NUEVO)

> **Paradigma:** Elaboración conceptual, no testeo de hipótesis.
> **Metáfora visual:** Ecosistema de manchas orgánicas (blobs) con física simulada.
> **Principio rector:** Las categorías cambian de nombre cuando su definición se expande. Las relaciones no se "testean" — se elaboran, se densifican, se expanden con datos divergentes.
> **HITL:** El investigador arrastra, conecta, expande y renombra. El sistema sugiere, muestra evidencia convergente/divergente, y recomienda.

---

## 📋 Descripción general del Playground

El **Theoretical Playground** es un espacio interactivo donde el investigador construye la integración teórica de las categorías saturadas. Reemplaza las iteraciones automáticas por familias de la Fase 6b actual por un **ecosistema conceptual vivo**:

- **Blobs** = categorías. Tamaño = incidentes acumulados. Color = capa teórica. Textura = densidad conceptual.
- **Tendriles** = relaciones elaboradas. Grosor = evidencia convergente. Fisuras = datos divergentes.
- **Ghost-blobs** = hipótesis de memos no conectadas. Se arrastran hacia blobs para densificarlos.
- **Neblina** = zonas de gap conceptual donde el sistema recomienda muestreo.
- **Shimmer** = sugerencia de renombre cuando la definición supera al nombre.

El investigador no "testea" relaciones — **elabora** conexiones conceptuales. Cuando un dato diverge, no se descarta la relación: se expande para acomodar la complejidad.

---

## 🗄️ FASE 1 — Modelos de datos y migraciones

### ⬜ T01. Tabla `theoretical_codes`

**Archivo:** `backend/app/models/domain/theory.py` (nuevo)

Registro de códigos teóricos (built-in + user-defined). Cada código tiene su lógica de evaluación visible y modificable.

```python
class TheoreticalCode(Base, TimestampMixin):
    __tablename__ = "theoretical_codes"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), nullable=True)
    # NULL = built-in (global). NOT NULL = user-defined para un proyecto.
    
    name: Mapped[str] = mapped_column(String(200))           # "Proceso / Secuencia"
    family: Mapped[str] = mapped_column(String(100))         # "process", "causal", "typology"
    description: Mapped[str] = mapped_column(Text)           # Qué evalúa
    glaserian: Mapped[bool] = mapped_column(Boolean, default=False)
    user_defined: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Lógica de evaluación (visible para el usuario)
    evaluation_logic: Mapped[dict] = mapped_column(JSONB)
    # {what_it_tests, how_it_tests: [...], evidence_thresholds: {...}, what_it_cannot_test: [...]}
    
    output_schema: Mapped[dict] = mapped_column(JSONB, default=dict)
    compatible_with: Mapped[list] = mapped_column(JSONB, default=list)  # IDs de otros códigos
    layer: Mapped[str] = mapped_column(String(50))
    # "process" | "conditions" | "variation" | "structure" | "consequences" | "action" | "fusion"
    
    visualization_hint: Mapped[str] = mapped_column(String(50), default="tendril")
    # "tendril" | "arrow" | "matrix" | "cluster"
```

### ⬜ T02. Tabla `category_definition_versions`

**Archivo:** `backend/app/models/domain/theory.py`

Historial completo de cambios de definición de cada categoría. Alimenta el detector de necesidad de renombre.

```python
class CategoryDefinitionVersion(Base, TimestampMixin):
    __tablename__ = "category_definition_versions"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categorias.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    version: Mapped[int] = mapped_column(Integer)
    
    name_at_version: Mapped[str] = mapped_column(String(200))
    definition_at_version: Mapped[str] = mapped_column(Text)
    properties_at_version: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {property_name: {gradient, evidence_doc_count}}
    incident_count_at_version: Mapped[int] = mapped_column(Integer)
    
    # ¿Qué disparó esta nueva versión?
    trigger: Mapped[str] = mapped_column(String(50))
    # "manual_edit" | "ghost_absorbed" | "relationship_elaborated" | "rename_applied"
    trigger_detail: Mapped[str] = mapped_column(Text, nullable=True)
    # Ej: "Memo H31 absorbido: añadió propiedad 'Intensidad del análisis'"
```

### ⬜ T03. Tabla `conceptual_relationships`

**Archivo:** `backend/app/models/domain/theory.py`

Relaciones elaboradas entre categorías. NO son "tests" — son elaboraciones conceptuales con evidencia convergente y divergente.

```python
class ConceptualRelationship(Base, TimestampMixin):
    __tablename__ = "conceptual_relationships"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    
    # Categorías conectadas
    category_ids: Mapped[list] = mapped_column(JSONB)  # [uuid_cat_a, uuid_cat_b]
    
    # Código teórico usado para elaborar esta relación
    theoretical_code_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("theoretical_codes.id"))
    
    # Pregunta del investigador que originó la elaboración
    researcher_question: Mapped[str] = mapped_column(Text)
    
    # Estado de elaboración
    elaboration_status: Mapped[str] = mapped_column(String(50), default="emerging")
    # "emerging" | "densifying" | "stable" | "tense" (datos divergentes sin resolver) | "expanded"
    direction: Mapped[str] = mapped_column(String(100), nullable=True)
    # "A_precedes_B" | "A_causes_B" | "A_opposes_B" | "A_conditions_B" | ...
    
    # Evidencia convergente (apoya la relación)
    converging_incident_ids: Mapped[list] = mapped_column(JSONB, default=list)
    converging_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Evidencia divergente (tensa la relación — NO la rompe, la expande)
    diverging_incident_ids: Mapped[list] = mapped_column(JSONB, default=list)
    diverging_doc_count: Mapped[int] = mapped_column(Integer, default=0)
    divergence_resolution: Mapped[str] = mapped_column(Text, nullable=True)
    # Cómo se expandió la relación para acomodar el dato divergente
    
    # Trazabilidad
    origin_memo_ids: Mapped[list] = mapped_column(JSONB, default=list)
    origin_hypothesis_ids: Mapped[list] = mapped_column(JSONB, default=list)
    
    # Métricas de ajuste conceptual
    conceptual_fit: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0 a 1.0
    # Calculado como: (converging_docs - diverging_docs * penalty) / total_docs
    
    layer: Mapped[str] = mapped_column(String(50))  # heredado del theoretical_code
    
    # Visualización
    position_tension: Mapped[float] = mapped_column(Float, default=0.0)
    # >0 = divergencia activa (el tendril muestra fisuras)
```

### ⬜ T04. Tabla `elaboration_memos`

**Archivo:** `backend/app/models/domain/theory.py`

Registro de cada iteración de elaboración (equivalente a los "memos de clasificación" de Glaser).

```python
class ElaborationMemo(Base, TimestampMixin):
    __tablename__ = "elaboration_memos"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    
    # ¿Qué se elaboró?
    elaboration_type: Mapped[str] = mapped_column(String(50))
    # "relationship_proposed" | "divergence_expanded" | "ghost_absorbed" | 
    # "rename_applied" | "definition_expanded" | "sampling_recommended"
    
    # Referencias
    relationship_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conceptual_relationships.id"), nullable=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categorias.id"), nullable=True)
    memo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("memos.id"), nullable=True)
    
    # Contenido
    content: Mapped[str] = mapped_column(Text)
    # Narrativa libre: qué insight apareció, qué sorprendió, qué preguntas quedan
    
    # Estado del ecosistema en este momento (snapshot para reconstrucción)
    ecosystem_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {blob_positions: {...}, tendril_states: {...}, ghost_positions: {...}}
```

### ⬜ T05. Tabla `ecosystem_layouts`

**Archivo:** `backend/app/models/domain/theory.py`

Guarda las posiciones y estados visuales del ecosistema para persistencia entre sesiones.

```python
class EcosystemLayout(Base, TimestampMixin):
    __tablename__ = "ecosystem_layouts"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"), unique=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    
    # Posiciones de blobs (categorías)
    blob_positions: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {category_id: {x: float, y: float, radius: float, color_phase: float}}
    
    # Estados de ghost-blobs
    ghost_positions: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {memo_id: {x: float, y: float, absorbed_by: category_id | null}}
    
    # Zonas de neblina (gaps)
    fog_zones: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {zone_id: {x, y, radius, label, suggested_sampling}}
    
    # Parámetros de la simulación física
    physics_params: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {attraction_strength: 0.01, repulsion: 0.05, damping: 0.95, core_gravity: 0.005}
```

### ⬜ T06. Migración 010

**Archivo:** `backend/migrations/versions/010_theoretical_playground.py` (nuevo)

Crear las 5 tablas. Depende de: `categorias`, `proyectos`, `memos`, `hypotheses`.

---

## 🧠 FASE 2 — Prompts del Playground

### ⬜ T07. Prompt: `conceptual_elaborator.md`

**Archivo:** `backend/app/prompts/deepseek_pro/conceptual_elaborator.md` (nuevo)
**Tier:** PRO

Evalúa la relación conceptual entre 2+ categorías usando un código teórico específico. Busca evidencia convergente y divergente. NO "testea" — elabora.

```yaml
---
agent: conceptual_elaborator
tier: PRO
description: Evalúa la relación conceptual entre categorías usando un código teórico. Busca evidencia convergente (apoya la relación) y divergente (la expande). NO emite veredictos absolutos.
notes:
  - La evidencia divergente NO rompe la relación. Sugiere cómo expandirla.
  - El output incluye "divergence_expansion_suggestions" — cómo acomodar el dato divergente.
  - Usa solo los incidentes proporcionados.
constraints:
  - No uses "aceptar/rechazar". Usa "converge/diverge/expande".
  - Cada incidente citado debe ser trazable.
  - Si no hay suficiente evidencia, indícalo. No inventes.
---

## System

[ROL]
Eres un metodólogo en Classic Grounded Theory especializado en ELABORACIÓN CONCEPTUAL.
NO eres un verificador de hipótesis. Tu tarea es explorar cómo dos o más categorías
se relacionan conceptualmente, usando un código teórico como lente.

[PRINCIPIO FUNDAMENTAL]
En CGT con poblaciones pequeñas no se "testean" hipótesis para verificar verdad absoluta.
Se ELABORAN relaciones conceptuales:
- La evidencia convergente (datos que apoyan la relación) la DENSIFICA.
- La evidencia divergente (datos que no encajan) la EXPANDE — no la rompe.
- Una relación con datos divergentes es MÁS RICA que una sin ellos, si los divergentes
  se acomodan en una expansión del concepto.

[MÉTODO]
1. Recupera todos los incidentes de las categorías involucradas.
2. Identifica documentos que contienen AMBAS categorías.
3. Para cada documento compartido, evalúa si los incidentes CONVERGEN (apoyan la relación)
   o DIVERGEN (la tensan).
4. Para la evidencia convergente: cita incidentes exactos.
5. Para la evidencia divergente: NO la descartes. Propón cómo EXPANDIR la relación para
   acomodarla (condición, subtipo, contexto, ruta alternativa).
6. Evalúa el AJUSTE CONCEPTUAL (conceptual_fit): qué tan bien explica esta relación
   el comportamiento de los participantes.

[QUÉ SIGNIFICA "EXPANDIR" UNA RELACIÓN CON DATO DIVERGENTE]
Ejemplo: Relación "A precede a B". Un incidente muestra B antes que A.
- ❌ INCORRECTO: "La relación es falsa. Descartar."
- ✅ CORRECTO: "La secuencia A→B es el patrón principal, pero existe una ruta
  alternativa B→A que ocurre bajo la condición X. Esto EXPANDE la relación:
  ahora es 'A precede a B, excepto bajo condición X donde la secuencia se invierte'."

Usa solo los incidentes proporcionados.
{lens_instruction}

## User

[CATEGORÍAS INVOLUCRADAS]
{categories_with_incidents}

[CÓDIGO TEÓRICO APLICADO]
Nombre: {theoretical_code_name}
Lógica de evaluación: {evaluation_logic}

[RELACIÓN PROPUESTA POR EL INVESTIGADOR]
"{researcher_question}"

[MEMOS RELACIONADOS]
{related_memos}

## Output Schema

```json
{{
  "type": "object",
  "additionalProperties": false,
  "required": ["relationship_summary", "converging_evidence", "diverging_evidence", "conceptual_fit"],
  "properties": {{
    "relationship_summary": {{
      "type": "string",
      "description": "Descripción narrativa de la relación encontrada. En presente. Nivel teórico."
    }},
    "converging_evidence": {{
      "type": "array",
      "description": "Incidentes que APOYAN la relación (convergen).",
      "items": {{
        "type": "object",
        "required": ["incident_id", "document_name", "exact_quote", "how_it_converges"],
        "properties": {{
          "incident_id": {{"type": "string"}},
          "document_name": {{"type": "string"}},
          "exact_quote": {{"type": "string", "description": "Cita textual exacta del incidente."}},
          "how_it_converges": {{"type": "string", "description": "Cómo este incidente apoya la relación."}}
        }}
      }}
    }},
    "diverging_evidence": {{
      "type": "array",
      "description": "Incidentes que TENSAN la relación (divergen). NO son refutaciones — son oportunidades de expansión.",
      "items": {{
        "type": "object",
        "required": ["incident_id", "document_name", "exact_quote", "how_it_diverges", "expansion_suggestion"],
        "properties": {{
          "incident_id": {{"type": "string"}},
          "document_name": {{"type": "string"}},
          "exact_quote": {{"type": "string"}},
          "how_it_diverges": {{"type": "string", "description": "En qué sentido este incidente no encaja en la relación."}},
          "expansion_suggestion": {{"type": "string", "description": "Cómo expandir la relación para acomodar este dato divergente (condición, subtipo, contexto, ruta alternativa)."}}
        }}
      }}
    }},
    "shared_documents_without_clear_evidence": {{
      "type": "array",
      "items": {{"type": "string"}},
      "description": "Documentos que contienen ambas categorías pero sin evidencia clara a favor ni en contra."
    }},
    "conceptual_fit": {{
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Qué tan bien explica esta relación el comportamiento de los participantes. 0=no explica nada, 1=explica perfectamente."
    }},
    "elaboration_note": {{
      "type": "string",
      "description": "Nota de elaboración libre: ¿qué insight apareció? ¿Qué queda por explorar? ¿Qué preguntas abre esto?"
    }},
    "suggested_next_elaborations": {{
      "type": "array",
      "items": {{"type": "string"}},
      "description": "Sugerencias de próximas relaciones a elaborar, basadas en lo descubierto aquí."
    }}
  }}
}}
```
```

### ⬜ T08. Prompt: `rename_suggester.md`

**Archivo:** `backend/app/prompts/deepseek_pro/rename_suggester.md` (nuevo)
**Tier:** PRO

Sugiere renombres cuando la definición de una categoría ha crecido significativamente. Genera nombres a distintos niveles de abstracción.

```yaml
---
agent: rename_suggester
tier: PRO
description: Sugiere renombres para una categoría cuya definición se ha expandido significativamente. Prioriza gerundios, mayor abstracción, y anclaje en los datos.
notes:
  - Solo se activa cuando el detector algorítmico (rename_detector.py) determina que es necesario.
  - Genera nombres a 3 niveles de abstracción: conservador, moderado, transformador.
  - Cada sugerencia incluye justificación de qué gana respecto al nombre actual.
constraints:
  - No sugieras nombres si el nombre actual es adecuado.
  - Usa gerundios cuando sea posible.
  - El nuevo nombre debe ser más abstracto pero anclado en los datos.
  - Si hay metáforas in-vivo en los incidentes, considéralas.
---
```

### ⬜ T09. Prompt: `ghost_blob_mapper.md`

**Archivo:** `backend/app/prompts/deepseek_pro/ghost_blob_mapper.md` (nuevo)
**Tier:** PRO

Para cada memo de hipótesis no conectado, determina qué categoría(s) existente(s) podría densificar y qué propiedad/dimensión añadiría.

```yaml
---
agent: ghost_blob_mapper
tier: PRO
description: Mapea hipótesis de memos no conectadas a categorías existentes que podrían densificar. Evalúa qué propiedad, dimensión o variante añadiría el memo.
notes:
  - Un memo puede mapear a MÚLTIPLES categorías (una primaria y secundarias).
  - Si un memo no encaja en ninguna categoría existente, puede sugerir crear una nueva.
  - Si un memo ya fue absorbido, se omite.
constraints:
  - No fuerces mapeos donde no hay ajuste conceptual.
  - Cada mapeo debe especificar QUÉ añadiría el memo a la categoría.
---
```

### ⬜ T10. Prompt: `ecosystem_gap_detector.md`

**Archivo:** `backend/app/prompts/deepseek_pro/ecosystem_gap_detector.md` (nuevo)
**Tier:** PRO

Analiza el ecosistema completo y detecta: categorías huérfanas, capas teóricas no cubiertas, zonas de baja densidad conceptual, y sugiere muestreo teórico dirigido.

---

## ⚙️ FASE 3 — Servicios core (Python)

### ⬜ T11. `rename_detector.py`

**Archivo:** `backend/app/services/rename_detector.py` (nuevo)

Detecta cuándo una categoría es candidata a renombre. Combina lógica algorítmica (thresholds) + LLM (generación de nombres).

```python
def should_suggest_rename(category_id: UUID, session: Session) -> bool:
    """
    Una categoría es candidata a renombre cuando:
    - Su definición tiene ≥ 3 versiones O
    - Las propiedades crecieron ≥ 2x desde la versión 1 O
    - Los incidentes crecieron ≥ 3x desde la versión 1 O
    - Hay drift semántico significativo (embedding del nombre vs embedding de la definición > threshold)
    """
    versions = get_definition_versions(category_id, session)
    if len(versions) < 3:
        return False
    
    first = versions[0]
    current = get_current_category(category_id, session)
    
    property_growth = len(current.properties) / max(len(first.properties_at_version), 1)
    incident_growth = current.incident_count / max(first.incident_count_at_version, 1)
    
    # Semantic drift (opcional, usa bi-encoder cache)
    name_embedding = embed(first.name_at_version)
    definition_embedding = embed(current.definicion)
    semantic_drift = cosine_distance(name_embedding, definition_embedding)
    
    return (
        property_growth >= 2.0 or
        incident_growth >= 3.0 or
        semantic_drift > 0.4
    )

def generate_rename_suggestions(category_id: UUID, session: Session) -> list[dict]:
    """
    Genera 3-5 nombres alternativos usando el prompt rename_suggester.
    Retorna: [{name, abstraction_level, rationale, what_it_gains}]
    """
```

### ⬜ T12. `elaboration_engine.py`

**Archivo:** `backend/app/services/elaboration_engine.py` (nuevo)

Motor principal de elaboración conceptual. Orquesta el ciclo completo.

```python
class ElaborationEngine:
    def elaborate_relationship(
        project_id: UUID,
        category_ids: list[UUID],
        theoretical_code_id: UUID,
        researcher_question: str,
        session: Session
    ) -> ConceptualRelationship:
        """
        1. Carga categorías con todos sus incidentes
        2. Carga el código teórico con su evaluation_logic
        3. Invoca al LLM (conceptual_elaborator.md)
        4. Procesa la respuesta: extrae evidencia convergente/divergente
        5. Crea ConceptualRelationship
        6. Crea ElaborationMemo
        7. Si hay evidencia divergente con expansion_suggestion:
           - Sugiere expandir definiciones de categorías involucradas
           - Sugiere crear condiciones/subtipos
        8. Actualiza ecosystem_layout (nueva relación = nuevo tendril)
        9. Dispara recomendaciones (invalida cache de recommendations)
        """
    
    def elaborate_divergence(
        relationship_id: UUID,
        divergence_resolution: str,  # Cómo el investigador decide expandir la relación
        session: Session
    ) -> ConceptualRelationship:
        """
        Cuando el investigador hace clic en una fisura de tendril y elige
        cómo expandir la relación para acomodar el dato divergente.
        """
    
    def absorb_ghost_blob(
        memo_id: UUID,
        target_category_id: UUID,
        session: Session
    ) -> Category:
        """
        Cuando el investigador arrastra un ghost-blob hacia un blob:
        1. Evalúa qué propiedad/dimensión añade el memo a la categoría
        2. Expande la definición de la categoría
        3. Crea CategoryDefinitionVersion (nueva)
        4. Verifica si ahora corresponde sugerir renombre
        5. Crea ElaborationMemo (tipo: ghost_absorbed)
        """
```

### ⬜ T13. `recommendation_engine.py`

**Archivo:** `backend/app/services/recommendation_engine.py` (nuevo)

Genera la "Guía de Elaboración" — sugerencias rankeadas por impacto.

```python
class RecommendationEngine:
    def generate_recommendations(project_id: UUID, session: Session) -> list[Recommendation]:
        """
        Evalúa 5 dimensiones:
        1. CONEXIONES SUGERIDAS: pares de categorías con alta co-ocurrencia en docs
           pero sin relación elaborada aún.
        2. GHOST-BLOBS SIN ABSORBER: memos de hipótesis no mapeados a categorías.
        3. RENOMBRES SUGERIDOS: categorías cuyo detector indica necesidad de renombre.
        4. ZONAS DE NEBLINA: gaps conceptuales (capas no cubiertas, categorías huérfanas).
        5. TENDRILES CON TENSIÓN: relaciones con evidencia divergente sin resolver.
        
        Rankea por impacto estimado:
        - Categorías conectadas (30%)
        - Capa teórica cubierta (25%)
        - Evidencia disponible (20%)
        - Memos respaldan (15%)
        - Centralidad al core (10%)
        """
```

---

## 🔌 FASE 4 — API Endpoints

### ⬜ T14. Theoretical Codes API

**Archivo:** `backend/app/api/v1/theoretical_codes.py` (nuevo)

```
GET    /api/v1/projects/{pid}/theoretical/codes
       → Lista códigos built-in + user-defined

POST   /api/v1/projects/{pid}/theoretical/codes
       → Crear código teórico user-defined

PUT    /api/v1/projects/{pid}/theoretical/codes/{tcid}
       → Modificar código user-defined (incluyendo evaluation_logic)

GET    /api/v1/projects/{pid}/theoretical/codes/{tcid}
       → Ver código con su lógica de evaluación completa
```

### ⬜ T15. Elaboration API

**Archivo:** `backend/app/api/v1/elaboration.py` (nuevo)

```
POST   /api/v1/projects/{pid}/elaboration/relationships
       → Iniciar elaboración de una relación
       Body: {category_ids, theoretical_code_id, researcher_question}
       Response: ConceptualRelationship con evidencia convergente/divergente

PUT    /api/v1/projects/{pid}/elaboration/relationships/{rid}/diverge
       → Expandir relación con dato divergente
       Body: {divergence_resolution, affected_incident_ids}

GET    /api/v1/projects/{pid}/elaboration/relationships
       → Listar todas las relaciones elaboradas

GET    /api/v1/projects/{pid}/elaboration/relationships/{rid}
       → Ver relación con trazabilidad completa a incidentes

POST   /api/v1/projects/{pid}/elaboration/ghosts/{memo_id}/absorb
       → Absorber ghost-blob en categoría
       Body: {target_category_id}

GET    /api/v1/projects/{pid}/elaboration/ghosts
       → Listar ghost-blobs pendientes
```

### ⬜ T16. Rename API

**Archivo:** `backend/app/api/v1/elaboration.py` (misma)

```
GET    /api/v1/projects/{pid}/elaboration/rename-suggestions/{category_id}
       → Ver si la categoría necesita renombre y sugerencias

POST   /api/v1/projects/{pid}/elaboration/rename
       → Aplicar renombre
       Body: {category_id, new_name, rationale}
       → Crea CategoryDefinitionVersion con trigger="rename_applied"

GET    /api/v1/projects/{pid}/elaboration/categories/{cid}/definition-history
       → Historial completo de definiciones (timeline de evolución)
```

### ⬜ T17. Ecosystem & Recommendations API

**Archivo:** `backend/app/api/v1/elaboration.py` (misma)

```
GET    /api/v1/projects/{pid}/elaboration/ecosystem
       → Estado completo del ecosistema (blobs, tendriles, ghosts, fog)

PUT    /api/v1/projects/{pid}/elaboration/ecosystem/layout
       → Guardar posiciones (el frontend persiste tras drag)

GET    /api/v1/projects/{pid}/elaboration/recommendations
       → Guía de elaboración (sugerencias rankeadas)

GET    /api/v1/projects/{pid}/elaboration/model
       → Grafo completo de relaciones + gaps + cobertura de capas

POST   /api/v1/projects/{pid}/elaboration/synthesize
       → Síntesis final: narrativa teórica integrada + esquema de capítulos
```

### ⬜ T18. Registrar rutas en main.py

**Archivo:** `backend/app/main.py`

Añadir:
```python
from app.api.v1 import theoretical_codes, elaboration
app.include_router(theoretical_codes.router, prefix="/api/v1", tags=["theoretical-codes"])
app.include_router(elaboration.router, prefix="/api/v1", tags=["elaboration"])
```

---

## 🎨 FASE 5 — Frontend: EcosystemCanvas

### ⬜ T19. Componente `EcosystemCanvas`

**Archivo:** `frontend/src/components/theory/EcosystemCanvas.tsx` (nuevo)

Lienzo interactivo con física simulada. Implementa:
- Renderizado de blobs (SVG/Canvas con gradientes radiales)
- Física de atracción/repulsión (d3-force o Matter.js)
- Drag & drop de blobs (arrastrar juntos = proponer relación)
- Zoom y paneo
- Renderizado de tendriles (líneas Bezier con grosor variable)
- Renderizado de fisuras (líneas quebradas luminosas sobre tendriles)
- Renderizado de ghost-blobs (translúcidos, borde difuso)
- Renderizado de neblina (overlay semitransparente)
- Shimmer animation (CSS keyframes en blobs con rename pendiente)
- Pulso de respiración (expansión/contracción sutil)

**Estados visuales por blob:**

```typescript
interface BlobVisualState {
  size: 'S' | 'M' | 'L' | 'XL';        // incidentes
  opacity: number;                       // saturación
  color: string;                         // capa teórica
  texture: 'smooth' | 'rough' | 'dense'; // densidad conceptual
  border: 'solid' | 'dotted' | 'pulsing' | 'shimmer';
  isCore: boolean;
}
```

### ⬜ T20. Subcomponentes visuales

**Archivos:**
- `frontend/src/components/theory/CategoryBlob.tsx`
- `frontend/src/components/theory/RelationshipTendril.tsx`
- `frontend/src/components/theory/GhostBlob.tsx`
- `frontend/src/components/theory/FogZone.tsx`
- `frontend/src/components/theory/BlobTooltip.tsx` (hover: nombre + definición resumida)

### ⬜ T21. Panel de elaboración (derecha)

**Archivo:** `frontend/src/components/theory/ElaborationPanel.tsx` (nuevo)

Panel lateral que se abre al seleccionar un blob o tendril:
- **Blob seleccionado:** definición, propiedades, historial de versiones, incidentes, sugerencia de renombre
- **Tendril seleccionado:** evidencia convergente, divergente, theoretical code usado, pregunta original
- **Al hacer clic en fisura:** opciones para expandir la relación

### ⬜ T22. Modal de renombre

**Archivo:** `frontend/src/components/theory/RenameModal.tsx` (nuevo)

Muestra nombres sugeridos a 3 niveles de abstracción. Permite elegir uno o escribir nombre propio. Preview animation: el blob cambia de color gradualmente.

### ⬜ T23. Panel de recomendaciones (izquierda)

**Archivo:** `frontend/src/components/theory/RecommendationGuide.tsx` (nuevo)

Lista colapsable de sugerencias rankeadas. Cada ítem tiene botón "Elaborar" que inicia la acción correspondiente (arrastrar blobs, mostrar ghost, abrir rename modal, etc.).

### ⬜ T24. Integración en la navegación

**Archivo:** `frontend/src/App.tsx` o router

Añadir ruta `/projects/:pid/theory` que carga el EcosystemCanvas con los datos del ecosistema.

---

## 🔗 FASE 6 — Integración con el pipeline existente

### ⬜ T25. Cablear entrada al Playground desde Fase 5b

**Archivo:** `backend/workers/heavy/tasks.py`

Tras la codificación selectiva (Fase 5b completada):
1. Verificar que existe core category confirmada
2. Verificar que hay categorías con puntaje_relevancia ≥ 4
3. Si ambas condiciones se cumplen → habilitar el Playground (flag en proyecto)
4. Generar ghost-blobs iniciales desde memos de hipótesis no conectados
5. Generar layout inicial del ecosistema (posiciones por similitud de embeddings)
6. Generar recomendaciones iniciales

### ⬜ T26. Conectar Memo_Bank → Ghost-blobs

**Archivo:** `backend/app/services/ghost_connector.py` (nuevo)

Al entrar al Playground:
1. Cargar todos los memos tipo HIPOTESIS que no estén ya referenciados en ninguna ConceptualRelationship
2. Para cada uno, ejecutar ghost_blob_mapper.md
3. Si el memo mapea a ≥ 1 categoría → crear ghost-blob con suggested_target_category
4. Si el memo no mapea a ninguna → ghost-blob huérfano (el investigador decide)

### ⬜ T27. Evento de entrada: transición de fase

**Archivo:** `backend/workers/heavy/tasks.py`

Cuando el investigador confirma la core category (HITL de Fase 5b), se dispara:
```python
def on_selective_coding_complete(project_id: UUID):
    """Prepara el ecosistema para el Theoretical Playground."""
    # 1. Verificar criterios de entrada
    # 2. Inicializar theoretical_codes built-in (si no existen)
    # 3. Generar ghost-blobs
    # 4. Generar layout inicial
    # 5. Generar recomendaciones iniciales
```

### ⬜ T28. Seed de 12 códigos teóricos built-in

**Archivo:** `backend/app/services/theory_seeder.py` (nuevo)

Al inicializar la BD o al crear un proyecto:
- Insertar los 12 códigos teóricos glaserianos (project_id=NULL)
- Cada uno con su `evaluation_logic` completa, `output_schema`, `layer`, `visualization_hint`

---

## 📊 Resumen de tareas

| # | Fase | Tarea | Archivos | Dificultad |
|---|------|-------|----------|------------|
| T01 | 1 | Modelo TheoreticalCode | `theory.py` (nuevo) | 🟡 MEDIO |
| T02 | 1 | Modelo CategoryDefinitionVersion | `theory.py` | 🟡 MEDIO |
| T03 | 1 | Modelo ConceptualRelationship | `theory.py` | 🟡 MEDIO |
| T04 | 1 | Modelo ElaborationMemo | `theory.py` | 🟡 MEDIO |
| T05 | 1 | Modelo EcosystemLayout | `theory.py` | 🟡 MEDIO |
| T06 | 1 | Migración 010 | `migrations/versions/010_*.py` | 🟢 TRIVIAL |
| T07 | 2 | Prompt conceptual_elaborator | `deepseek_pro/conceptual_elaborator.md` | 🟠 ALTO |
| T08 | 2 | Prompt rename_suggester | `deepseek_pro/rename_suggester.md` | 🟡 MEDIO |
| T09 | 2 | Prompt ghost_blob_mapper | `deepseek_pro/ghost_blob_mapper.md` | 🟡 MEDIO |
| T10 | 2 | Prompt ecosystem_gap_detector | `deepseek_pro/ecosystem_gap_detector.md` | 🟡 MEDIO |
| T11 | 3 | Servicio rename_detector | `services/rename_detector.py` | 🟡 MEDIO |
| T12 | 3 | Servicio elaboration_engine | `services/elaboration_engine.py` | 🟠 ALTO |
| T13 | 3 | Servicio recommendation_engine | `services/recommendation_engine.py` | 🟡 MEDIO |
| T14 | 4 | API theoretical_codes | `api/v1/theoretical_codes.py` | 🟢 TRIVIAL |
| T15 | 4 | API elaboration | `api/v1/elaboration.py` | 🟡 MEDIO |
| T16 | 4 | API rename | `api/v1/elaboration.py` | 🟢 TRIVIAL |
| T17 | 4 | API ecosystem + recommendations | `api/v1/elaboration.py` | 🟡 MEDIO |
| T18 | 4 | Registrar rutas | `main.py` | 🟢 TRIVIAL |
| T19 | 5 | EcosystemCanvas | `components/theory/EcosystemCanvas.tsx` | 🟠 ALTO |
| T20 | 5 | Subcomponentes visuales (5) | `components/theory/*.tsx` | 🟡 MEDIO |
| T21 | 5 | ElaborationPanel | `components/theory/ElaborationPanel.tsx` | 🟡 MEDIO |
| T22 | 5 | RenameModal | `components/theory/RenameModal.tsx` | 🟡 MEDIO |
| T23 | 5 | RecommendationGuide | `components/theory/RecommendationGuide.tsx` | 🟡 MEDIO |
| T24 | 5 | Ruta en App | `App.tsx` o router | 🟢 TRIVIAL |
| T25 | 6 | Entrada desde Fase 5b | `tasks.py` | 🟡 MEDIO |
| T26 | 6 | Memo_Bank → Ghost-blobs | `services/ghost_connector.py` | 🟡 MEDIO |
| T27 | 6 | Evento de transición | `tasks.py` | 🟡 MEDIO |
| T28 | 6 | Seed 12 built-in codes | `services/theory_seeder.py` | 🟢 TRIVIAL |

**Total: 28 tareas.**

**Distribución por dificultad:**
- 🟢 TRIVIAL: 7 (T06, T14, T16, T18, T24, T28)
- 🟡 MEDIO: 18
- 🟠 ALTO: 4 (T07, T12, T19)

**Orden de ejecución recomendado:**
1. T01–T06 (modelos + migración) → base de datos
2. T28 (seed built-in codes) → datos de referencia
3. T07–T10 (prompts) → cerebro del sistema
4. T11–T13 (servicios) → lógica de negocio
5. T14–T18 (API) → exponer funcionalidad
6. T25–T27 (integración pipeline) → conectar con el flujo existente
7. T19–T24 (frontend) → interfaz visual

---

# 🎯 MUESTREO TEÓRICO POR PROPIEDADES EMERGENTES

> **Diagnóstico corregido:** Las variables del TheoSampler NO son "impuestas". Hay DOS momentos legítimos de emergencia: (1) las variables que emergen **junto con el core concern** durante selective coding — definen quiénes experimentan la preocupación y qué los distingue; (2) las **propiedades de las categorías** que emergen durante theoretical coding — definen cómo se procesa el core concern de maneras diferentes. Ambos tipos son legítimos. Ambos guían el muestreo.
>
> **Principio:** Cuando un eje de comparación (de cualquier momento) está vacío o desbalanceado, el sistema debe **alertar al investigador**, permitir **recolectar nuevos datos**, y **re-procesar el pipeline completo** actualizando categorías, saturación y gaps. Nuestro build actual (LangGraph + PostgresSaver + Celery) lo permite.

---

## Cómo emerge una variable de comparación (el ejemplo del usuario)

```
FASE 1 — Categoría inicial
  Nombre: "Agradeciendo"
  Definición: "Los participantes expresan gratitud hacia quienes les ayudaron"
  Incidentes: 8 casos de gratitud explícita
  
FASE 2 — Llega incidente divergente
  Entrevistado: "No les debo nada. Me usaron y luego me descartaron."
  → incident_elaborator detecta: DIVERGE_STRONG
  → No es "agradecimiento" — es su opuesto
  → PERO resuena con la misma preocupación subyacente (deuda emocional)
  
FASE 3 — Expansión conceptual
  Definición expandida: "Los participantes procesan actitudes cargadas 
  de deuda emocional — gratitud o desprecio — hacia figuras de autoridad"
  → Nueva propiedad: "Valencia actitudinal"
  → Gradiente: gratitud ←→ desprecio
  → rename_suggester activa: "Sintiendo el peso" o "Debiendo actitudes"
  
FASE 4 — Muestreo por la nueva dimensión
  → "Tengo 8 incidentes en polo gratitud y 1 en polo desprecio"
  → Necesito más casos cerca de 'desprecio' para densificar la dimensión
  → Buscar en TODOS los documentos (no solo los ya codificados)
  → Pedir a la IA: 'Revisá las entrevistas. ¿Hay pasajes donde alguien
    exprese desprecio o resentimiento hacia figuras que les ayudaron?'
```

**Lo crucial:** La dimensión "valencia actitudinal" no estaba en ningún Excel. No es un metadato del documento. Es una **propiedad de la categoría** que emergió al comparar incidentes divergentes.

---

## Tareas de Emergent Sampling

### ⬜ E01. Prompt: `property_sampler.md`

**Archivo:** `backend/app/prompts/deepseek_pro/property_sampler.md` (nuevo)
**Tier:** PRO

Reemplaza al TheoSampler actual. En lugar de buscar por `metadatos->>key`, busca **incidentes que manifiesten una propiedad específica de una categoría en un rango específico del gradiente**.

```yaml
---
agent: property_sampler
tier: PRO
description: >
  Muestreo teórico guiado por PROPIEDADES de categorías, no por metadatos
  de documentos. Para una categoría y una propiedad, busca incidentes
  (en documentos ya codificados o no) que manifiesten esa propiedad en
  el extremo solicitado del gradiente.
notes:
  - NO busca por metadata keys. Busca por contenido semántico.
  - Puede buscar en documentos YA codificados (revisar segmentos no asignados
    a esta categoría) o en documentos NUEVOS.
  - Si no encuentra incidentes en el rango buscado, lo reporta como gap
    de muestreo (necesidad de recolectar más datos).
constraints:
  - Usa solo los datos proporcionados.
  - Si no hay evidencia del extremo buscado, dilo: "Sin evidencia en el corpus actual."
  - Sugerir qué tipo de caso se necesitaría recolectar.
---

## System

[ROL]
Eres un especialista en muestreo teórico para Classic Grounded Theory.
Tu tarea es buscar incidentes que DENSIFIQUEN una propiedad específica
 de una categoría, particularmente en los extremos de su gradiente.

[PRINCIPIO]
El muestreo teórico en CGT no busca representatividad estadística.
Busca MAXIMIZAR la variación en las propiedades de las categorías.
Para cada propiedad con un gradiente conocido, necesitamos incidentes
en AMBOS extremos (y puntos intermedios) para densificar el concepto.

[MÉTODO]
1. Recibís: una categoría, una propiedad específica, y el extremo del
   gradiente que necesita más evidencia.
2. Buscás en TODOS los segmentos del corpus (no solo los ya asignados
   a esta categoría) pasajes que manifiesten esa propiedad en ese extremo.
3. Para cada incidente encontrado:
   - Cita exacta
   - ¿Confirma el extremo conocido o lo EXPANDE aún más?
   - ¿Revela algo nuevo sobre esta propiedad?
4. Si no encontrás nada en el corpus actual:
   - Sugerí qué tipo de participante o contexto podría manifestar ese extremo
   - Redactá una pregunta de entrevista para buscarlo

## User

[CATEGORÍA]
Nombre: {category_label}
Definición actual: {category_definition}

[PROPIEDAD A DENSIFICAR]
Nombre: {property_name}
Gradiente actual: {property_gradient}
Extremo que necesita más evidencia: {target_extreme}
Incidentes actuales en este extremo: {current_count}

[CORPUS DISPONIBLE]
{all_segments_summary}

[MEMOS DE MUESTREO RELACIONADOS]
{sampling_memos}

## Output Schema

```json
{{
  "type": "object",
  "additionalProperties": false,
  "required": ["found_incidents", "gradient_expanded"],
  "properties": {{
    "found_incidents": {{
      "type": "array",
      "items": {{
        "type": "object",
        "required": ["segment_id", "document_name", "exact_quote"],
        "properties": {{
          "segment_id": {{"type": "string"}},
          "document_name": {{"type": "string"}},
          "exact_quote": {{"type": "string"}},
          "extreme_manifested": {{
            "type": "string",
            "enum": ["confirms_known_extreme", "expands_extreme_further", "reveals_new_extreme"],
            "description": "¿Este incidente confirma el extremo conocido, lo lleva más lejos, o revela un nuevo extremo?"
          }},
          "elaboration": {{"type": "string", "description": "Cómo este incidente densifica la propiedad."}}
        }}
      }}
    }},
    "gradient_expanded": {{
      "type": "boolean",
      "description": "true si algún incidente expandió el gradiente más allá de lo conocido."
    }},
    "expanded_gradient_description": {{
      "type": "string",
      "description": "Nuevo rango del gradiente si se expandió. String vacío si no."
    }},
    "corpus_gap": {{
      "type": "boolean",
      "description": "true si el corpus actual NO contiene incidentes en el extremo buscado."
    }},
    "sampling_recommendation": {{
      "type": "string",
      "description": "Si corpus_gap=true: qué tipo de caso buscar, qué pregunta hacer. Si false: string vacío."
    }},
    "suggested_interview_question": {{
      "type": "string",
      "description": "Pregunta concreta para una entrevista de muestreo teórico."
    }}
  }}
}}
```
```

### ⬜ E02. Prompt: `corpus_scanner.md`

**Archivo:** `backend/app/prompts/deepseek_flash/corpus_scanner.md` (nuevo)
**Tier:** FLASH

Escaneo rápido de todo el corpus buscando pasajes relacionados con una propiedad emergente. Más ligero que `property_sampler` — solo detecta presencia/ausencia, no elabora.

```yaml
---
agent: corpus_scanner
tier: FLASH
description: Escaneo rápido del corpus para detectar pasajes relacionados con una propiedad de categoría. No elabora — solo reporta presencia/ausencia con citas.
notes:
  - Se ejecuta en lote sobre todos los segmentos.
  - Output ligero: solo segment_id, quote, relevance_score.
  - Alimenta al property_sampler (PRO) que sí elabora.
---
```

### ⬜ E03. Servicio `emergent_sampler.py`

**Archivo:** `backend/app/services/emergent_sampler.py` (nuevo)

Orquesta el muestreo por propiedades emergentes. Reemplaza `task_a06_theoretical_sample`.

```python
class EmergentSampler:
    def sample_for_property_extreme(
        category_id: UUID,
        property_name: str,
        target_extreme: str,  # "high" | "low" | descripción del extremo
        session: Session
    ) -> SamplingResult:
        """
        1. Verifica el gradiente actual de la propiedad
        2. Determina cuántos incidentes hay en cada extremo
        3. Si hay desbalance (ej. 8 en polo A, 1 en polo B):
           a. Primero escanea el corpus existente (corpus_scanner FLASH)
              buscando pasajes no codificados que manifiesten el extremo faltante
           b. Si encuentra → los retorna para que el investigador los codifique
           c. Si no encuentra → activa property_sampler (PRO) para:
              - Confirmar que realmente no hay evidencia
              - Sugerir muestreo externo (qué tipo de caso buscar)
              - Redactar pregunta de entrevista
        4. Retorna los incidentes encontrados + recomendación de muestreo
        """
    
    def detect_emergent_dimensions(
        category_id: UUID,
        session: Session
    ) -> list[EmergentDimension]:
        """
        Analiza las propiedades actuales de la categoría y detecta:
        - Qué propiedades tienen gradientes desbalanceados
        - Qué propiedades son nuevas (pocos incidentes)
        - Qué propiedades sugieren una dimensión subyacente no nombrada aún
        
        Esto es lo que el viejo AI Agent (My workflow 2, nodo 21) hacía:
        derivar variables implícitas desde los criteria de las categorías.
        Pero ahora las variables son PROPIEDADES, no metadata keys.
        """
    
    def suggest_rename_from_dimension_expansion(
        category_id: UUID,
        new_dimension: str,
        session: Session
    ) -> list[str]:
        """
        Cuando una categoría se expande para acomodar un nuevo polo
        (ej. 'agradecimiento' ahora incluye 'desprecio'), sugiere
        nombres que capturen AMBOS polos.
        
        Ej: "Agradeciendo" + nuevo polo "desprecio" → 
            "Sintiendo el peso", "Debiendo actitudes", "Cargando deudas emocionales"
        """
```

### ⬜ E04. Refactor de `task_a06_theoretical_sample`

**Archivo:** `backend/workers/heavy/tasks.py`

La tarea actual se renombra a `task_a06_legacy` (deprecated). Se crea `task_e01_emergent_sample` que usa `EmergentSampler` en lugar de queries SQL por metadata.

```python
@app.task(name="e01_emergent_sample")
def task_e01_emergent_sample(proyecto_id: str, category_id: str, property_name: str, target_extreme: str) -> dict:
    """E01: Muestreo teórico por propiedad emergente de categoría."""
    sampler = EmergentSampler()
    result = sampler.sample_for_property_extreme(
        UUID(category_id), property_name, target_extreme
    )
    return result.to_dict()
```

---

## 📊 Resumen de tareas de Emergent Sampling

| # | Tarea | Archivos | Dificultad |
|---|-------|----------|------------|
| E01 | Prompt property_sampler (PRO) | `deepseek_pro/property_sampler.md` | 🟠 ALTO |
| E02 | Prompt corpus_scanner (FLASH) | `deepseek_flash/corpus_scanner.md` | 🟢 TRIVIAL |
| E03 | Servicio emergent_sampler | `services/emergent_sampler.py` | 🟠 ALTO |
| E04 | Refactor TheoSampler → emergent | `workers/heavy/tasks.py` | 🟡 MEDIO |

**Gran total actualizado: 46 tareas (10 Selective + 8 Emergent Sampling + Feedback + 28 Playground).**

---

## 🔄 FEEDBACK LOOP — De la alerta al re-procesamiento

> **Infraestructura:** LangGraph StateGraph con PostgresSaver permite pausar el grafo en HITL, aceptar nuevos datos, y re-ejecutar nodos afectados. Celery ejecuta las tareas pesadas (ingesta, codificación, saturación).

### Los dos momentos de emergencia de variables

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  MOMENTO 1 — Emergencia del MAIN CONCERN (Fase 5b temprana)     │
│                                                                  │
│  A1 (Population Context) acumula surprising_details:             │
│    "Doc 3: Este periodista-gestor habla de IA distinto a los    │
│     redactores puros. Ve la herramienta como aliada estratégica, │
│     no como amenaza."                                            │
│    "Doc 7: Este freelance reacciona con ansiedad, a diferencia   │
│     de los empleados de plantilla que muestran curiosidad."      │
│                                                                  │
│  A14 (Main Concern Proposer) sintetiza:                          │
│    Main concern: "Manteniendo relevancia profesional ante la IA" │
│    Y SIMULTÁNEAMENTE:                                            │
│    Dimensiones poblacionales relevantes:                         │
│      • ROL_ORGANIZACIONAL (gestor vs. redactor vs. freelance)   │
│      • TAMAÑO_DEL_MEDIO (grande vs. pequeño)                     │
│      • TRAYECTORIA_PROFESIONAL (consolidado vs. emergente)       │
│                                                                  │
│  Estas variables NO venían de un Excel.                          │
│  EMERGIERON de A1 y se cristalizaron en A14.                     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  MOMENTO 2 — Emergencia de PROPIEDADES (Fase 5b-6b)             │
│                                                                  │
│  Al densificar categorías comparando incidentes:                 │
│    Categoría "Integrando estratégicamente"                       │
│    → Propiedad "Profundidad de integración": superficial↔profundo│
│    → Propiedad "Motor": defensivo↔expansivo                      │
│                                                                  │
│  Estas son DIMENSIONES de la categoría.                          │
│  No son variables demográficas. Son propiedades emergentes.      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### El ciclo de detección → alerta → recolección → re-procesamiento

```
                     ┌──────────────────┐
                     │   TheoSampler    │
                     │   Evalúa TODOS   │
                     │   los ejes       │
                     └────────┬─────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Eje A:   │   │ Eje B:   │   │ Eje C:   │
        │ ROL_ORG  │   │ PROFUND. │   │ TAMAÑO   │
        │ manager 8│   │ profundo7│   │ grande 5 │
        │ redactor6│   │ medio  4 │   │ pequeño7│
        │ freelance│   │ superf 0 │   │ startup0│
        │   1 ⚠️   │   │     🔴   │   │    🔴   │
        └────┬─────┘   └────┬─────┘   └────┬─────┘
             │               │               │
             ▼               ▼               ▼
        ┌─────────────────────────────────────────┐
        │         SISTEMA DE ALERTAS              │
        │                                         │
        │  ⚠️ "freelance" tiene solo 1 doc.      │
        │     ¿Hay más freelancers en el corpus?  │
        │                                         │
        │  🔴 "superficial" no tiene incidentes.  │
        │     ¿Existen integraciones superficiales│
        │     de IA en esta población?            │
        │                                         │
        │  🔴 "startup" no tiene documentos.      │
        │     ¿Hay startups en tu población?      │
        │     Si sí, necesitás datos de ellas.    │
        └────────────────┬────────────────────────┘
                         │
                         ▼
        ┌─────────────────────────────────────────┐
        │           HITL: ELECCIÓN                │
        │                                         │
        │  [Buscar en corpus existente]           │
        │  [Cargar nuevos documentos]             │
        │  [Diseñar pregunta de entrevista]       │
        │  [Marcar como limitación del estudio]   │
        └────────────────┬────────────────────────┘
                         │
                         ▼ (si carga nuevos datos)
        ┌─────────────────────────────────────────┐
        │        RE-PROCESAMIENTO                 │
        │                                         │
        │  1. Ingesta + Segmentación (Fase 1-2)   │
        │  2. Open Coding contra categorías       │
        │     existentes (Fase 3-4)               │
        │  3. incident_elaborator: ¿expande       │
        │     alguna categoría?                    │
        │  4. Actualizar saturación               │
        │  5. Reconstruir ejes de comparación     │
        │  6. Volver a TheoSampler → evaluar      │
        │     si los gaps se cerraron             │
        └────────────────┬────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │ ¿Gaps críticos   │
              │ persisten?       │
              └────┬─────────┬───┘
                   │         │
               SÍ  │         │  NO
                   ▼         ▼
           ┌──────────┐  ┌──────────────┐
           │ Volver a  │  │ Continuar    │
           │ alertar   │  │ Theoretical  │
           │ (HITL)    │  │ Playground   │
           └──────────┘  └──────────────┘
```

### Cómo el StateGraph lo implementa

```python
# nodo: theosampler_evaluate
# Evalúa TODOS los ejes (Momento 1 + Momento 2)
def theosampler_evaluate(state: AnalysisState) -> AnalysisState:
    axes = build_comparison_axes(state)
    gaps = []
    
    for axis in axes:
        for value, count in axis["values"].items():
            if count == 0:
                gaps.append({"axis": axis, "value": value, 
                            "severity": "empty", "resolved": False})
            elif count == 1 and axis["axis_type"] == "category_property":
                gaps.append({"axis": axis, "value": value,
                            "severity": "underrepresented", "resolved": False})
    
    state["pending_gaps"] = gaps
    state["comparison_axes"] = axes
    return state

# router: después de evaluar gaps
def after_theosampler(state: AnalysisState) -> str:
    if state["pending_gaps"]:
        return "hitl_gap_review"    # Pausa: el investigador ve alertas
    return "theoretical_playground"  # Sin gaps: avanza al Playground

# nodo: process_new_data
# Cuando el investigador carga nuevos documentos para llenar gaps
def process_new_data(state: AnalysisState) -> AnalysisState:
    new_docs = state["new_documents"]  # Docs cargados por el investigador
    
    for doc in new_docs:
        segments = ingest_and_segment(doc)
        for seg in segments:
            for cat in state["categories"]:
                result = elaborate_incident(cat, seg)
                if result.expanded:
                    update_category(cat, result)
        
        update_saturation(state["project_id"])
    
    # Re-evaluar: ¿los gaps se cerraron?
    return theosampler_evaluate(state)
```

### ⬜ E05. Ampliar A14: output de dimensiones poblacionales

**Archivo:** `backend/app/prompts/deepseek_pro/main_concern_proposer.md`

Añadir al output schema de A14 un nuevo campo `relevant_population_dimensions`:

```json
"relevant_population_dimensions": {
  "type": "array",
  "description": "Dimensiones de la población que parecen relevantes para entender cómo se manifiesta esta preocupación. Derivadas de A1 (surprising_details) y A2 (diferencias entre entrevistados).",
  "items": {
    "type": "object",
    "required": ["dimension_name", "observed_values", "emergence_rationale"],
    "properties": {
      "dimension_name": {"type": "string", "description": "Nombre de la dimensión (ej. 'ROL_ORGANIZACIONAL')."},
      "observed_values": {"type": "array", "items": {"type": "string"}, "description": "Valores observados en los datos hasta ahora."},
      "emergence_rationale": {"type": "string", "description": "Qué observaciones de A1/A2 sugieren que esta dimensión es relevante."},
      "missing_values": {"type": "array", "items": {"type": "string"}, "description": "Valores que podrían existir en la población pero no están en los datos."}
    }
  }
}
```

### ⬜ E06. Prompt de alerta: `gap_alerter.md`

**Archivo:** `backend/app/prompts/deepseek_pro/gap_alerter.md` (nuevo)
**Tier:** PRO

Genera alertas legibles para el investigador cuando un eje de comparación está vacío o desbalanceado.

### ⬜ E07. Nodo del grafo: `hitl_gap_review`

**Archivo:** `backend/app/services/workflow.py`

Nodo del StateGraph que pausa la ejecución con `interrupt()` y presenta al investigador:
- Lista de gaps con severidad (🔴 vacío, ⚠️ subrepresentado)
- Sugerencia de acción para cada uno
- Opciones: buscar en corpus, cargar datos, diseñar pregunta, marcar límite

### ⬜ E08. Nodo del grafo: `process_new_data`

**Archivo:** `backend/app/services/workflow.py`

Nodo del StateGraph que recibe los nuevos documentos cargados, los procesa a través de las Fases 1-5b, y re-evalúa los gaps. Usa Celery para las tareas pesadas.

---

## 📊 Resumen de tareas de Feedback Loop

| # | Tarea | Archivos | Dificultad |
|---|-------|----------|------------|
| E05 | Ampliar A14: output dimensiones poblacionales | `main_concern_proposer.md` | 🟡 MEDIO |
| E06 | Prompt gap_alerter (PRO) | `deepseek_pro/gap_alerter.md` | 🟡 MEDIO |
| E07 | Nodo hitl_gap_review en StateGraph | `services/workflow.py` | 🟠 ALTO |
| E08 | Nodo process_new_data en StateGraph | `services/workflow.py`, `tasks.py` | 🟠 ALTO |

**Gran total final: 46 tareas.**

---

# 🎨 LENGUAJE VISUAL UNIFICADO + INSTRUCCIONES DE IMPLEMENTACIÓN

> **Principio:** Cada atributo visual codifica EXACTAMENTE una dimensión de información. No hay decoración — todo es dato. Cada tipo de tarea (servicio, prompt, modelo, API, frontend, pipeline) tiene un template concreto que la IA debe seguir.

---

## 1. Paleta de colores — Capas teóricas

Cada capa teórica (layer) tiene un color. Blobs y tendriles heredan el color de su capa.

| Capa | HEX | Nombre | Uso |
|------|-----|--------|-----|
| `core` | `#FF6B35` | Naranja fuego | Core category (blob más grande, central, opaco) |
| `process` | `#4ECDC4` | Teal | Secuencias, etapas, flujos |
| `conditions` | `#45B7D1` | Azul cielo | Condiciones estructurales, contingencias |
| `variation` | `#96CEB4` | Verde salvia | Tipologías, oposiciones, gradientes |
| `consequences` | `#DDA0DD` | Lavanda | Consecuencias, resultados, efectos |
| `action` | `#F7DC6F` | Amarillo dorado | Estrategias, respuestas |
| `fusion` | `#D3D3D3` | Gris plata | Intercambiabilidad, fusión |
| `undefined` | `#E8E8E8` | Gris neutro | Sin capa asignada aún |

**Transiciones:** El color se interpola (lerp en HSL) cuando un blob cambia de capa. Duración: 2s con easing `ease-in-out`. Sin saltos.

---

## 2. Especificaciones de Blobs

### Tamaño (radio en px)

| Tamaño | Incidentes | Radio | Opacidad | Significado |
|--------|-----------|-------|----------|-------------|
| **S** | 1–5 | 28–36 | 0.55 | Categoría temprana |
| **M** | 6–15 | 38–50 | 0.70 | En desarrollo |
| **L** | 16–30 | 52–64 | 0.85 | Densa, saturada |
| **XL** | 31+ | 68–80 | 0.95 | Core category (forzado aunque tenga menos incidentes) |

### Textura (densidad conceptual → ruido Perlin)

| Textura | Propiedades | Amplitud ruido |
|---------|------------|----------------|
| `smooth` | 0–2 | 0 |
| `rough` | 3–5 | 0.03 |
| `dense` | 6+ | 0.06 |

### Borde (estado)

| Estado | SVG/CSS | Cuándo |
|--------|---------|--------|
| `solid` | `stroke-width:2; stroke:<color>` | Categoría estable |
| `dotted` | `stroke-dasharray:4 4` | Necesita muestreo (pocos incidentes en algún extremo) |
| `pulsing` | `@keyframes pulse: r ±4px, 2s` | Definición recién expandida (últimos 60s) |
| `shimmer` | `hue-rotate` 0→360 en 4s sobre gradiente radial | Renombre sugerido pendiente |
| `dividing` | Estrangulamiento: dos círculos con `clip-path` | SUBDIVIDE sugerido |

### Respiración

Todos los blobs "respiran": `radius += sin(time * 2.0 + phase) * 2.0`. Fase aleatoria por blob para que no latan sincronizados.

---

## 3. Especificaciones de Tendriles

Curva Bézier cuadrática entre centros de blobs. Punto de control: punto medio + desplazamiento perpendicular (30px * índice para evitar superposición).

```typescript
interface TendrilStyle {
  grosor: number;           // 1–8px, proporcional a log(converging_docs + 1)
  color: string;            // heredado del theoretical_code.layer
  opacidad: number;         // 0.3 (emerging) → 1.0 (stable)
  dashArray: string | null; // "6 4" si emerging, null si estable
  fisuras: Fissure[];       // líneas zigzag doradas si position_tension > 0
  pulso: boolean;           // animación de brillo si evidencia añadida en últimos 30s
}

interface Fissure {
  posicion: number;         // 0.0–1.0 en la curva
  intensidad: number;       // 0.0–1.0 proporcional a diverging_doc_count
  color: string;            // '#FFD700' dorado fijo
  incidentes: UUID[];       // IDs de incidentes divergentes
}
```

**Regla crítica:** Un tendril NUNCA se rompe. La divergencia se muestra como fisura dorada, no como rotura.

---

## 4. Ghost-blobs

| Atributo | Valor |
|----------|-------|
| Opacidad | 0.25 |
| Borde | `stroke-dasharray: 2 6` |
| Tamaño | fijo 20px |
| Label | Visible solo en hover |
| Arrastrable | Sí — hacia un blob (absorber) o hacia espacio vacío (crear categoría) |

---

## 5. Neblina (fog zones)

Overlay semitransparente con gradiente radial. Color: `#FFFFFF` al 10% en centro, 0% en bordes. Label centrado: "Zona de muestreo sugerida" en gris claro.

---

## 6. Física del ecosistema

```python
# Parámetros por defecto (sobrescribibles en ecosystem_layout.physics_params)
DEFAULT_PHYSICS = {
    "attraction_strength": 0.01,   # Fuerza de atracción entre blobs con tendril
    "repulsion": 0.05,             # Fuerza de repulsión para evitar solapamiento
    "damping": 0.95,               # Amortiguación (1 = sin fricción)
    "core_gravity": 0.005,         # Atracción suave de todos los blobs hacia el core
    "min_distance": 80,            # Distancia mínima entre centros (px)
    "max_velocity": 3.0,           # Velocidad máxima (px/frame)
}
```

**Regla:** Los blobs con tendril grueso (relación densificada) se atraen más fuerte: `attraction *= (1 + grosor / 4)`.

---

## 7. Instrucciones de implementación por tipo de tarea

### 📝 Tarea tipo PROMPT

**Objetivo:** Crear un archivo `.md` en `backend/app/prompts/deepseek_pro/` o `deepseek_flash/`.

**Template obligatorio:**
```yaml
---
agent: <id_unico>
tier: PRO | FLASH
description: <una línea>
notes:
  - <nota de implementación>
constraints:
  - <regla anti-alucinación>
---

## System
[ROL] ...
[OBJETIVO] ...
[MÉTODO] ...
[RESTRICCIONES] ...

## User
<variables con {single_braces}>

## Output Schema
```json
{<JSON Schema con additionalProperties: false, max 3 niveles, enum para valores acotados>}
```
```

**Reglas:**
- System: rol + objetivo + restricciones + marco conceptual. NUNCA incluye datos.
- User: solo datos con `{variables}`. NUNCA incluye instrucciones.
- Output Schema: bloque ` ```json ``` ` separado. `additionalProperties: false` en todo objeto. Max 3 niveles de anidamiento. `description` en cada campo. Sin `oneOf`/`anyOf`/`$ref` (DeepSeek no los sigue). Arrays sin `minItems`.
- Constraints del frontmatter: reglas anti-alucinación que se inyectan en el system prompt.

**Variables estándar disponibles:** `{population_assumption}`, `{population_context}`, `{processes}`, `{existing_codes}`, `{existing_hypotheses}`, `{segments}`, `{indicators}`.

### 🐍 Tarea tipo SERVICIO

**Objetivo:** Crear un archivo `.py` en `backend/app/services/`.

**Template:**
```python
"""<descripción del servicio. Qué problema resuelve.>"""
from __future__ import annotations
import logging
from uuid import UUID
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class <ServiceName>:
    """<Docstring de la clase.>"""
    
    def __init__(self, session: Session | None = None):
        self.session = session
    
    def <metodo_principal>(self, ...) -> ...:
        """
        <Qué hace. Qué recibe. Qué devuelve.>
        
        Flujo:
        1. <paso>
        2. <paso>
        """
        # Implementación
```

**Reglas:**
- Usar type hints en TODOS los parámetros y retornos.
- Sesión de BD se recibe por parámetro (no se crea dentro).
- Si el método llama a un LLM, usar `llm_client.run_agent(agent_id, variables={...})`.
- Si el método es pesado, debe ser llamado desde una tarea Celery, no desde la API directamente.
- Logging con `logger.info()` para decisiones importantes, `logger.debug()` para detalles.
- Manejo de errores: `try/except` con `logger.exception()` y re-raise.

### 🗄️ Tarea tipo MODELO

**Objetivo:** Añadir clase(s) en `backend/app/models/domain/<archivo>.py`.

**Template:**
```python
class <ModelName>(Base, TimestampMixin):
    __tablename__ = "<snake_case_table>"
    
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    proyecto_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    
    # ... columnas ...
    
    # Relaciones (solo si son necesarias para queries)
    proyecto = relationship("Proyecto", back_populates="<backref>")
```

**Reglas:**
- Heredar de `Base, TimestampMixin`.
- `proyecto_id` con ForeignKey a `proyectos.id` en toda tabla de dominio.
- JSONB para `dict`/`list` (importar de `sqlalchemy.dialects.postgresql`).
- `nullable=True` por defecto en columnas opcionales. Solo `nullable=False` las requeridas.
- Array de UUIDs: `mapped_column(JSONB, default=list)` (PostgreSQL no tiene `UUID[]` nativo vía SQLAlchemy).
- Si el modelo es nuevo, crear migración en `backend/migrations/versions/`.

### 🔌 Tarea tipo API

**Objetivo:** Crear/editar archivo en `backend/app/api/v1/`.

**Template:**
```python
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_db, get_current_user

router = APIRouter()

@router.get("/projects/{project_id}/<resource>")
async def list_<resource>(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
) -> list[<Schema>]:
    """<descripción>"""
    # Validar acceso al proyecto
    # Ejecutar servicio
    # Retornar
```

**Reglas:**
- Usar `Depends(get_db)` para sesión, `Depends(get_current_user)` para auth.
- Validar que el usuario tiene acceso al proyecto.
- Schemas Pydantic en `backend/app/schemas/` (crear si no existen).
- Endpoints POST/PUT: body con Pydantic model.
- Errores: `HTTPException` con status_code apropiado.

### 🎨 Tarea tipo FRONTEND

**Objetivo:** Crear componente React en `frontend/src/components/`.

**Template:**
```typescript
// <descripción del componente>
import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';

interface <ComponentName>Props {
  // props
}

interface <ComponentName>State {
  // estado interno
}

export const <ComponentName>: React.FC<<ComponentName>Props> = (props) => {
  // hooks
  // efectos
  // render
  return (...);
};
```

**Reglas:**
- TypeScript estricto. Interfaces para props y estado.
- Estilos: CSS modules o styled-components (elegir uno y ser consistente).
- Llamadas API: usar fetch wrapper existente en `frontend/src/api/`.
- Animaciones: CSS `@keyframes` para shimmer, pulso, respiración. No usar librerías externas sin aprobar.
- SVG para blobs y tendriles. Canvas solo si es necesario por performance (>50 blobs).
- Física: `d3-force` para simulación (ya está en `package.json`).
- Estado global: React Context si varios componentes necesitan el ecosistema.

### ⚙️ Tarea tipo PIPELINE

**Objetivo:** Añadir tarea Celery en `workers/heavy/tasks.py` o `workers/fast/tasks.py`.

**Template:**
```python
@app.task(name="<task_name>")
def task_<name>(proyecto_id: str, ...) -> dict:
    """<descripción>"""
    s = SessionLocal()
    try:
        # Lógica
        return {"status": "ok", ...}
    except Exception as e:
        logger.exception("<name> failed for project %s", proyecto_id)
        return {"status": "error", "detail": str(e)}
    finally:
        s.close()
```

**Reglas:**
- `SessionLocal()` se crea y cierra en la tarea.
- Retornar siempre un dict (no objetos ORM — no son serializables por Celery).
- `logger.exception()` para errores.
- Si la tarea llama a un agente LLM, usar timeout y retry.
- Tareas en `workers/heavy/` para PRO, `workers/fast/` para FLASH.

---

## 📊 Gran total final

| Bloque | Tareas |
|--------|--------|
| Pre-Coding Infrastructure | C01–C08 (8) |
| Selective Coding Refactor | S01–S10 (10) |
| Emergent Sampling | E01–E04 (4) |
| Feedback Loop + Alertas | E05–E08 (4) |
| Theoretical Playground | T01–T28 (28) |
| **Total** | **54 tareas** |

**Distribución:**
- 🟢 TRIVIAL: 17
- 🟡 MEDIO: 28
- 🟠 ALTO: 9

**Primeras 5 tareas a ejecutar (orden de dependencias):**
1. T01 — Modelo `theoretical_codes` (base para todo lo demás)
2. S01 — Columna `parent_category_id` en `categorias` (migración simple)
3. T02 — Modelo `category_definition_versions` (referenciado por S04, S05, T11, T12)
4. T03 — Modelo `conceptual_relationships` (referenciado por T12, T15)
5. T06 — Migración 010 (crea las 5 tablas)
