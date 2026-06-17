# CGT Alignment — MemoMaker: Sorting Log Multi-Agente

> **Objetivo:** Implementar un sistema de 3 agentes que, al saturarse una categoría, generen, simplifiquen y correlacionen memos teóricos usando las 12 familias de códigos teóricos de Glaser como configuración compartida del sistema.
>
> **Versión:** 1.0 — 2026-06-16
>
> **Depende de:** `Patron_Desarrollo_Maestro.md` §0.3 (R0.4–R0.10), `kb.md` §8 (Theoretical Coding)
>
> **Archivos afectados:** `workers/heavy/tasks.py`, `prompts/pro/`, `prompts/flash/`, `backend/app/services/theory_seeder.py`

---

## 1. Diagnóstico

### 1.1 El problema

El pipeline actual satura categorías pero **no produce memos**. El `SelectiveElaborator` y `EmergentSampler` operan a nivel de incidentes y paradigm_states, pero cuando una categoría alcanza saturación (3 iteraciones sin `did_state_expand`), el sistema simplemente avanza a la siguiente fase sin documentar **qué aprendió**.

En la Classic Grounded Theory de Glaser, la saturación no es un checkpoint binario — es el momento en que el investigador **escribe un memo teórico** que captura lo que la categoría revela. Este memo luego se usa en el **sorting** (fase 8 del kb.md): se imprime, se desparrama sobre una mesa, y se agrupa usando los 12 lentes teóricos.

### 1.2 Lo que el sistema necesita

| Necesidad | Estado actual | Solución propuesta |
|-----------|---------------|-------------------|
| Memo al saturar | ❌ No existe | `memo_generator` (PRO) |
| Simplificación del memo | ❌ No existe | `memo_simplifier` (PRO) |
| Correlación cross-memo usando las 12 familias | ❌ No existe | `memo_correlator` (FLASH) |
| Las 12 familias como config | ⚠️ Están en `theory_seeder.py` pero no son accesibles como config programática | Extraer a `backend/app/core/theoretical_families.py` |
| Sorting Log | ⚠️ Parcial (ElaborationMemo + RecommendationEngine) | Extender con `memo_sorting_attempts` |

---

## 2. Las 12 familias como configuración compartida

> **Implementación planificada:** Ver `CHECKLIST_CGT_REFACTOR.md` F1.3. El módulo `backend/app/core/theoretical_families.py` será la fuente única de verdad. `theory_seeder.py` importará desde allí en vez de definirlas inline.

### 2.1 Extraer a módulo independiente

Las 12 familias actualmente viven en `backend/app/services/theory_seeder.py` como `BUILT_IN_THEORETICAL_CODES`. Deben extraerse a un módulo de configuración que sea accesible tanto para el seeder (que persiste en DB) como para el MemoMaker (que las usa como lentes de correlación).

**Nuevo archivo:** `backend/app/core/theoretical_families.py`

```python
"""12 familias de códigos teóricos glaserianos — configuración compartida.

Usado por:
- TheorySeeder: persiste en theoretical_codes al iniciar
- MemoMaker (memo_correlator): lentes para correlacionar memos
- RecommendationEngine: sugiere familias para el sorting
- Playground: muestra los 12 lentes en el menú contextual
"""

from __future__ import annotations

THEORETICAL_FAMILIES: list[dict] = [
    {
        "id": "bbbbbbbb-0001-4000-8000-000000000001",
        "name": "Proceso / Secuencia",
        "family": "process",
        "glaserian": True,
        "layer": "process",
        "sorting_label": "¿En qué orden ocurren?",
        "correlation_prompt": "¿Los memos A y B describen etapas de un mismo proceso? ¿Hay una secuencia temporal o lógica entre ellos?",
    },
    {
        "id": "bbbbbbbb-0002-4000-8000-000000000002",
        "name": "Causal / Seis C's",
        "family": "causal",
        "glaserian": True,
        "layer": "causal",
        "sorting_label": "¿Qué causa qué?",
        "correlation_prompt": "¿El memo A causa, produce o desencadena lo que describe el memo B?",
    },
    {
        "id": "bbbbbbbb-0003-4000-8000-000000000003",
        "name": "Oposición / Polaridades",
        "family": "opposition",
        "glaserian": True,
        "layer": "structural",
        "sorting_label": "¿Son polos opuestos?",
        "correlation_prompt": "¿Los memos A y B describen extremos opuestos de una misma dimensión?",
    },
    {
        "id": "bbbbbbbb-0004-4000-8000-000000000004",
        "name": "Tipología / Clasificación",
        "family": "typology",
        "glaserian": True,
        "layer": "structural",
        "sorting_label": "¿Qué tipos emergen?",
        "correlation_prompt": "¿Los memos A y B forman una tipología? ¿Son subtipos de una categoría más amplia?",
    },
    {
        "id": "bbbbbbbb-0005-4000-8000-000000000005",
        "name": "Jerarquía / Centralidad",
        "family": "hierarchy",
        "glaserian": True,
        "layer": "structural",
        "sorting_label": "¿Qué es más central?",
        "correlation_prompt": "¿El memo A es más central/abstracto que el memo B? ¿B es una instancia o componente de A?",
    },
    {
        "id": "bbbbbbbb-0006-4000-8000-000000000006",
        "name": "Matriz 2×2 / Ejes cruzados",
        "family": "matrix",
        "glaserian": True,
        "layer": "structural",
        "sorting_label": "¿Qué dos dimensiones organizan todo?",
        "correlation_prompt": "¿Los memos A y B forman los ejes de una matriz? ¿Al cruzarlos emergen 4 cuadrantes?",
    },
    {
        "id": "bbbbbbbb-0007-4000-8000-000000000007",
        "name": "Consecuencias / Resultados",
        "family": "consequences",
        "glaserian": True,
        "layer": "outcome",
        "sorting_label": "¿Qué produce actuar?",
        "correlation_prompt": "¿El memo B describe el resultado o consecuencia de lo que describe el memo A?",
    },
    {
        "id": "bbbbbbbb-0008-4000-8000-000000000008",
        "name": "Estrategias / Tácticas",
        "family": "strategy",
        "glaserian": True,
        "layer": "action",
        "sorting_label": "¿Qué estrategias comparten?",
        "correlation_prompt": "¿El memo A describe cómo los actores manejan o resuelven lo que describe el memo B? ¿Es una estrategia para procesar el main concern?",
    },
    {
        "id": "bbbbbbbb-0009-4000-8000-000000000009",
        "name": "Condición Estructural",
        "family": "structural_condition",
        "glaserian": True,
        "layer": "context",
        "sorting_label": "¿Qué condiciones estables moldean el fenómeno?",
        "correlation_prompt": "¿El memo A describe una condición estructural estable que moldea o constriñe lo que describe el memo B?",
    },
    {
        "id": "bbbbbbbb-0010-4000-8000-000000000010",
        "name": "Contingencia / Condiciones",
        "family": "contingency",
        "glaserian": True,
        "layer": "context",
        "sorting_label": "¿Qué condiciones variables lo modifican?",
        "correlation_prompt": "¿El memo A describe una condición que, cuando está presente, modifica lo que describe el memo B? ¿Es un 'depende'?",
    },
    {
        "id": "bbbbbbbb-0011-4000-8000-000000000011",
        "name": "Covarianza / Co-variación",
        "family": "covariance",
        "glaserian": True,
        "layer": "relationship",
        "sorting_label": "¿Qué varía junto?",
        "correlation_prompt": "¿Los memos A y B varían juntos? ¿Cuando A aumenta, B también? ¿O se mueven en direcciones opuestas?",
    },
    {
        "id": "bbbbbbbb-0012-4000-8000-000000000012",
        "name": "Intercambiabilidad / Equivalencia",
        "family": "interchangeability",
        "glaserian": True,
        "layer": "validation",
        "sorting_label": "¿Son la misma categoría?",
        "correlation_prompt": "¿Los memos A y B describen el mismo fenómeno subyacente? ¿Son intercambiables? ¿Deberían fusionarse?",
    },
]
```

### 2.2 Refactor de `theory_seeder.py`

El seeder debe importar de `theoretical_families.py` en lugar de tener el dict hardcodeado. Los campos adicionales (`evaluation_logic`, `output_schema`, `compatible_with`) se mantienen en el seeder porque son específicos del Playground, no del MemoMaker.

```python
# theory_seeder.py — refactorizado
from app.core.theoretical_families import THEORETICAL_FAMILIES as FAMILIES

def seed_theoretical_codes(session: Session) -> int:
    inserted = 0
    for fam in FAMILIES:
        existing = session.execute(
            text("SELECT id FROM theoretical_codes WHERE id = :fid"),
            {"fid": fam["id"]},
        ).fetchone()
        if not existing:
            # Aquí se agregan evaluation_logic, output_schema, etc.
            # que son específicos del Playground
            ...
```

---

## 3. Diseño del MemoMaker — 3 agentes

### 3.1 Trigger

El MemoMaker se dispara desde `task_core_saturation_loop` cuando una categoría alcanza el criterio de saturación (`did_state_expand=false` por 3 iteraciones consecutivas). No es un paso automático del coordinator — es un **servicio bajo demanda** que el saturation loop invoca por categoría.

```python
# En task_core_saturation_loop, después de detectar saturación:
if no_expand_count >= 3:
    cat_results["status"] = "saturated"
    # ── Disparar MemoMaker ──
    _run_memo_maker(s, proyecto_id, cat_id, cat_name, cat_def)
```

### 3.2 Arquitectura de los 3 agentes

```
┌─ MEMOMAKER ───────────────────────────────────────────────────────┐
│                                                                    │
│  TRIGGER: Categoría saturada (did_state_expand=false × 3)          │
│                                                                    │
│  ┌─ AGENTE 1: memo_generator (PRO) ────────────────────────────┐  │
│  │                                                              │  │
│  │ PROMPT: prompts/pro/memo_generator.md                        │  │
│  │                                                              │  │
│  │ INPUT (desde DB):                                            │  │
│  │  • category_label, category_definition, version              │  │
│  │  • paradigm_states: todas las iteraciones (ORDER BY iter)    │  │
│  │    ─ did_state_expand, expansion_type, paradigm_snapshot     │  │
│  │  • incidents: codigos_segmento JOIN segmentos JOIN docs      │  │
│  │    ─ s.texto, d.original_filename, cs.confianza              │  │
│  │    ─ LIMIT 30 (muestra representativa)                       │  │
│  │  • related_memos: memos HIPOTESIS/PROPIEDAD/RELACION         │  │
│  │    ─ WHERE contenido ILIKE '%' || cat_name || '%'            │  │
│  │                                                              │  │
│  │ OUTPUT:                                                      │  │
│  │  {                                                           │  │
│  │    "descriptive_memo": "400-800 palabras. Describe lo que    │  │
│  │     LOS DATOS MUESTRAN. Lenguaje de participantes. Incluye   │  │
│  │     variación: 'en unos casos... en otros...'. No fuerces    │  │
│  │     estructura de condiciones/consecuencias.",               │  │
│  │    "what_emerged": [                                         │  │
│  │      "Hallazgo 1 — patrón consolidado a través de las        │  │
│  │       iteraciones",                                          │  │
│  │      "Hallazgo 2 — propiedad nueva y cuándo apareció",       │  │
│  │      "Hallazgo 3 — incidente divergente que expandió"        │  │
│  │    ],                                                        │  │
│  │    "what_remains_open": [                                    │  │
│  │      "Pregunta sin resolver — qué falta documentar"          │  │
│  │    ],                                                        │  │
│  │    "evolution_narrative": "cómo cambió la definición:        │  │
│  │     versión 1 → versión 2 → versión N",                     │  │
│  │    "representative_incidents": [                             │  │
│  │      {"text": "...", "document": "...", "why": "..."}        │  │
│  │    ] (máx 3)                                                │  │
│  │  }                                                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│                          ▼                                         │
│  ┌─ AGENTE 2: memo_simplifier (PRO) ───────────────────────────┐  │
│  │                                                              │  │
│  │ PROMPT: prompts/pro/memo_simplifier.md                       │  │
│  │                                                              │  │
│  │ INPUT: descriptive_memo + what_emerged + what_remains_open   │  │
│  │        + evolution_narrative (del Agente 1)                  │  │
│  │                                                              │  │
│  │ OUTPUT:                                                      │  │
│  │  {                                                           │  │
│  │    "simplified_memo": "150-250 palabras. Elimina redundancia,│  │
│  │     preserva esencia y variación.",                          │  │
│  │    "core_statements": [                                      │  │
│  │      "Afirmación 1 — lo que los datos consistentemente       │  │
│  │       muestran (con evidencia)",                             │  │
│  │      "Afirmación 2 — ...",                                   │  │
│  │      "Afirmación 3 — ..."                                    │  │
│  │    ],                                                        │  │
│  │    "tensions_flagged": [                                     │  │
│  │      "Tensión entre hallazgo X y hallazgo Y — posible        │  │
│  │       paradoja o dimensión no capturada"                     │  │
│  │    ],                                                        │  │
│  │    "simplifier_note": "qué eliminé y por qué (transparencia  │  │
│  │     metodológica)"                                           │  │
│  │  }                                                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                          │                                         │
│                          ▼                                         │
│  ┌─ AGENTE 3: memo_correlator (FLASH) ─────────────────────────┐  │
│  │                                                              │  │
│  │ PROMPT: prompts/flash/memo_correlator.md                     │  │
│  │                                                              │  │
│  │ INPUT:                                                       │  │
│  │  • simplified_memo de ESTA categoría (Agente 2)              │  │
│  │  • simplified_memos de TODAS las demás categorías saturadas  │  │
│  │    (cargados de elaboration_memos WHERE                      │  │
│  │     elaboration_type='memo_simplified')                      │  │
│  │  • LAS 12 FAMILIAS TEÓRICAS (desde theoretical_families.py)  │  │
│  │    ─ Cada familia con su correlation_prompt                  │  │
│  │                                                              │  │
│  │ OUTPUT:                                                      │  │
│  │  {                                                           │  │
│  │    "discovered_patterns": [                                  │  │
│  │      {                                                       │  │
│  │        "pattern_label": "nombre descriptivo del patrón",     │  │
│  │        "description": "descripción del patrón cross-memo",   │  │
│  │        "theoretical_family": "process | causal | opposition  │  │
│  │         | typology | hierarchy | matrix | consequences       │  │
│  │         | strategy | structural_condition | contingency      │  │
│  │         | covariance | interchangeability",                  │  │
│  │        "family_label": "Proceso / Secuencia",                │  │
│  │        "evidence_categories": ["cat A", "cat B"],            │  │
│  │        "confidence": "high | medium | low"                   │  │
│  │      }                                                       │  │
│  │    ],                                                        │  │
│  │    "homeless_insights": [                                    │  │
│  │      "Idea del memo que no correlaciona con ninguna otra     │  │
│  │       categoría — posible nuevo código o dimensión"          │  │
│  │    ],                                                        │  │
│  │    "DEBATE_RATIONALE": {                                     │  │
│  │      "agent_1_proposed": "qué propuso el generator (resumen  │  │
│  │       de los hallazgos principales)",                        │  │
│  │      "agent_2_challenged": "qué simplificó o tensionó el     │  │
│  │       simplifier (qué eliminó, qué flaggeó)",                │  │
│  │      "agent_3_found": "qué patrones cross-memo descubrió el  │  │
│  │       correlator usando las 12 familias",                    │  │
│  │      "consensus": "en qué coinciden los 3 agentes",          │  │
│  │      "disagreements": "en qué difieren y por qué"            │  │
│  │    }                                                         │  │
│  │  }                                                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  PERSISTENCIA (3 elaboration_memos por categoría):                 │
│  • elaboration_type='memo_generated'     → descriptive_memo        │
│  • elaboration_type='memo_simplified'    → simplified_memo +       │
│    core_statements + tensions_flagged                              │
│  • elaboration_type='memo_correlated'    → discovered_patterns +   │
│    homeless_insights + debate_rationale                            │
│  • UPDATE categorias SET metadatos = metadatos ||                  │
│    '{"last_memo_at": "<timestamp>"}'::jsonb                        │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Integración con el Sorting Log

### 4.1 Qué es el Sorting Log

Según `kb.md` §8.3, el sorting es el proceso de agrupar memos usando los 12 lentes teóricos. El investigador prueba familias: "Probé Proceso: 4 grupos, 1 homeless. Probé Causal: 5 grupos, 0 homeless." Los memos generados por el MemoMaker son el **input** de este proceso.

### 4.2 Nueva tabla: `memo_sorting_attempts`

Para registrar el sorting log que describe el kb.md:

```sql
CREATE TABLE memo_sorting_attempts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES proyectos(id),
    theoretical_family TEXT NOT NULL,  -- 'process', 'causal', etc.
    attempted_at TIMESTAMPTZ DEFAULT now(),

    -- Resultados del sorting para esta familia
    groups_formed INT,         -- cuántos grupos se formaron
    homeless_count INT,        -- cuántos memos quedaron sin grupo
    forced_count INT,          -- cuántas colocaciones fueron forzadas
    thin_groups INT,           -- cuántos grupos tienen < 3 memos

    -- Topología de grupos
    group_map JSONB,           -- {group_label: [memo_id, ...]}
    cross_family_matches JSONB -- grupos que también aparecen en otras familias
);
```

### 4.3 Pre-clasificación al entrar al Playground

El `RecommendationEngine` (`recommendation_engine.py`) debe extenderse para pre-clasificar los memos generados por el MemoMaker:

```
Al entrar al Playground:
  1. Cargar todos los elaboration_memos tipo='memo_simplified'
  2. Para cada memo, ejecutar memo_correlator (FLASH) en modo "pre-classify"
     → "Este memo tiene afinidad con Causal (0.85) y Proceso (0.70)"
  3. Mostrar estas afinidades en el RecommendationGuide como punto de partida
```

---

## 5. Plan de implementación

| Paso | Archivo | Acción |
|------|---------|--------|
| **M1** | `backend/app/core/theoretical_families.py` (NUEVO) | Extraer las 12 familias a config compartido |
| **M2** | `backend/app/services/theory_seeder.py` | Refactorizar: importar de theoretical_families.py |
| **M3** | `prompts/pro/memo_generator.md` (NUEVO) | Prompt del Agente 1 |
| **M4** | `prompts/pro/memo_simplifier.md` (NUEVO) | Prompt del Agente 2 |
| **M5** | `prompts/flash/memo_correlator.md` (NUEVO) | Prompt del Agente 3 |
| **M6** | `workers/heavy/tasks.py` | Agregar `_run_memo_maker()` + integrar en saturation loop |
| **M7** | `backend/app/models/domain/` (NUEVO) | Modelo `MemoSortingAttempt` + migración |
| **M8** | `backend/app/services/recommendation_engine.py` | Extender con pre-clasificación de memos |

---

## 6. Notas de diseño

1. **Las 12 familias son configuración, no código.** Cualquier componente que necesite los lentes teóricos (MemoMaker, Playground, RecommendationEngine) importa de `theoretical_families.py`. Si el investigador crea una nueva familia user-defined, se agrega a `theoretical_codes` en DB y el sistema la descubre dinámicamente.

2. **El MemoMaker no reemplaza al investigador.** Los memos generados son input para el sorting, no el sorting en sí. El investigador sigue siendo quien arrastra blobs, elige lentes, y decide la estructura final. El MemoMaker acelera la fase de "escribir el memo inicial".

3. **El Agente 3 descubre, no impone.** El `memo_correlator` usa las 12 familias como lentes para encontrar patrones, pero no fuerza que cada par de memos encaje en una familia. Los `homeless_insights` son tan valiosos como los `discovered_patterns`.

4. **El debate rationale es trazabilidad.** No es un lujo cosmético — es el registro de cómo se llegó a cada conclusión. Si en 6 meses el investigador vuelve a leer los memos, el debate rationale le dice exactamente qué pensó cada agente y por qué.
