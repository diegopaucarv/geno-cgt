# CGT Alignment — Refacción Arquitectónica

> **Objetivo:** Alinear el pipeline de Open Coding (Fase A) y Síntesis Cross-Document (Fase B) con los requisitos metodológicos de la Classic Grounded Theory.
>
> **Versión:** 1.0 — 2026-06-16
>
> **Problema detectado:** El diagrama de secuencias actual modela el pipeline como una línea de ensamblaje automatizada, sin HITL, sin separación entre hallazgo/comparación/síntesis, y sin verificación progresiva del main concern.

---

## 1. Diagnóstico del diagrama actual

### 1.1 Lo que el diagrama muestra

```
Segmentación → Open Coding (A1, A2, B2a, B2b, B2.5, Prime Mover, A3)
            → Síntesis (B1, Map, Reduce, Core Concern, Hypotheses)
            → Find Core Category (Paradigm, Main Concern, Core Emergence…)
            → Selective Reduction → Saturation → Database A/B → Playground
```

### 1.2 Lo que está mal (6 problemas estructurales)

| # | Problema | Evidencia en el diagrama | Consecuencia metodológica |
|---|----------|--------------------------|---------------------------|
| **P1** | **Sin HITL en decisiones teóricas** | Entre Segmentación y Playground no hay ningún `🛑 HITL`. El Core Concern Finder, Main Concern Proposer, y Selective Reduction se ejecutan automáticamente. | Viola R0.1 del `Patron_Desarrollo_Maestro.md`. El investigador nunca confirma el main concern ni la core category. |
| **P2** | **Hallazgo, comparación y síntesis colapsados** | B2a (Indicator Extractor), B2b (Code Generator) y B2.5 (Code Critic) operan en el mismo paso. El mismo agente que encuentra incidentes también los compara y etiqueta. | Sesgo de confirmación temprana: el incidente nuevo se fuerza a encajar en categorías existentes. No hay separación entre "¿qué hay aquí?" y "¿se parece a lo que ya vi?". |
| **P3** | **Patrón de interés como paso aislado y tardío** | El Core Concern Finder aparece después de la síntesis, como un paso independiente. | La verificación del patrón de interés es imposible antes de 3 entrevistas, y debe progresar con cada nuevo documento. No es un paso final — es un proceso iterativo. |
| **P4** | **Población estática** | A1 (Population Context) se actualiza pero el investigador nunca puede cambiar el scope poblacional. | Si el investigador descubre que su población real son "redactores" y no "todos los periodistas", A1 debería regenerarse. El diagrama no contempla este bucle. |
| **P5** | **Sin distinción baseline/properline/interpreted** | Todos los segmentos se codifican por igual. | `properline_data` (deseabilidad social) y `interpreted_data` (opinión forzada) contaminan la extracción del main concern. Solo `baseline_data` (experiencia espontánea) revela la preocupación real. |
| **P6** | **A1 y A2 en orden incorrecto** | A1 (Population Context) y A2 (Process Identifier) se ejecutan en paralelo o A1 antes que A2. | A2 (proceso individual) debe ejecutarse primero por documento. A1 (contexto poblacional) debe actualizarse cada 3 documentos, usando los A2 acumulados. |

---

## 2. Fase 0: Configuración inicial (mínima, guiada)

### 2.1 Solo 2 configuraciones obligatorias

```
┌─────────────────────────────────────────────────────────────────┐
│ FASE 0: CONFIGURACIÓN INICIAL                                    │
│                                                                  │
│ 0. POBLACIÓN DE INTERÉS (único parámetro obligatorio)            │
│    El investigador describe su población en lenguaje natural.    │
│    Puede ser específica: "los pobladores del asentamiento        │
│    humano X". Pero el sistema necesita una descripción           │
│    GENERALIZABLE para que el análisis tenga validez teórica.     │
│                                                                  │
│    ┌─ population_generalizer (FLASH, automático) ─────────────┐ │
│    │ Transforma la descripción cruda del usuario en una        │ │
│    │ población generalizable a nivel de sistema:               │ │
│    │                                                           │ │
│    │ Input:  "los pobladores del asentamiento humano X"        │ │
│    │ Output: "habitantes de asentamientos humanos marginales   │ │
│    │          de Lima en situación de pobreza urbana"          │ │
│    │                                                           │ │
│    │ Input:  "periodistas de 3 redacciones en España y México" │ │
│    │ Output: "periodistas en activo en medios hispanohablantes  │ │
│    │          con presencia digital"                            │ │
│    │                                                           │ │
│    │ La descripción cruda se PRESERVA como contexto.           │ │
│    │ La descripción generalizada es la que alimenta A1,        │ │
│    │ guía el muestreo, y delimita el alcance teórico.         │ │
│    │ El investigador puede EDITAR la versión generalizada.     │ │
│    └──────────────────────────────────────────────────────────┘ │
│                                                                  │
│    → El sistema infiere spatial_frame según la descripción:      │
│      "un solo asentamiento" = cohabiting_group                 │
│      "varios asentamientos en una ciudad" = sparse              │
│      "múltiples ciudades/países" = high_diversity               │
│                                                                  │
│    → El sistema infiere temporal_frame según la descripción:     │
│      "en situación de pobreza urbana" = present_continuous      │
│      "que fueron desplazados en 2020" = retrospective           │
│                                                                  │
│ 1. OBJETO DE ESTUDIO (obligatorio, default: "concern")           │
│    Define QUÉ tipo de patrón humano se busca:                    │
│                                                                  │
│    ○ "concern" — preocupación central (default CGT)              │
│    ○ "emotion" — emoción central                                 │
│    ○ "behavior" — conducta central                               │
│    ○ "discourse" — discurso central                              │
│    ○ "identity" — trabajo identitario                            │
│                                                                  │
│    → Deriva automáticamente el ROLE PROMPT:                      │
│      "concern" → "" (layman, sin preconcepciones)                │
│      "emotion" → "investigador de patrones emocionales"          │
│      "behavior" → "observador de conductas recurrentes"          │
│      (el investigador puede editarlo)                            │
│                                                                  │
│    → Define el formato de codificación:                          │
│      "concern" → gerundios de procesamiento                      │
│      "emotion" → gerundios de sentir                             │
│      "behavior" → gerundios de acción                            │
│                                                                  │
│ ── OPCIONAL (bajo demanda del investigador) ─────────────────── │
│                                                                  │
│ 2. POPULATION ANALYST (agente opcional)                          │
│    El investigador puede pedir: "Analizá mi población"           │
│    → Lee A1 + core patterns iniciales                            │
│    → Sugiere sub-poblaciones, ajustes de scope                  │
│    → Ej: "Parece haber dos grupos diferenciados: periodistas     │
│      gestores (integran IA) y redactores (resisten). ¿Querés    │
│      enfocarte en uno o mantener ambos?"                         │
│                                                                  │
│ 3. QUALITATIVE CONFIG ADVISOR (agente opcional)                  │
│    El investigador puede pedir: "Sugerime configuraciones"       │
│    → Lee los datos iniciales                                    │
│    → Recomienda object_of_study, temporal_frame, coding_style   │
│    → Ej: "Por el tipo de entrevistas (preguntas abiertas sobre   │
│      experiencia laboral), sugeriría object_of_study='concern',  │
│      temporal_frame='present_continuous'. Tus datos muestran      │
│      más patrones de procesamiento que de emoción pura."         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Implementación en BD

```sql
-- population_assumption ya existe (C01, migración 010)
-- Se amplía para incluir role_prompt
ALTER TABLE proyectos 
ADD COLUMN role_prompt TEXT DEFAULT '';  -- '' = layman
```

---

## 3. Fase A corregida: Open Coding con verificación progresiva

### 3.1 Principios

1. **El hallazgo de incidentes NO compara con otros documentos.** El `IncidentExtractor` solo ve el documento actual. Comparar con datos previos en esta etapa sesga el análisis.

2. **La comparación es un paso separado y posterior.** El `IncidentComparator` (Fase B) es el único agente con acceso a múltiples documentos.

3. **La verificación del patrón de interés es progresiva.** No es un paso final. Comienza con el primer documento (problema tentativo) y se refina cada 3 documentos.

4. **La población puede cambiar.** El investigador, al ver A1 cada 3 documentos, puede decidir que la población real es más acotada (o más amplia) que la inicial.

### 3.2 Flujo detallado

```
┌─ FASE A: OPEN CODING POR DOCUMENTO ─────────────────────────────┐
│                                                                  │
│  INPUT: Documento segmentado                                     │
│  CONFIG: population_assumption (población + objeto de estudio)   │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  A0. PRE-CLASIFICACIÓN (por segmento, FLASH)                     │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: glaser_data_classifier (FLASH)                          │
│  Input:  segmento.texto                                          │
│  Output: baseline_data | properline_data | interpreted_data      │
│          | vague_data                                            │
│                                                                  │
│  → Solo los segmentos baseline_data avanzan a A1.                │
│  → properline e interpreted se archivan para contexto.           │
│  → vague_data se marca como anomalía.                            │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  A1. INCIDENT EXTRACTION (por segmento baseline, PRO)            │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: incident_extractor (PRO) — NUEVO o REFACCIONADO         │
│  Input:  segmento baseline_data                                  │
│  Context: population_assumption.object_of_study                  │
│                                                                  │
│  Aplica las 4 preguntas de Glaser:                               │
│    1. "¿De qué trata este dato?"                                 │
│    2. "¿Qué categoría o propiedad indica este incidente?"        │
│    3. "¿Qué está sucediendo realmente aquí?"                     │
│    4. "¿Cuál es la preocupación principal del participante?"     │
│                                                                  │
│  Produce:                                                        │
│    • jot (anotación rápida, 1-2 palabras, gerundio)              │
│    • Las 4 respuestas textuales                                  │
│    • confidence (0.0-1.0)                                       │
│    • keep_moving: true si el incidente es ambiguo                │
│      (no sobre-analizar — anotar y avanzar)                     │
│                                                                  │
│  REGLAS CRÍTICAS:                                                │
│    • NO compara con otros documentos (sesgo de confirmación)     │
│    • NO compara con categorías existentes (fuerza encaje)        │
│    • Si keep_moving=true → guardar el jot y avanzar              │
│    • Usa gerundios (u otro formato según object_of_study)        │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  A2. RESEARCH PROBLEM EXTRACTION (por documento, PRO)                            │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: pattern_of_interest_extractor (PRO) — EXISTENTE (C03, implementado como `prime_mover_extractor`)           │
│  Input:  todos los segmentos baseline_data del documento         │
│  Context: population_assumption.object_of_study                  │
│                                                                  │
│  Output:                                                         │
│    • pattern_of_interest (gerundio)                                      │
│    • description (2-3 oraciones)                                 │
│    • evidence_quotes (citas textuales)                           │
│    • confidence (HIGH | MEDIUM | LOW)                            │
│                                                                  │
│  NOTA DE MODULARIDAD:                                            │
│    Si object_of_study = "concern" → busca preocupaciones         │
│    Si object_of_study = "emotion" → busca patrón emocional       │
│    El método no cambia. El lente sí.                             │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  A3. POPULATION CONTEXT UPDATE (cada 3 documentos, PRO)          │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: A1 (Population Context) — EXISTENTE                     │
│  Input:  segmentos del nuevo documento + context acumulado       │
│  Output: surprising_details, language_patterns,                  │
│          data_production_context                                  │
│                                                                  │
│  🛑 HITL GATE (cada 3 documentos):                               │
│     El sistema muestra:                                          │
│       • Población actual: "[descripción]"                        │
│       • Nuevos surprising_details: "[...]"                       │
│       • Pregunta: "¿La población sigue siendo la correcta?"      │
│                                                                  │
│     El investigador puede:                                       │
│       • Mantener población actual                                │
│       • Acotar: "Solo redactores, no gestores"                   │
│       • Ampliar: "También medios digitales nativos"              │
│       • Cambiar completamente: "En realidad son editores"        │
│                                                                  │
│     Si cambia → A1 se regenera con el nuevo scope.               │
│     Los incidentes ya extraídos se conservan (no se pierden).    │
│     Los que quedan fuera del nuevo scope se marcan como          │
│     "out_of_scope" (archivados, no eliminados).                  │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  A4. RESEARCH PROBLEM VERIFICATION (cada 3 documentos, PRO)          │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: pattern_of_interest_verifier (PRO) — UNIFICA A14 + critic      │
│  Input:                                                          │
│    • pattern_of_interests de TODOS los documentos procesados (A2)        │
│    • A1 (population context actualizado)                         │
│    • object_of_study                                             │
│                                                                  │
│  Output:                                                         │
│    • pattern_of_interest propuesto (formato según object_of_study)    │
│    • relevant_population_dimensions (Momento 1)                  │
│    • confidence (HIGH | MEDIUM | LOW)                            │
│    • converging (cuántos documentos comparten este problema)            │
│    • diverging (cuáles no encajan y por qué)                  │
│                                                                  │
│  🛑 HITL GATE (cada 3 documentos):                               │
│     El sistema muestra:                                          │
│       • Patrón de interés actual: "[...]"                             │
│       • Patrón de interés propuesto: "[...]"                          │
│       • Documentos que convergen: 5/7                          │
│       • Documentos que divergen: 2/7 (con explicación)        │
│       • Dimensiones poblacionales relevantes                     │
│                                                                  │
│     El investigador puede:                                       │
│       • Confirmar                                                │
│       • Modificar (escribir su propio patrón de interés)              │
│       • Cambiar object_of_study ("no es concern, es emotion")    │
│       • Pedir más datos antes de decidir                         │
│                                                                  │
│     Si cambia object_of_study → se actualiza role_prompt         │
│     y se re-ejecutan A1 y A2 con el nuevo lente.                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. Fase B corregida: Síntesis Cross-Document con tres agentes + crítico

### 4.1 Principios

1. **Separación estricta hallazgo/comparación/síntesis.** El `IncidentComparator` (B1) no etiqueta. El `PatternLabeler` (B2) no compara. El `LabelCritic` (B3) no etiqueta ni compara — solo evalúa.

2. **El Comparator solo ve incidentes crudos.** No ve categorías existentes. Esto evita el sesgo de confirmación: forzar incidentes nuevos a encajar en moldes viejos.

3. **El Labeler y el Critic dialogan.** Si el Critic encuentra que una etiqueta no captura el patrón, re-ejecuta el Labeler con feedback. Es un bucle generativo-crítico, no un paso lineal.

4. **La verificación del patrón de interés continúa.** El B4 se ejecuta cada 3 documentos nuevos, refinando el patrón de interés con las categorías emergentes de B2.

### 4.2 Flujo detallado

```
┌─ FASE B: SÍNTESIS CROSS-DOCUMENT ───────────────────────────────┐
│                                                                  │
│  DISPARADOR: ≥ 3 documentos con A1-A2 completado                 │
│  CONFIG: population_assumption (población + objeto de estudio)   │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  B1. INCIDENT COMPARATOR (cross-document, PRO)                   │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: incident_comparator (PRO) — REFACCIONAR DESDE            │
│          clusterizador_informado.md                               │
│                                                                  │
│  Input:  TODOS los extracted_incidents de TODOS los documentos   │
│          procesados hasta ahora                                   │
│                                                                  │
│  Context: NINGUNO — solo ve incidentes crudos.                   │
│           NO ve categorías existentes.                            │
│           NO ve el main concern.                                  │
│                                                                  │
│  Método: Constant Comparative Method                              │
│    1. Toma pares de incidentes.                                   │
│    2. Compara: ¿describen el mismo patrón de comportamiento?      │
│    3. Agrupa por intercambiabilidad de indicadores.              │
│    4. Para cada grupo:                                           │
│       • ¿Qué comparten?                                          │
│       • ¿En qué varían? (dimensiones internas)                   │
│                                                                  │
│  Output:                                                         │
│    • incident_groups: [{incident_ids, shared_pattern_description, │
│      internal_variations}]                                       │
│    • ungrouped_incidents: [{incident_id, why_ungrouped}]          │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  B2. PATTERN LABELER (cross-document, PRO)                       │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: pattern_labeler (PRO) — REFACCIONAR DESDE               │
│          b2b_generate_codes.md                                    │
│                                                                  │
│  Input:  incident_groups de B1                                   │
│  Context: object_of_study (determina formato de etiqueta)        │
│                                                                  │
│  Método:                                                         │
│    1. Para cada grupo de B1:                                     │
│       • Propone etiqueta en gerundio (u otro formato)            │
│       • Escribe definición inicial (2-3 oraciones)               │
│       • Identifica propiedades emergentes del grupo              │
│    2. Para incidentes ungrouped:                                 │
│       • Propone etiqueta individual si el patrón es claro        │
│       • Marca como "anomalía" si no hay patrón                   │
│                                                                  │
│  Output:                                                         │
│    • proposed_labels: [{group_id, label (gerundio), definition,  │
│      properties, incident_ids}]                                   │
│    • anomalies: [{incident_id, rationale}]                       │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  B3. LABEL CRITIC (cross-document, PRO, dialoga con B2)          │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Agente: label_critic (PRO) — REFACCIONAR DESDE b2_critic.md     │
│                                                                  │
│  Input:  proposed_labels de B2 + incidentes fuente               │
│                                                                  │
│  Método:                                                         │
│    Para cada etiqueta propuesta por B2:                          │
│    1. ¿La etiqueta captura el patrón subyacente de TODOS los     │
│       incidentes del grupo?                                       │
│    2. ¿Es suficientemente abstracta? (ni muy concreta ni muy     │
│       vaga)                                                      │
│    3. ¿Es un gerundio? (o el formato correcto según objeto)      │
│    4. ¿Hay incidentes en el grupo que NO encajan con la etiqueta?│
│       → Si sí, ¿deberían estar en otro grupo?                    │
│                                                                  │
│  Output:                                                         │
│    • evaluations: [{label_id, verdict: SAT | MOD | FORCED,       │
│      rationale, suggested_improvement}]                          │
│    • mislabeled_incidents: [{incident_id, current_label,         │
│      suggested_label}]                                           │
│                                                                  │
│  BUCLE GENERATIVO-CRÍTICO:                                       │
│    Si hay verdicts MOD → re-ejecutar B2 con el feedback del      │
│    critic (suggested_improvement). Máximo 3 iteraciones.         │
│    Si hay verdicts FORCED → el incidente va a ungrouped.         │
│                                                                  │
│  ═══════════════════════════════════════════════════════════════ │
│  B4. MAIN CONCERN VERIFICATION (cada 3 docs nuevos, PRO)         │
│  ═══════════════════════════════════════════════════════════════ │
│                                                                  │
│  Mismo agente que A4, pero ahora recibe también:                 │
│    • Las categorías emergentes de B2 (patrones etiquetados)      │
│    • Los ungrouped incidents de B1 (posibles nuevos patrones)    │
│                                                                  │
│  Esto permite refinar el patrón de interés con evidencia de           │
│  categorías emergentes, no solo de problemas individuales por documento.      │
│                                                                  │
│  🛑 HITL GATE (mismo mecanismo que A4)                           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 5. Los 7 agentes: especificación completa

### 5.1 `glaser_data_classifier` — A0

| Campo | Valor |
|-------|-------|
| **Estado** | ✅ EXISTENTE (`deepseek_flash/glaser_data_classifier.md`, C02) |
| **Tier** | ⚙️ Algorítmico + 🟡 FLASH (dos capas) |
| **Input** | `segmento.texto`, `document_name`, `interview_type` |
| **Output** | `data_type` (baseline | properline | interpreted | vague), `rationale`, `contains_concern` (bool) |
| **Se ejecuta** | Una vez por segmento, al inicio del pipeline |
| **Consume** | Nada (solo el segmento) |
| **Alimenta** | A1 (solo baseline_data avanza) |
| **Estrategia** | **Dos capas:** (1) `preclassify_glaser()` algorítmico (regex + heurísticas) clasifica ~90% de segmentos — rápido y gratuito. (2) Confirmación FLASH solo para segmentos con `confidence < 0.7` (borderline). Este patrón híbrido ⚙️+FLASH es reutilizable para muchos agentes FLASH donde el 90% de los casos son determinísticos. |

### 5.2 `incident_extractor` — A1

| Campo | Valor |
|-------|-------|
| **Estado** | ⚠️ REFACCIONAR desde `b2a_extract_indicators.md` + `incident_extractor.md` |
| **Tier** | 🟡 **FLASH** |
| **Input** | `segmento.texto` (baseline_data), `object_of_study` |
| **Output** | `jot` (1-2 palabras, gerundio), `what_is_this_about`, `what_category_does_it_indicate`, `what_is_really_happening`, `participants_pattern` (parametrizado por object_of_study), `confidence`, `keep_moving` |
| **Se ejecuta** | Una vez por segmento baseline (cientos de llamadas por proyecto) |
| **Consume** | NADA (no ve otros docs, no ve categorías) |
| **Alimenta** | `extracted_incidents` table → B1 |
| **Reglas** | Keep Moving: si el incidente es ambiguo, anotar y avanzar. No sobre-analizar. |
| **Justificación del tier:** FLASH, no PRO. El output son 4 respuestas de ~1 oración cada una + un jot de 1-2 palabras → ~1 párrafo total. Nuestro modelo FLASH maneja outputs de hasta un párrafo para tareas estructuradas. Usar PRO aquí violaría el principio keep-moving (sobre-analizar incidentes individuales) y costaría 10× más en cientos de llamadas. La profundidad analítica emerge de la acumulación de docenas de incidentes, no del análisis individual. |

### 5.3 `pattern_of_interest_extractor` — A2

> **Nota terminológica:** El nombre interno del campo en BD y código es `prime_mover` (herencia de Glaser). El contenido se adapta al `object_of_study`. Si `object_of_study = "concern"`, extrae una preocupación central (main concern). Si `object_of_study = "emotion"`, extrae una emoción central recurrente. En todos los casos, el output es el **patrón de interés** (pattern of interest) que estructura la experiencia de este entrevistado.

| Campo | Valor |
|-------|-------|
| **Estado** | ✅ EXISTENTE (`deepseek_pro/prime_mover_extractor.md`, C03) |
| **Tier** | PRO |
| **Input** | `baseline_segments` del documento, `object_of_study` |
| **Output** | `prime_mover` (gerundio), `description`, `evidence_quotes`, `confidence` |
| **Se ejecuta** | Una vez por documento |
| **Consume** | Solo segmentos baseline del documento actual |
| **Alimenta** | A4 (Main Concern Verification) |

### 5.4 `incident_comparator` — B1

| Campo | Valor |
|-------|-------|
| **Estado** | ⚠️ REFACCIONAR desde `clusterizador_informado.md` |
| **Tier** | PRO |
| **Input** | `extracted_incidents[]` de TODOS los documentos |
| **Output** | `incident_groups[]` (incident_ids, shared_pattern_description, internal_variations), `ungrouped_incidents[]` |
| **Se ejecuta** | Cada ≥3 documentos |
| **Consume** | Incidentes crudos. NO ve categorías existentes. |
| **Alimenta** | B2 (Pattern Labeler) |
| **Reglas** | Constant Comparative Method. Intercambiabilidad de indicadores. |

### 5.5 `pattern_labeler` — B2

| Campo | Valor |
|-------|-------|
| **Estado** | ⚠️ REFACCIONAR desde `b2b_generate_codes.md` |
| **Tier** | PRO |
| **Input** | `incident_groups[]` de B1, `object_of_study` |
| **Output** | `proposed_labels[]` (group_id, label, definition, properties, incident_ids), `anomalies[]` |
| **Se ejecuta** | Después de B1 |
| **Consume** | Solo los grupos de B1 |
| **Alimenta** | B3 (Label Critic) |

### 5.6 `label_critic` — B3

| Campo | Valor |
|-------|-------|
| **Estado** | ⚠️ REFACCIONAR desde `b2_critic.md` |
| **Tier** | 🟡 **FLASH** |
| **Input** | `proposed_labels[]` de B2 + incidentes fuente |
| **Output** | `evaluations[]` (label_id, verdict: SAT|MOD|FORCED, rationale, suggested_improvement), `mislabeled_incidents[]` |
| **Se ejecuta** | Después de B2. Puede re-ejecutar B2 (máx 3 iteraciones). |
| **Consume** | Etiquetas de B2 + incidentes originales |
| **Alimenta** | B2 (si MOD → re-ejecutar) o DB (si SAT → guardar categorías) |
| **Justificación del tier:** FLASH, no PRO. Evaluar etiquetas contra grupos de incidentes es un diff estructurado — análogo a un code review. El output es un veredicto + rationale corto + lista de issues → cabe en un párrafo. Nuestro FLASH maneja esto perfectamente. El bucle B2↔B3 puede iterar hasta 3 veces: usar PRO aquí triplicaría el costo innecesariamente. La separación generate (PRO) ↔ critique (FLASH) es exactamente el patrón que `SelfRefinementLoop` ya implementa. |

### 5.7 `core_pattern_verifier` — A4 (Open Coding)

> **Importante:** Este agente verifica convergencia de patrones individuales cada 3 documentos durante open coding. NO debe confundirse con `main_concern_proposer` + `main_concern_critic` que operan en selective coding (Fase A) con inputs mucho más ricos (sistema completo de categorías + memos). Son rituales metodológicos distintos. Ver kb.md §4 vs §6.1.

| Campo | Valor |
|-------|-------|
| **Estado** | ⚠️ REFACCIONAR desde `main_concern_proposer.md` (simplificando — solo recibe patrones individuales, no categorías) |
| **Tier** | 🟣 PRO |
| **Input** | `pattern_of_interests[]` (de A2, solo los 3 documentos más recientes), `A1 population_context`, `object_of_study` |
| **Output** | `convergence_assessment` (converging/diverging/mixed), `converging_patterns[]`, `diverging_patterns[]`, `confidence`, `recommendation` (continue/refine/change_lens) |
| **Se ejecuta** | Cada 3 documentos durante open coding |
| **Consume** | Patrones individuales de A2 + contexto poblacional |
| **Alimenta** | 🛑 HITL gate (¿patrón de interés correcto?) |
| **NO consume** | NO ve categorías del sistema completo (eso es tarea de `main_concern_proposer` en selective coding) |

---

## 6. Capa de datos: nuevas tablas y columnas

### 6.1 `extracted_incidents` (nueva)

```sql
CREATE TABLE extracted_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    segmento_id UUID REFERENCES segmentos(id),
    documento_id UUID REFERENCES documentos(id),
    proyecto_id UUID REFERENCES proyectos(id),
    
    -- Las 4 preguntas de Glaser
    what_is_this_about TEXT,
    what_category_does_it_indicate TEXT,
    what_is_really_happening TEXT,
    participants_main_concern TEXT,
    
    -- Jot (anotación rápida)
    jot TEXT,
    
    -- Metadata
    glaser_data_type VARCHAR(50),  -- baseline | properline | interpreted | vague
    confidence FLOAT DEFAULT 0.5,
    keep_moving BOOLEAN DEFAULT false,
    
    creado_en TIMESTAMPTZ DEFAULT now()
);
```

### 6.2 `incident_comparisons` (nueva)

```sql
CREATE TABLE incident_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    incident_a_id UUID REFERENCES extracted_incidents(id),
    incident_b_id UUID REFERENCES extracted_incidents(id),
    proyecto_id UUID REFERENCES proyectos(id),
    
    similarity_rationale TEXT,
    difference_rationale TEXT,
    are_interchangeable BOOLEAN,
    suggested_pattern_label TEXT,
    compared_by VARCHAR(50) DEFAULT 'llm',
    
    creado_en TIMESTAMPTZ DEFAULT now()
);
```

### 6.3 `incident_groups` (nueva)

```sql
CREATE TABLE incident_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    proyecto_id UUID REFERENCES proyectos(id),
    version INT DEFAULT 1,
    
    incident_ids UUID[] NOT NULL,
    shared_pattern_description TEXT,
    internal_variations JSONB DEFAULT '[]',
    
    -- Vinculado a categoría después de B2
    category_id UUID REFERENCES categorias(id),
    
    created_by_agent VARCHAR(100),  -- 'incident_comparator'
    creado_en TIMESTAMPTZ DEFAULT now()
);
```

### 6.4 Columnas nuevas en tablas existentes

```sql
-- Proyecto: role_prompt
ALTER TABLE proyectos ADD COLUMN role_prompt TEXT DEFAULT '';

-- Segmento: glaser_data_type ya existe (tipo_dato_glaser)
-- DocumentProcess: prime_mover ya existe (C06, migración 011)
```

---

## 7. Refactored Sequence Diagram (Fases A y B)

```
┌─ FASE A: OPEN CODING (por documento, iterativo) ─────────────────┐
│                                                                  │
│  Doc 1:                                                          │
│    A0 (glaser_data_classifier, FLASH) → baseline segments        │
│    A1 (incident_extractor, PRO) → extracted_incidents            │
│    A2 (pattern_of_interest_extractor, PRO) → pattern_of_interest          │
│                                                                  │
│  Doc 2:                                                          │
│    A0 → A1 → A2                                                  │
│                                                                  │
│  Doc 3:                                                          │
│    A0 → A1 → A2                                                  │
│    ─── TRIGGER: ≥3 docs ───                                      │
│    A3: Population Context (A1, PRO)                               │
│      → 🛑 HITL: ¿población correcta?                             │
│    A4: Main Concern Verification (PRO)                            │
│      Input: pattern_of_interests[doc1, doc2, doc3] + A1                 │
│      → 🛑 HITL: ¿patrón central correcto?                          │
│                                                                  │
│  Doc 4+:                                                         │
│    A0 → A1 → A2                                                  │
│    Cada 3 docs → A3 + A4 (HITL)                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

┌─ FASE B: SÍNTESIS (cada ≥3 docs, cross-document) ───────────────┐
│                                                                  │
│  B1 (incident_comparator, PRO):                                  │
│    Input: TODOS los extracted_incidents de TODOS los docs        │
│    → incident_groups (intercambiabilidad)                        │
│                                                                  │
│  B2 (pattern_labeler, PRO):                                      │
│    Input: incident_groups de B1                                  │
│    → proposed_labels (gerundios + definiciones)                  │
│                                                                  │
│  B3 (label_critic, FLASH) ↔ B2 (bucle generativo-crítico):       │
│    Evalúa cada etiqueta → SAT | MOD | FORCED                     │
│    Si MOD → re-ejecutar B2 con feedback (máx 3 iteraciones)      │
│                                                                  │
│  B4 (evidence_retriever, ALG — RAG sin LLM):                     │
│    Input: categorías aprobadas por B3                             │
│    → busca segmentos en el corpus para cada categoría             │
│                                                                  │
│  A4 (core_pattern_verifier, PRO):                                 │
│    Input: pattern_of_interests + A1 population_context            │
│    → 🛑 HITL: ¿patrón de interés correcto?                        │
│                                                                  │
│  Output: categorías validadas + patrón de interés confirmado │
│          confirmado por el investigador                          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 8. Plan de migración

### 8.1 Agentes a crear

| # | Agente | Archivo | Basado en |
|---|--------|---------|-----------|
| 1 | `incident_extractor` | `deepseek_pro/incident_extractor_v2.md` | `b2a_extract_indicators.md` + `incident_extractor.md` |
| 2 | `incident_comparator` | `deepseek_pro/incident_comparator.md` | `clusterizador_informado.md` |
| 3 | `pattern_labeler` | `deepseek_pro/pattern_labeler.md` | `b2b_generate_codes.md` |
| 4 | `label_critic` | `deepseek_pro/label_critic.md` | `b2_critic.md` |
| 5 | `pattern_of_interest_verifier` | `deepseek_pro/pattern_of_interest_verifier.md` | `main_concern_proposer.md` + `main_concern_critic.md` |

### 8.2 Agentes existentes que se mantienen

| Agente | Archivo | Rol en la nueva arquitectura |
|--------|---------|------------------------------|
| `glaser_data_classifier` | `deepseek_flash/glaser_data_classifier.md` | A0 — sin cambios |
| `pattern_of_interest_extractor` | `deepseek_pro/prime_mover_extractor.md` | A2 — sin cambios (archivo interno mantiene nombre `prime_mover`) |
| `a1_population_context` | `deepseek_pro/a1_population_context.md` | A3 — sin cambios (solo se añade HITL gate) |

### 8.3 Agentes existentes a deprecated

| Agente | Archivo | Razón |
|--------|---------|-------|
| `b2a_extract_indicators` | `deepseek_flash/b2a_extract_indicators.md` | Reemplazado por `incident_extractor` (más rico: 4 preguntas + jots) |
| `b2b_generate_codes` | `deepseek_pro/b2b_generate_codes.md` | Reemplazado por `pattern_labeler` (recibe grupos del comparator) |
| `b2_critic` | `deepseek_pro/b2_critic.md` | Reemplazado por `label_critic` (diálogo con pattern_labeler) |
| `clusterizador_informado` | `deepseek_pro/clusterizador_informado.md` | Reemplazado por `incident_comparator` (compara incidentes crudos, no categorías) |
| `main_concern_proposer` | `deepseek_pro/main_concern_proposer.md` | Unificado en `main_concern_verifier` |
| `main_concern_critic` | `deepseek_pro/main_concern_critic.md` | Unificado en `main_concern_verifier` |

### 8.4 Migraciones de BD

| # | Migración | Tablas/Columnas |
|---|-----------|-----------------|
| 013 | `extracted_incidents` | Nueva tabla |
| 014 | `incident_comparisons` | Nueva tabla |
| 015 | `incident_groups` | Nueva tabla |
| 016 | `role_prompt` en proyectos | Nueva columna |


---

## 9. Conexión con el pipeline existente

### 9.1 Lo que NO cambia

- **Segmentación** (NLP Worker) — sin cambios
- **A1 Population Context** — sin cambios en el agente, se añade HITL gate
- **A2 Process Identifier** — sin cambios
- **Prime Mover Extractor** — sin cambios
- **Selective Coding** (Fase 5b) — sin cambios, recibe las categorías de B2/B3
- **Theoretical Playground** (Fase 6b) — sin cambios

### 9.2 Lo que SÍ cambia

- **B2a/B2b/B2.5** → reemplazados por A1 (Incident Extractor) + B1 (Comparator) + B2 (Labeler) + B3 (Critic)
- **Core Concern Finder / Main Concern Proposer** → unificados en A4/B4 (Main Concern Verifier) con HITL
- **Flujo de datos**: los `extracted_incidents` son el nuevo artefacto intermedio entre Segmentación y Síntesis
- **HITL gates**: A3 (cada 3 docs, confirmar población), A4 (cada 3 docs, confirmar patrón de interés), B4 (cada 3 docs, refinar patrón de interés)

### 9.3 Orden de implementación

1. **Migraciones 013-016** (tablas nuevas + role_prompt)
2. **Agentes 1-5** (incident_extractor, comparator, labeler, critic, verifier)
3. **Refactor workers/heavy/tasks.py** (nuevo flujo A0→A1→A2→A3→A4, luego B1→B2→B3→B4)
4. **HITL API endpoints** (population review, pattern of interest review)
5. **Frontend HITL modals** (PopulationReviewModal, MainConcernReviewModal)
6. **Deprecación de agentes antiguos** (mantener archivos, marcar como legacy)

---

## 10. Parámetros hardcodeados — diagnóstico y plan de cambio

### 10.1 Principio

El sistema es modular respecto al `object_of_study`. Lo que Glaser llama "main concern" es solo una de las configuraciones posibles. El término genérico que unifica todas las variantes es **patrón de interés** (pattern of interest). Sin embargo, múltiples agentes y configuraciones tienen valores hardcodeados que asumen `object_of_study = "concern"` y `coding_style = "gerundio"`. Esta sección los documenta y especifica cómo deben adaptarse.

### 10.2 Mapeo: object_of_study → patrón de interés y estilo de codificación

| object_of_study | El patrón de interés es… | Estilo de codificación sugerido | Ejemplo |
|-----------------|--------------------------|-------------------------------|---------|
| `concern` | Preocupación central (main concern) | Gerundios de procesamiento | "Manteniendo relevancia profesional ante la IA" |
| `emotion` | Emoción central recurrente | Gerundios de sentir | "Sintiendo culpa por delegar" |
| `behavior` | Conducta central recurrente | Gerundios de acción | "Evadiendo responsabilidades" |
| `discourse` | Discurso central recurrente | Gerundios o nominalización | "Justificándose ante pares" |
| `identity` | Trabajo identitario central | Gerundios o in-vivo | "Negociando pertenencia al gremio" |

### 10.3 Parámetro 1: Estilo de codificación (`coding_style`)

**Dónde está hardcodeado "gerundio":**

| Archivo | Línea/Lugar | Qué dice | Debería ser |
|---------|-------------|----------|-------------|
| `project.py` | `DEFAULT_POPULATION_ASSUMPTION` | `"hábitos hipotéticos de comportamiento que procesan preocupaciones similares o más amplias en la vida diaria del entrevistado"` | Debe adaptarse al `object_of_study`. Si `emotion`, debería decir `"patrones emocionales recurrentes que estructuran la experiencia del entrevistado"`. |
| `agents/quality/scorer.py` | `evaluate_codes_algorithmic(coding_style="gerundio")` | Default `"gerundio"` | Debe leer `coding_style` de `population_assumption.coding_styles[0]` |
| `agents/self_refiner.py` | `coding_style = kwargs.get("coding_style", "gerundio")` | Default `"gerundio"` | Debe leer de config del proyecto |
| `deepseek_pro/a2_process_identifier.md` | `process_description` schema | `"expresado como gerundio"` | Debe decir `"expresado como {coding_style} (según configuración del proyecto)"` |
| `deepseek_pro/agrupador.md` | System prompt | `"Usa gerundios"`, `"LABEL en gerundio"` | Debe decir `"Usa {coding_style}"` |
| `deepseek_pro/b2_critic.md` | System prompt | `"precisión del GERUNDIO"`, `"nuevo gerundio"` | Debe adaptarse al estilo configurado |
| `deepseek_pro/b2b_generate_codes.md` | description | `"Genera códigos en gerundio"` | Debe adaptarse al estilo configurado |
| `deepseek_pro/clusterizador_informado.md` | System prompt | `"gerundio nuevo"` | Debe adaptarse al estilo configurado |
| `deepseek_pro/rename_suggester.md` | System prompt | `"Debe usar gerundios"` | Debe adaptarse al estilo configurado |

**Solución:** `coding_styles.py` ya soporta 6 estilos (gerundio, in_vivo, nominalización, paráfrasis, tema-subtema, causal) y el endpoint `PUT /projects/{id}/config/coding-styles` ya existe. Falta inyectar `{coding_style_instruction}` en todos los prompts listados arriba, usando `get_combined_instruction(coding_styles)`.

### 10.4 Parámetro 2: "Main concern" como término no modular

**Dónde está hardcodeado "main concern" / "preocupación central":**

| Archivo | Qué dice | Debería adaptarse a |
|---------|----------|---------------------|
| `deepseek_pro/main_concern_proposer.md` | `"preocupación central (main concern)"`, campo `main_concern` | Campo `pattern_of_interest`. Descripción: `"Patrón de interés central. Si object_of_study='concern', equivale al 'main concern' de Glaser."` |
| `deepseek_pro/main_concern_critic.md` | `"candidatos a preocupación central"`, `"main concern"` | Cambiar a `"candidatos a patrón de interés"` |
| `deepseek_pro/core_emergence_proposer.md` | `"PROCESAMIENTO DEL MAIN CONCERN"`, `"relación con el main concern"`, campo `main_concern` | Cambiar a `"RELACIÓN CON EL PATRÓN DE INTERÉS"`, campo `pattern_of_interest` |
| `deepseek_pro/clusterizador_informado.md` | `"Main concern: {main_concern}"` | Cambiar a `"Patrón de interés: {pattern_of_interest}"` |
| `deepseek_pro/prime_mover_extractor.md` | `"prime_mover"`, `"preocupación"` | Cambiar a `"pattern_of_interest"`, `"patrón de interés"` |
| `deepseek_pro/a2_process_identifier.md` | `"proceso central que este entrevistado intenta resolver"` | Asume `concern`. Debería decir `"patrón recurrente que estructura la experiencia de este entrevistado (según object_of_study)"` |

### 10.5 Parámetro 3: Las 4 preguntas de Glaser en el Incident Extractor

La pregunta 4 del `incident_extractor` (A1): `"¿Cuál es la preocupación principal del participante?"` asume `object_of_study = "concern"`.

| object_of_study | Pregunta 4 |
|-----------------|------------|
| `concern` | "¿Cuál es la preocupación principal del participante?" |
| `emotion` | "¿Cuál es la emoción recurrente del participante?" |
| `behavior` | "¿Cuál es la conducta recurrente del participante?" |
| `discourse` | "¿Cuál es el patrón discursivo recurrente del participante?" |
| `identity` | "¿Cuál es el trabajo identitario recurrente del participante?" |

### 10.6 Parámetro 4: Constructor hardcodeado de pregunta de investigación (`DEFAULT_POPULATION_ASSUMPTION`)

`project.py` línea 9-13: `DEFAULT_POPULATION_ASSUMPTION = "hábitos hipotéticos de comportamiento que procesan preocupaciones similares o más amplias en la vida diaria del entrevistado"`

Esto asume tres cosas a la vez: `object_of_study = "concern"`, `coding_style = "gerundio"`, `temporal_frame = "present_continuous"`.

**Solución:** Una función `get_default_population_assumption(object_of_study, temporal_frame)` que genere el texto apropiado. Si el investigador no configura nada, el default actual es razonable para `concern + present_continuous`. Para otras configuraciones, debe adaptarse.

### 10.7 Parámetro 5: Formato de "jot" en el Incident Extractor

El `incident_extractor` (A1) produce un `jot` de "1-2 palabras, gerundio". Esto es correcto para `coding_style = "gerundio"`, pero debería adaptarse:

| coding_style | Formato del jot |
|-------------|-----------------|
| `gerundio` | 1-2 palabras, verbo en -ando/-iendo |
| `in_vivo` | Cita textual del participante entre comillas |
| `nominalización` | Sustantivo abstracto (-ción, -miento, -dad) |

### 10.8 Parámetro 6: Población generalizable (`population_generalizer`)

**Problema:** El sistema asume que el investigador proporciona una población ya generalizable. Pero los investigadores frecuentemente describen su población en términos muy específicos: "los pobladores del asentamiento humano X", "los alumnos del colegio Y", "los médicos del hospital Z". El sistema necesita una población con **alcance teórico** — suficientemente abstracta para que los hallazgos sean transferibles.

**Solución:** Un agente FLASH (`population_generalizer`) que se ejecuta automáticamente al crear el proyecto:

```
Usuario describe:  "los pobladores del asentamiento humano 7 de Octubre"
     │
     ▼
population_generalizer (FLASH):
  • Detecta el nivel de especificidad
  • Propone generalización con alcance teórico
  • Preserva la descripción original como contexto
     │
     ▼
Sistema usa:       "habitantes de asentamientos humanos marginales
                    de Lima Metropolitana en situación de pobreza urbana"
```

**Especificación del agente:**

| Campo | Valor |
|-------|-------|
| **Nombre** | `population_generalizer` |
| **Tier** | FLASH |
| **Input** | `raw_population_description` (texto libre del usuario) |
| **Output** | `generalized_population` (descripción con alcance teórico), `spatial_frame` (inferido), `temporal_frame` (inferido), `generalization_rationale` |
| **Se ejecuta** | Una vez, al crear el proyecto |
| **Reglas** | No puede ser MÁS específica que la original. Debe ser suficientemente abstracta para validez teórica. El usuario puede editarla. |

**Ejemplos:**

| Descripción cruda (usuario) | Descripción generalizada (sistema) |
|----------------------------|-------------------------------------|
| "los pobladores del AAHH 7 de Octubre" | "habitantes de asentamientos humanos marginales de Lima Metropolitana" |
| "los alumnos del colegio San Agustín" | "estudiantes de secundaria en colegios privados de clase media limeña" |
| "los médicos del hospital regional de Huancayo" | "profesionales de la salud en hospitales públicos regionales del Perú" |
| "periodistas de 3 redacciones en España y México" | "periodistas en activo en medios hispanohablantes con presencia digital" |

**Por qué es necesario:** Sin generalización, el análisis CGT no puede aspirar a teoría sustantiva transferible. Una población demasiado específica produce hallazgos que solo aplican a ese caso. La generalización permite que los hallazgos sean teóricamente relevantes para una clase de casos.

### 10.9 Cambios necesarios en JSON Schemas (unificación terminológica)

**Archivo: `deepseek_pro/prime_mover_extractor.md`**

```diff
- "required": ["prime_mover", "confidence"],
+ "required": ["pattern_of_interest", "confidence"],
  "properties": {
-   "prime_mover": {
+   "pattern_of_interest": {
      "type": "string",
-     "description": "Patron recurrente principal expresado como gerundio."
+     "description": "Patrón de interés recurrente expresado según coding_style. Si object_of_study='concern', equivale al 'main concern' de Glaser."
    },
```

**Archivo: `deepseek_pro/main_concern_proposer.md`**

```diff
- "required": ["main_concern", ...],
+ "required": ["pattern_of_interest", ...],
  "properties": {
-   "main_concern": {
+   "pattern_of_interest": {
      "type": "string",
-     "description": "Preocupación central expresada como gerundio..."
+     "description": "Patrón de interés central expresado según coding_style. Si object_of_study='concern', equivale al 'main concern' de Glaser."
    },
```

### 10.10 Cambios necesarios en código

**Archivo: `workers/heavy/tasks.py` — `_extract_prime_mover()`**

```diff
  return {
-   "prime_mover": response.get("prime_mover", ""),
+   "pattern_of_interest": response.get("pattern_of_interest", ""),
    ...
  }
```

```diff
  if len(baseline) < 2:
-   return {"prime_mover": "", "insufficient_data": True}
+   return {"pattern_of_interest": "", "insufficient_data": True}
```

**Archivo: `workers/heavy/tasks.py` — `process_document_agents_a()`**

```diff
- results["prime_mover"] = pm_result
+ results["pattern_of_interest"] = pm_result
- if pm_result and pm_result.get("prime_mover"):
+ if pm_result and pm_result.get("pattern_of_interest"):
```

**Archivo: `workers/heavy/tasks.py` — `task_a14_main_concern()`**

```diff
- "prime_movers_per_document": prime_movers_text,
+ "pattern_of_interests_per_document": pattern_of_interests_text,
```

### 10.11 Plan de cambios — orden de prioridad

| Prioridad | Cambio | Archivos afectados | Esfuerzo |
|-----------|--------|-------------------|----------|
| **1** | Crear `population_generalizer` (FLASH) + integrar en Fase 0 | `deepseek_flash/population_generalizer.md`, `projects.py` | BAJO |
| **2** | Unificar campo `pattern_of_interest` en JSON schemas | `main_concern_proposer.md`, `main_concern_critic.md`, `core_emergence_proposer.md`, `clusterizador_informado.md`, `prime_mover_extractor.md` | MEDIO |
| **3** | Inyectar `{coding_style_instruction}` en prompts que hardcodean "gerundio" | `a2_process_identifier.md`, `agrupador.md`, `b2_critic.md`, `b2b_generate_codes.md`, `clusterizador_informado.md`, `rename_suggester.md` | MEDIO |
| **4** | Adaptar `DEFAULT_POPULATION_ASSUMPTION` a `object_of_study` | `project.py` | BAJO |
| **5** | Adaptar las 4 preguntas de Glaser en A1 + formato de jot | `incident_extractor_v2.md` | BAJO |

### 10.12 Lo que NO cambia

- **Nombre de archivos de prompt:** `main_concern_proposer.md`, `prime_mover_extractor.md` se mantienen (referencia histórica)
- **Columna BD:** `document_processes.prime_mover` se mantiene (nombre interno)
- **Función:** `_extract_prime_mover()` se mantiene
- **Prompt agent_id:** se mantienen

---

## 11. Análisis de tipos de datos (Glaser data types) en el pipeline

### 11.1 Diagnóstico

El sistema clasifica cada segmento con `tipo_dato_glaser` (A0: `glaser_data_classifier`, FLASH). Sin embargo, esta clasificación **no se usa sistemáticamente** en los agentes downstream. Actualmente solo A2 (`core_pattern_extractor`) filtra por `baseline_data`. El resto de agentes ignora el tipo de dato.

Esto es un problema porque:

- `properline_data` (deseabilidad social) parece revelar preocupaciones pero en realidad revela normas sociales — no la experiencia real del participante.
- `interpreted_data` (opinión forzada) es útil para entender el discurso público del grupo, pero no para encontrar el patrón de interés latente.
- `vague_data` (evasión) puede ser señal de un tema tabú — no debe descartarse, sino marcarse como anomalía.

### 11.2 Dónde debe inyectarse el tipo de dato

| Agente | Usa tipo de dato | Cómo |
|--------|-----------------|------|
| **A0** | Produce | Clasifica cada segmento |
| **A1 (incident_extractor)** | ✅ **Filtra** | Solo recibe `baseline_data`. `properline` e `interpreted` se archivan. `vague` se marca como anomalía. |
| **A2 (core_pattern_extractor)** | ✅ **Filtra** | Solo usa `baseline_data`. El patrón de interés emerge de experiencia espontánea, no de opinión. |
| **B1 (incident_comparator)** | ⚠️ **Pondera** | Compara incidentes de todos los tipos, pero `baseline_data` tiene peso 1.0, `properline` 0.5, `interpreted` 0.3. Los incidentes `vague` se excluyen de la comparación. |
| **B2 (pattern_labeler)** | ⚠️ **Informa** | Recibe el `glaser_data_type` de cada incidente en el grupo. Si un grupo tiene mayoría `properline`, el labeler debe advertir: "Este patrón podría reflejar deseabilidad social, no experiencia real". |
| **B3 (label_critic)** | ⚠️ **Evalúa** | Si una etiqueta se basa principalmente en `properline_data`, el critic debe ser más estricto (exigir más evidencia convergente). |
| **A4/B4 (core_pattern_verifier)** | ✅ **Prioriza** | Al evaluar convergencia de patrones, los patrones basados en `baseline_data` tienen más peso que los basados en `interpreted_data`. |
| **SaturationGapAnalyzer** | ⚠️ **Informa** | Muestra distribución de tipos de dato por categoría. Si una categoría tiene 80% `properline`, su saturación es sospechosa (puede estar saturada de norma social, no de experiencia). |

### 11.3 Regla general

```
BASELINE_DATA → Oro. Usar para extraer patrones, verificar main concern, y饱和ar.
PROPERLINE_DATA → Plata. Usar para entender normas del grupo. No usar para饱和ar.
INTERPRETED_DATA → Bronce. Usar para contexto. No usar para extraer patrones.
VAGUE_DATA → Anomalía. Marcar, no descartar. Puede señalar temas tabú.
```

---

## 12. Dependencias entre agentes — análisis de contexto

### 12.1 Principio rector

En CGT hay una tensión fundamental entre **emergencia** (requiere aislamiento) y **síntesis** (requiere contexto). Un agente que encuentra patrones NO debe ver categorías existentes — eso sesga hacia la confirmación. Un agente que sintetiza DEBE ver todo lo acumulado — sin contexto no puede integrar.

### 12.2 Matriz de dependencias

| # | Agente | Fase | ¿Necesita contexto acumulado? | ¿Qué NO debe ver? | Justificación CGT |
|---|--------|------|------------------------------|-------------------|-------------------|
| A0 | `glaser_data_classifier` | Pre-codificación | ❌ Nada | Nada | Clasificación pura. El tipo de dato es una propiedad intrínseca del segmento. |
| A1 | `incident_extractor` | Hallazgo | ❌ **AISLADO** | Otros documentos, categorías existentes, patrones previos | **Emergencia.** Si ve categorías existentes, fuerza el incidente nuevo a encajar en moldes viejos (sesgo de confirmación). Solo debe ver: `object_of_study`, `coding_style`, y el segmento actual. |
| A2 | `core_pattern_extractor` | Hallazgo | ❌ **AISLADO** | Otros documentos, A1 output de otros docs, categorías | **Emergencia.** El patrón de interés de este entrevistado debe emerger de SUS datos espontáneos. Ver otros documentos contaminaría con patrones ajenos. |
| A3 | `population_context` (A1 original) | Síntesis poblacional | ✅ **ACUMULATIVO** | Nada (necesita ver todo) | **Síntesis.** La población se entiende comparando. Necesita `surprising_details` acumulados de todos los documentos previos. |
| A4 | `core_pattern_verifier` | Verificación | ✅ **COMPLETO** | Nada | **Síntesis.** Debe ver TODOS los patrones individuales (A2) + población (A3) + objeto de estudio para detectar convergencia. |
| B1 | `incident_comparator` | Comparación | ❌ **AISLADO** | Categorías existentes, etiquetas previas | **Emergencia.** Compara incidentes CRUDOS. Si ve categorías existentes, agrupa por similitud superficial a etiquetas viejas en lugar de por intercambiabilidad real. Es el equivalente al "sorting" físico de Glaser: solo ves las tarjetas, no las etiquetas que les pusiste antes. |
| B2 | `pattern_labeler` | Síntesis | ✅ **GRUPO** | Nada (necesita ver el grupo completo) | **Síntesis.** Recibe los grupos de B1. Necesita ver TODOS los incidentes del grupo para proponer una etiqueta que los capture a todos. Pero NO necesita ver otros grupos (cada grupo se etiqueta independientemente). |
| B3 | `label_critic` | Crítica | ✅ **GRUPO + FUENTE** | Nada | **Síntesis crítica.** Evalúa la etiqueta de B2 contra los incidentes fuente. Necesita ver ambos. Puede dialogar con B2 (bucle generativo-crítico). |
| B4 | `core_pattern_verifier` (2° pass) | Verificación | ✅ **COMPLETO** | Nada | **Síntesis final.** Recibe patrones individuales (A2) + categorías emergentes (B2) + población (A3). Tiene la foto más completa. |

### 12.3 Visualización de dependencias

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONTEXTO AISLADO (emergencia)                 │
│                                                                  │
│  A0 ← [segmento]                                                │
│  A1 ← [segmento baseline + object_of_study + coding_style]      │
│       🚫 NO ve: otros docs, categorías, patrones previos         │
│                                                                  │
│  A2 ← [todos los baseline del documento + object_of_study]      │
│       🚫 NO ve: otros docs, A1 de otros docs, categorías         │
│                                                                  │
│  B1 ← [TODOS los extracted_incidents de TODOS los docs]         │
│       🚫 NO ve: categorías existentes, etiquetas previas         │
│       ✅ SÍ ve: glaser_data_type (para ponderar)                 │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                    CONTEXTO COMPLETO (síntesis)                   │
│                                                                  │
│  A3 ← [surprising_details acumulados de TODOS los docs previos] │
│       ✅ SÍ ve: todo el contexto poblacional acumulado           │
│                                                                  │
│  A4 ← [A2 patterns + A3 population + object_of_study]           │
│       ✅ SÍ ve: todos los patrones individuales + población      │
│                                                                  │
│  B2 ← [incident_groups de B1 + object_of_study + coding_style]  │
│       ✅ SÍ ve: el grupo completo de incidentes                  │
│                                                                  │
│  B3 ← [B2 labels + source incidents]                            │
│       ✅ SÍ ve: etiquetas + datos fuente para evaluar            │
│                                                                  │
│  B4 ← [A2 + B2 + A3 + object_of_study]                          │
│       ✅ SÍ ve: todo — patrones, categorías, población           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 12.4 Lo que el diagrama actual viola

| Violación | Dónde ocurre | Corrección |
|-----------|-------------|------------|
| B2a (Indicator Extractor) ve códigos existentes | `b2a_extract_indicators` recibe `existing_codes` como contexto | A1 no debe recibir `existing_codes`. Debe estar aislado. |
| B2b (Code Generator) compara con categorías previas | `b2b_generate_codes` recibe `existing_codes` en el prompt | B1 (comparator) debe trabajar con incidentes crudos, sin ver categorías. B2 (labeler) solo ve los grupos de B1. |
| A1 (Population Context) se ejecuta en paralelo con A2 | El diagrama muestra A1 y A2 en la misma "FASE A" sin orden | A2 debe ejecutarse primero (por documento). A3 se ejecuta cada 3 documentos, usando A2 acumulados. |
| Core Concern Finder recibe categorías existentes | `core_concern_finder` usa `all_open_codes` | A4 debe ver patrones individuales (A2) + población (A3), no categorías pre-etiquetadas. Las categorías entran en B4. |

---

## 13. Análisis del sistema multiagente actual — patrones reutilizables

### 13.1 Arquitectura actual

El sistema actual implementa un pipeline multiagente con RAG que opera en dos fases:

```
FASE A (por documento, secuencial):
  A1 (Population Context) → A2 (Process Identifier) → A3 (Sense Maker, desde doc 3)
  + C06 (Prime Mover Extractor)

FASE B (cross-document, triggered ≥3 docs):
  B1 (Sampling Distiller) → B2a (Indicator Extractor, FLASH)
  → B2b (Code Generator, PRO) → B2.5 (Code Critic, PRO)
  → B2.5 Grounding (algorithmic + pgvector) → B3 (Hypothesis Generator)
```

### 13.2 Patrones de ejecución que benefician nuestro nuevo diseño

#### 13.2.1 Cadena FLASH→PRO (B2a→B2b) → nuestra cadena A0→A1

**Cómo funciona ahora:**
- `b2a_extract_indicators` (FLASH) pre-procesa segmentos, extrae indicadores crudos
- `b2b_generate_codes` (PRO) recibe indicadores ya filtrados y genera códigos con razonamiento cualitativo
- La separación FLASH/PRO ahorra costos: FLASH filtra lo obvio, PRO razona sobre lo filtrado

**Cómo se mapea a nuestro diseño:**
- A0 (`glaser_data_classifier`, FLASH) → pre-clasifica segmentos por tipo de dato. Barato, determinista.
- A1 (`incident_extractor`, PRO) → recibe SOLO baseline_data ya filtrado. Aplica las 4 preguntas de Glaser con razonamiento cualitativo.
- **Patrón a preservar:** FLASH pre-procesa y filtra → PRO razona sobre lo filtrado. Este patrón DEBE mantenerse para A0→A1 y para el `corpus_scanner` (FLASH) → `property_sampler` (PRO).

#### 13.2.2 Memo-based storage (B1 → memos) → nuestro ghost-blob system

**Cómo funciona ahora:**
- B1 (`sampling_distiller`) genera dimensiones de muestreo y las guarda como `memos` (tipo='MUESTREO')
- B3 (`hypothesis_generator`) guarda hipótesis en tabla `hypotheses` con `status='candidate'`
- Los memos son persistentes y trazables — cada uno tiene `proyecto_id`, `autor_id`, `tipo`, `estado`

**Cómo se mapea a nuestro diseño:**
- Los memos de hipótesis (B3) se convierten en **ghost-blobs** en el Theoretical Playground
- `GhostConnector.generate_ghost_blobs()` ya lee la tabla `memos` y clasifica con `ghost_blob_mapper` (PRO)
- Los memos de muestreo (B1) alimentan el `EmergentSampler`
- **Patrón a preservar:** toda salida de agente que sea una hipótesis o sugerencia debe persistir como memo. Esto permite trazabilidad completa y evita perder trabajo analítico.

#### 13.2.3 RAG enrichment de códigos (B2b post-processing) → nuestro evidence mapping

**Cómo funciona ahora:**
- `_enrich_codes_with_evidence()` toma cada código generado por B2b
- Para cada código: `search_segments(code_name + definition, proyecto_id, top_k=8)` usando RRF (semantic + lexical fusion)
- Filtra segmentos con score ≥ 0.5
- Agrupa por `documento_id` único
- Calcula `puntaje_relevancia = COUNT(DISTINCT documentos con evidencia)`
- Adjunta `evidence: [{documento, documento_id, segmentos}]` a cada código

**Cómo se mapea a nuestro diseño:**
- B2 (`pattern_labeler`) debe enriquecer cada etiqueta propuesta con evidencia textual del corpus
- `conceptual_elaborator` (T07) ya usa incidentes para mostrar evidencia convergente/divergente
- El `ElaborationPanel` muestra evidencia textual en el frontend
- **Patrón a preservar:** RAG enrichment como paso post-generación. Todo código/etiqueta/categoría debe tener evidencia textual rastreable. La función `search_segments` con RRF ya existe y es reutilizable.

#### 13.2.4 Versioned population context → nuestro A3

**Cómo funciona ahora:**
- `population_contexts` es una tabla versionada: cada ejecución de A1 inserta una nueva fila con `version N+1`
- El contexto poblacional es ACUMULATIVO: cada nueva versión integra lo anterior con lo nuevo
- Los campos `surprising_details`, `language_patterns`, `data_production_context` crecen orgánicamente

**Cómo se mapea a nuestro diseño:**
- A3 (Population Context Update) usa exactamente este patrón
- Se ejecuta cada 3 documentos
- El HITL gate de A3 ("¿la población sigue siendo la correcta?") es nuevo — pero la infraestructura de versionado ya existe
- **Patrón a preservar:** versionado acumulativo con inserción (no update). Esto permite auditoría completa de cómo evolucionó la comprensión de la población.

#### 13.2.5 Step checkpoints + Redis logging → nuestros HITL gates

**Cómo funciona ahora:**
- `_plog()` empuja logs a Redis (`pipeline_logs:{project_id}`) con TTL de 1 hora
- `task_step_checkpoints` permite resumir tareas multi-step
- `AbortableTask` permite cancelar workers

**Cómo se mapea a nuestro diseño:**
- Los HITL gates (A3, A4, B4) necesitan notificar al frontend que el pipeline está pausado esperando decisión
- La infraestructura Redis pub/sub ya existe para esto
- `interrupt()` de LangGraph ya se usa en `node_hitl_review`
- **Patrón a preservar:** Redis como canal de notificación para HITL. El patrón de logging ya está — solo necesita extenderse para eventos HITL.

#### 13.2.6 Pipeline tracking (processing_states) → nuestro tracking de fases

**Cómo funciona ahora:**
- `processing_states` rastrea qué pasos se completaron para cada entidad (documento, segmento, código)
- Campos: `entity_type`, `entity_id`, `step` (ej: 'segmented', 'coded', 'synthesized')

**Cómo se mapea a nuestro diseño:**
- Necesitamos tracking de qué documentos pasaron por A0, A1, A2, y cuáles están pendientes
- Necesitamos tracking de qué categorías pasaron por B2, B3
- **Patrón a preservar:** `processing_states` como tabla de checkpoint. Extender con nuevos steps: `glaser_classified`, `incidents_extracted`, `core_pattern_extracted`, `compared`, `labeled`, `critiqued`.

### 13.3 Lo que el sistema actual hace bien y debemos preservar

| Patrón | Dónde está | Por qué preservarlo |
|--------|-----------|-------------------|
| Cadena FLASH→PRO | B2a→B2b | Ahorra costos. FLASH filtra, PRO razona. Aplicar a A0→A1, corpus_scanner→property_sampler |
| Memo-based storage | B1, B3 | Trazabilidad completa. Todo output de agente que sea hipótesis/sugerencia → memo. Base de ghost-blobs. |
| RAG enrichment | `_enrich_codes_with_evidence` | Evidencia textual para cada código. `search_segments` con RRF ya existe. Reutilizar en B2. |
| Versioned population context | `population_contexts` | Acumulativo, auditable. Base de A3. |
| Redis pipeline logging | `_plog()` | Notificaciones en tiempo real. Extender para HITL gates. |
| Processing states | `processing_states` | Checkpointing de pipeline. Extender con nuevos steps. |
| SelfRefinement loop | `self_refiner.py` | Bucle generativo-crítico. Mismo patrón que B2↔B3. Ya existe la infraestructura. |
| Algorithmic checks | `algorithmic_checks.py` | Validación sin LLM (regex para coding_style, deduplication). Ahorra costos. Usar en B3 para pre-filtrar antes de llamar al critic PRO. |

### 13.4 Lo que el sistema actual NO hace y debemos construir

| Ausencia | Impacto | Solución en nuestro diseño |
|----------|---------|---------------------------|
| Sin separación hallazgo/comparación | B2a y B2b reciben `existing_codes` → sesgo de confirmación | A1 y B1 aislados de categorías existentes |
| Sin filtro baseline/properline en coding | Todos los segmentos se codifican igual | A0 filtra → solo baseline_data a A1 |
| Sin HITL en decisiones teóricas | Main concern y core category se calculan sin confirmación | A3, A4, B4 con HITL gates |
| Sin cycleo de feedback para gaps | TheoSampler no alerta sobre ejes vacíos | SaturationGapAnalyzer + hitl_gap_review |
| Sin población generalizable | DEFAULT_POPULATION_ASSUMPTION hardcodeado | population_generalizer (FLASH) en Fase 0 |

---

## 14. Análisis de CoT (Chain of Thought) en el sistema actual

### 14.1 Cómo funciona ahora

El sistema actual tiene **tres capas de razonamiento**:

```
CAPA 1: CoT interno del modelo (DeepSeek V4 Pro)
  DeepSeek V4 Pro razona internamente antes de responder.
  El campo reasoning_content se extrae y preserva.
  PERO: response_format=json_object puede SUPRIMIR esta capacidad.

CAPA 2: SelfRefinementLoop (orquestación)
  Generate (PRO) → AlgorithmicCheck (no LLM) → Critic (FLASH) → Refine
  Es un CoT explícito a nivel de orquestación.
  El modelo ve su output anterior + feedback del critic.

CAPA 3: Pipeline secuencial (agentes encadenados)
  A1 → A2 → A3 → B1 → B2a → B2b → B2.5 → B3
  Cada agente recibe el contexto del anterior.
  Es un CoT implícito a nivel de arquitectura.
```

### 14.2 Problema: `response_format=json_object` suprime el razonamiento

**Evidencia:** `_call_llm()` siempre usa `response_format={"type": "json_object"}` (línea 459). Esto fuerza al modelo a producir JSON directamente, sin espacio para razonamiento explícito en el output.

**Impacto en CGT:**
- DeepSeek V4 Pro funciona MEJOR cuando puede razonar antes de emitir JSON. El `reasoning_content` es donde ocurre el pensamiento cualitativo.
- Para tareas PRO (generación de códigos, síntesis, verificación de patrones), el razonamiento paso a paso es METODOLÓGICAMENTE necesario: el agente debe justificar por qué dos incidentes son intercambiables, por qué una etiqueta captura el patrón, etc.
- Para tareas FLASH (clasificación, extracción), el JSON directo es adecuado.

### 14.3 Dónde conviene CoT y dónde no

| Agente | Tier | ¿CoT? | Justificación |
|--------|------|-------|---------------|
| A0 (`glaser_data_classifier`) | FLASH | ❌ No | Clasificación determinista. 4 categorías. No necesita razonar. |
| A1 (`incident_extractor`) | PRO | ✅ **Sí** | Las 4 preguntas de Glaser requieren razonamiento cualitativo. "¿Qué está sucediendo realmente aquí?" no se responde con pattern matching. |
| A2 (`core_pattern_extractor`) | PRO | ✅ **Sí** | Sintetizar el patrón de interés de un documento requiere integrar múltiples incidentes. Es razonamiento abductivo. |
| A3 (`population_context`) | PRO | ✅ **Sí** | Detectar surprising_details requiere comparar lo esperado con lo observado. Razonamiento contrafáctico. |
| A4 (`core_pattern_verifier`) | PRO | ✅ **Sí** | Evaluar convergencia de patrones requiere sopesar evidencia a favor y en contra. |
| B1 (`incident_comparator`) | PRO | ✅ **Sí** | Constant comparative method: ¿son estos dos incidentes el mismo patrón subyacente? Requiere razonamiento analógico. |
| B2 (`pattern_labeler`) | PRO | ✅ **Sí** | Proponer etiqueta abstracta desde incidentes concretos. Razonamiento inductivo. |
| B3 (`label_critic`) | PRO | ✅ **Sí** | Evaluar si una etiqueta captura el patrón subyacente. Razonamiento evaluativo. |
| `corpus_scanner` | FLASH | ❌ No | Búsqueda de patrones en texto. Pattern matching. |
| `property_sampler` | PRO | ✅ **Sí** | Sugerir muestreo externo requiere razonamiento sobre gaps. |
| `conceptual_elaborator` (T07) | PRO | ✅ **Sí** | Elaborar relación entre categorías requiere integrar evidencia convergente y divergente. |

### 14.4 El patrón SelfRefinement como CoT óptimo para CGT

El `SelfRefinementLoop` implementa un patrón que es **metodológicamente perfecto para CGT**:

```
Generate → AlgorithmicCheck → Critic → Refine
   │              │               │         │
   │              │               │         └── El modelo corrige
   │              │               └── Evaluación cualitativa (FLASH)
   │              └── Validación determinista (regex, sin LLM)
   └── Generación inicial (PRO, con CoT interno)
```

**Por qué conviene para B2↔B3:**
1. **Generate** (B2 pattern_labeler, PRO con CoT): propone etiquetas. El modelo razona internamente sobre los incidentes del grupo.
2. **AlgorithmicCheck** (sin LLM): valida que la etiqueta cumpla el `coding_style` (regex), que no haya duplicados. Barato.
3. **Critic** (B3 label_critic, FLASH): solo se ejecuta si el algorithmic check falla o si hay ambigüedad cualitativa. Evalúa grounding, abstracción, precisión.
4. **Refine**: el modelo recibe el feedback del critic y mejora la etiqueta.

**Ahorro:** El paso 2 (algorithmic) evita llamar al LLM critic en ~60% de los casos (cuando el formato es correcto). El paso 3 (FLASH) es más barato que re-ejecutar el PRO.

### 14.5 Recomendación: dual-mode CoT

```python
# Propuesta de configuración por tier
COT_CONFIG = {
    "PRO": {
        "response_format": None,        # Sin json_object — dejar que el modelo razone
        "extract_json_from_reasoning": True,  # Extraer JSON del bloque final
    },
    "FLASH": {
        "response_format": {"type": "json_object"},  # JSON directo, sin razonamiento
        "temperature": 0.1,
    },
}
```

**Para PRO:** Eliminar `response_format=json_object`. Dejar que DeepSeek V4 Pro razone internamente (el `reasoning_content` se preserva). Usar un parser que extraiga el JSON del final de la respuesta (después del razonamiento). Esto duplica la calidad en tareas de síntesis cualitativa.

**Para FLASH:** Mantener `response_format=json_object`. Son tareas de clasificación/extracción donde el razonamiento no aporta y solo aumentaría costos.

### 14.6 El CoT ya existe donde más se necesita

El `SelfRefinementLoop` ya implementa el patrón Generate→Critic→Refine que nuestro diseño requiere para B2↔B3. La infraestructura está lista. Solo necesita:
1. Nuevos `generate_prompt_id` y `critic_prompt_id` para B2 y B3
2. Desactivar `json_object` en PRO para permitir razonamiento interno
3. Mantener el algorithmic check como filtro barato pre-critic

---

## 15. Análisis de RAG — dónde y cómo usarlo en el nuevo sistema

### 15.1 Cómo funciona ahora

El RAG actual (`RAGService`, `backend/app/services/rag.py`) es sofisticado:

- **RRF (Reciprocal Rank Fusion):** fusiona rankings semántico (HNSW sobre embeddings TEI) y léxico (BM25 sobre ts_vector). Sin normalizar scores.
- **MMR opcional:** reordena para diversidad sobre ≤ 50 candidatos.
- **Tres modos:** `rrf` (default), `semantic` (solo cosine), `lexical` (solo BM25).

Se usa en **2 lugares** concretos:

| Uso | Dónde | Cuándo | Propósito |
|-----|-------|--------|-----------|
| **Evidence enrichment** | `_enrich_codes_with_evidence()` en `agents_b.py` | Después de B2b (code generation) | Para cada código nuevo, busca segmentos en el corpus que lo respalden. Calcula `puntaje_relevancia = COUNT(DISTINCT docs con evidencia)`. |
| **Agentic hypothesis gen** | `b3_generate_hypotheses_agentic()` en `agents_b.py` | Solo si `AGENTIC_MODE=true` | Antes de generar hipótesis, el agente puede llamar `search_segments` como tool para verificar evidencia. |

### 15.2 Principio rector: RAG vs. Contexto Acumulativo

En CGT hay una distinción fundamental:

```
RAG = "Volver a los datos crudos para buscar evidencia adicional"
     Útil cuando: necesitás verificar una afirmación contra el corpus completo
     Costoso: embedding + RRF query por cada búsqueda
     Riesgo: loop infinito de verificación

CONTEXTO ACUMULATIVO = "Usar lo que ya extrajimos y sintetizamos"
     Útil cuando: el trabajo analítico previo ya capturó los patrones
     Barato: queries SQL sobre tablas estructuradas
     Seguro: no reintroduce sesgo de búsqueda
```

**Regla general:** Si el agente ya recibió los datos que necesita (incidentes extraídos, patrones sintetizados, contexto poblacional), **no necesita RAG**. Solo usar RAG cuando el trabajo previo NO capturó lo que se busca.

### 15.3 Matriz: dónde RAG, dónde contexto acumulativo

| Agente | ¿Necesita RAG? | ¿Por qué? | ¿Qué usar en su lugar? |
|--------|---------------|-----------|----------------------|
| **A0** (glaser_data_classifier) | ❌ No | Clasifica un segmento individual. No necesita buscar en el corpus. | Nada — es autónomo |
| **A1** (incident_extractor) | ❌ No | Trabaja sobre UN segmento baseline. Debe estar AISLADO. Buscar en el corpus sesgaría. | `object_of_study` + `coding_style` |
| **A2** (core_pattern_extractor) | ❌ No | Trabaja sobre UN documento. Debe estar AISLADO. | Baseline segments del documento actual |
| **A3** (population_context) | ❌ No | Usa contexto acumulativo versionado (`population_contexts`). | Tabla `population_contexts` (SQL, barato) |
| **A4** (core_pattern_verifier) | ❌ No | Recibe TODOS los core_patterns + A3. Tiene todo lo necesario. | `document_processes.prime_mover` + `population_contexts` |
| **B1** (incident_comparator) | ⚠️ **Opcional** | Normalmente recibe TODOS los extracted_incidents. Pero si el investigador sospecha que hay incidentes no extraídos, podría usar RAG para buscar más. | `extracted_incidents` table. RAG solo bajo demanda del investigador. |
| **B2** (pattern_labeler) | ✅ **Sí, post-generación** | Después de etiquetar, RAG enrichment busca evidencia textual para cada etiqueta. Mismo patrón que `_enrich_codes_with_evidence`. | `search_segments(label + definition)` para evidence mapping |
| **B3** (label_critic) | ❌ No | Evalúa etiquetas contra los incidentes fuente del grupo. Ya tiene los datos. | `incident_groups` + `extracted_incidents` |
| **B4** (core_pattern_verifier 2° pass) | ❌ No | Recibe A2 + B2 + A3. Es el punto de máxima síntesis. | Todo acumulado |
| **conceptual_elaborator** (T07) | ✅ **Sí** | Cuando el investigador arrastra dos blobs, necesita buscar incidentes en TODO el corpus que muestren la relación (convergente/divergente). | `search_segments(cat_A + cat_B)` para evidencia |
| **rename_suggester** (T08) | ❌ No | Trabaja desde `definition_history`. Tiene todo el contexto. | `category_definition_versions` |
| **ghost_blob_mapper** (T09) | ❌ No | Mapea memos a categorías existentes. Datos ya estructurados. | `memos` + `categorias` |
| **ecosystem_gap_detector** (T10) | ❌ No | Analiza el grafo de relaciones. Estructura, no contenido. | `conceptual_relationships` + `categorias` |
| **property_sampler** (E01) | ✅ **Sí** | Busca en el corpus incidentes que manifiesten una propiedad en un extremo específico. ES su función. | `corpus_scanner` (FLASH, barato) → `property_sampler` (PRO) |
| **SaturationGapAnalyzer** (C08) | ❌ No | Analiza métricas y gaps estructurales. No busca contenido nuevo. | `saturation_metrics` + `paradigm_states` + `comparison_axes` |

### 15.4 Dónde EVITAR RAG: el riesgo del loop de verificación

El peligro más sutil del RAG en CGT es el **loop de verificación infinita**:

```
1. B2 etiqueta un grupo → RAG enrichment encuentra evidencia
2. La evidencia revela un incidente divergente → se expande la etiqueta
3. Nueva etiqueta → nuevo RAG → nueva evidencia → nueva divergencia → ...
```

**Regla de corte:** RAG se usa UNA vez por ciclo de síntesis, no iterativamente.

| Situación | ¿Usar RAG? | Alternativa |
|-----------|-----------|-------------|
| B2 acaba de etiquetar | ✅ Sí — una vez, para evidence mapping | — |
| La evidencia muestra divergencia | ❌ No volver a buscar con RAG | 🛑 **HITL**: el investigador decide si expandir la relación, acotarla, o marcar como excepción |
| A4 detecta patrones no convergentes | ❌ No buscar más datos con RAG | 🛑 **HITL**: ¿cambiar población? ¿cambiar object_of_study? ¿muestrear? |
| SaturationGapAnalyzer detecta eje vacío | ❌ No buscar en corpus con RAG | 🛑 **HITL**: `hitl_gap_review` → cargar nuevos docs o marcar limitación |
| conceptual_elaborator muestra divergencia | ❌ No re-ejecutar RAG | 🛑 **HITL**: clic en fisura dorada → expandir relación |

**Principio:** RAG informa. HITL decide. RAG no itera.

### 15.5 RAG guiado por HITL en el frontend

Los componentes del frontend ya están diseñados para que el investigador **guíe** cuándo y cómo usar RAG:

| Componente | Interacción | Cuándo usa RAG |
|-----------|------------|---------------|
| **EcosystemCanvas** | Arrastrar dos blobs juntos → menú contextual de código teórico | `conceptual_elaborator` dispara RAG para buscar evidencia convergente/divergente |
| **ElaborationPanel** (TendrilDetail) | Muestra evidencia encontrada por RAG | RAG ya se ejecutó. El panel muestra resultados. |
| **RecommendationGuide** → "Conexiones sugeridas" | Sugiere pares con alta co-ocurrencia | NO usa RAG — usa SQL sobre `codigos_segmento` para detectar co-ocurrencia |
| **RecommendationGuide** → "Ghost-blobs" | Sugiere absorción de memos | NO usa RAG — usa `ghost_blob_mapper` sobre datos estructurados |
| **RecommendationGuide** → "Zonas de neblina" | Sugiere muestreo | NO usa RAG — detecta gaps estructurales. Si el investigador acepta, va a HITL gap review. |
| **RenameModal** | Muestra sugerencias de renombre | NO usa RAG — usa `rename_suggester` sobre `definition_history` |
| **Botón "Sync gaps"** | Refresca SaturationGapAnalyzer | NO usa RAG — analiza métricas y gaps estructurales |

### 15.6 Resumen: 3 reglas para RAG en el nuevo sistema

```
REGLA 1: RAG solo cuando el contexto acumulativo es insuficiente.
         Si el agente ya recibió los datos que necesita (incidentes,
         patrones, contexto), NO usar RAG.

REGLA 2: RAG se ejecuta UNA vez por ciclo de síntesis, no iterativamente.
         La divergencia no se resuelve con más RAG — se resuelve con HITL.

REGLA 3: RAG informa. HITL decide. RAG no itera.
         El investigador es el gate entre "buscar más evidencia" y
         "tomar una decisión teórica".
```

---

## 16. Sistema relacional de referencias — trazabilidad CGT

### 16.1 La jerarquía ideal

En CGT, toda afirmación teórica debe ser trazable hasta el dato empírico que la respalda. La jerarquía es:

```
CÓDIGO TEÓRICO (theoretical_codes)
  └── RELACIÓN CONCEPTUAL (conceptual_relationships)
        └── CATEGORÍA (categorias)
              └── INCIDENTE (extracted_incidents / codigos_segmento)
                    └── SEGMENTO (segmentos)
                          └── DOCUMENTO (documentos)
```

El investigador debe poder hacer **drill-down** desde cualquier nivel: "Esta relación de proceso entre A y B → ¿qué incidentes la respaldan? → ¿en qué segmentos? → ¿de qué documentos? → mostrame la cita exacta."

### 16.2 Auditoría: qué está implementado y qué falta

#### 16.2.1 Eslabones FUERTES (FK + relationship)

| Origen | Destino | Mecanismo | Estado |
|--------|---------|-----------|--------|
| `TheoreticalCode` | `ConceptualRelationship` | FK `theoretical_code_id` + `back_populates` | ✅ Implementado |
| `ConceptualRelationship` | `TheoreticalCode` | `theoretical_code` relationship | ✅ Implementado |
| `Categoria` | `CodigoSegmento` | `codigos_segmento` relationship | ✅ Implementado |
| `CodigoSegmento` | `Segmento` | FK `segmento_id` + `segmento` relationship | ✅ Implementado |
| `Segmento` | `Documento` | FK `documento_id` + `documento` relationship | ✅ Implementado |
| `Categoria` | `CategoryDefinitionVersion` | `definition_versions` relationship | ✅ Implementado |
| `Categoria` | `ParadigmState` | `paradigm_states` relationship | ✅ Implementado |
| `ElaborationMemo` | `ConceptualRelationship` | FK `relationship_id` | ✅ Implementado |
| `ElaborationMemo` | `Categoria` | FK `category_id` | ✅ Implementado |
| `ElaborationMemo` | `Memo` | FK `memo_id` | ✅ Implementado |

#### 16.2.2 Eslabones DÉBILES (JSONB, sin FK)

| Origen | Destino | Mecanismo | Problema | Estado |
|--------|---------|-----------|----------|--------|
| `ConceptualRelationship` | `Categoria` | `category_ids` JSONB array | No es FK. No se puede hacer JOIN. La integridad referencial no está garantizada. | ⚠️ Débil |
| `ConceptualRelationship` | Incidentes | `converging_incident_ids` JSONB + `diverging_incident_ids` JSONB | No hay tabla de referencia. ¿Estos UUIDs son `codigos_segmento.id`? ¿`extracted_incidents.id` (que no existe aún)? | ❌ Roto |
| `ConceptualRelationship` | Memos origen | `origin_memo_ids` JSONB | No es FK a `memos`. | ⚠️ Débil |
| `ConceptualRelationship` | Hipótesis origen | `origin_hypothesis_ids` JSONB | No es FK a `hypotheses`. | ⚠️ Débil |

#### 16.2.3 Eslabones AUSENTES (no existen)

| Origen | Destino | Qué falta |
|--------|---------|-----------|
| `ConceptualRelationship` | Cita textual | No hay forma de hacer drill-down desde una relación hasta las citas exactas que la respaldan. `converging_incident_ids` existe como campo pero no referencia ninguna tabla concreta. |
| Memo (ghost-blob) | Categoria absorbida | La absorción se registra en `ElaborationMemo` (tipo='ghost_absorbed') pero no hay FK explícita memo→categoría. La trazabilidad es reconstructiva (hay que buscar el ElaborationMemo). |
| `IncidentGroup` (B1 output) | `Categoria` (B2 output) | La tabla `incident_groups` está planeada pero no implementada. El campo `category_id` vincularía grupo→categoría. |

### 16.3 Lo que SÍ está programado y arquitectónicamente sistematizado

**Capa de modelos (SQLAlchemy):**
- Todas las tablas tienen `proyecto_id` FK a `proyectos` → trazabilidad por proyecto.
- `TimestampMixin` en todas las tablas → trazabilidad temporal.
- `relationship()` con `back_populates` en la mayoría de entidades → navegabilidad ORM.
- `cascade="all, delete-orphan"` en relaciones padre-hijo → integridad en cascada.

**Capa de API:**
- `GET /elaboration/relationships/{id}` devuelve la relación con trazabilidad a `category_ids`, `converging_doc_count`, `diverging_doc_count`.
- `GET /elaboration/categories/{id}/definition-history` devuelve el timeline completo de versiones.
- `GET /elaboration/ecosystem` devuelve blobs + tendrils + layout.

**Capa de frontend:**
- `ElaborationPanel` (BlobDetail) muestra definición, propiedades, historial de versiones.
- `ElaborationPanel` (TendrilDetail) muestra evidencia convergente/divergente, código teórico usado.
- `CategoryEvolutionPanel` muestra timeline de versiones con triggers.

### 16.4 Lo que NO está programado (solo documentado/planeado)

| Funcionalidad | Dónde se necesita | Qué falta |
|--------------|-------------------|-----------|
| **Drill-down: relación → citas textuales** | `ElaborationPanel` (TendrilDetail) | Endpoint `GET /elaboration/relationships/{id}/evidence` que devuelva los segmentos/texto de `converging_incident_ids` y `diverging_incident_ids` |
| **Tabla `extracted_incidents`** | B1 (incident_comparator) | Migración 013 — planeada, no implementada. Sin esta tabla, `converging_incident_ids` no tiene dónde apuntar. |
| **Tabla `incident_groups`** | B2 (pattern_labeler) | Migración 015 — planeada, no implementada. Es el puente entre B1 (grupos de incidentes) y B2 (etiquetas). |
| **Tabla `incident_comparisons`** | B1 (incident_comparator) | Migración 014 — planeada, no implementada. Registra cada par comparado (constant comparative method). |
| **FK de `category_ids` a `categorias`** | `ConceptualRelationship` | Actualmente es JSONB. Debería ser una tabla pivote `relationship_categories` con FKs. |
| **FK de `origin_memo_ids` a `memos`** | `ConceptualRelationship` | Actualmente es JSONB. Debería ser `relationship_memos` con FKs. |
| **Frontend: clic en evidencia → ver cita** | `ElaborationPanel` | El panel muestra conteos ("5 docs convergen") pero no permite expandir para ver las citas. |
| **Frontend: clic en tendril → drill-down** | `EcosystemCanvas` | Al hacer clic en un tendril, debería mostrar las citas que respaldan (y desafían) la relación. |

### 16.5 Plan de acción para completar la trazabilidad

| Prioridad | Acción | Impacto |
|-----------|--------|---------|
| **1** | Implementar migraciones 013 (`extracted_incidents`), 014 (`incident_comparisons`), 015 (`incident_groups`) | Sin estas tablas, B1 y B2 no tienen dónde persistir sus outputs. |
| **2** | Crear tabla pivote `relationship_evidence` con FKs: `relationship_id → ConceptualRelationship`, `incident_id → extracted_incidents`, `evidence_type` (converging/diverging), `exact_quote` | Reemplaza los JSONB `converging_incident_ids` y `diverging_incident_ids`. Permite JOINs limpios. |
| **3** | Endpoint `GET /elaboration/relationships/{id}/evidence` → devuelve incidentes con citas textuales, documento de origen, y tipo de evidencia | Habilita el drill-down en el frontend. |
| **4** | Componente `EvidenceList` en `ElaborationPanel`: lista expandible de citas con documento, tipo, y texto | El investigador ve la evidencia textual directamente. |
| **5** | Reemplazar `category_ids` JSONB por tabla pivote `relationship_categories` | Integridad referencial. JOINs limpios. |

---

## 17. Sistema de memoing — diagnóstico y refacción

### 17.1 Cómo funciona ahora

Los agentes almacenan sus resultados en **5 tablas distintas** sin un modelo unificado de "memo como artefacto analítico":

| Agente | Output | Tabla | ¿Es modificable por el usuario? | ¿Tiene trazabilidad a evidencia? |
|--------|--------|-------|-------------------------------|----------------------------------|
| A1 | surprising_details | `population_contexts` (versioned) | ❌ No (solo lectura) | ❌ No (texto libre) |
| A2 | process_description | `document_processes` | ❌ No | ❌ No |
| A3 | hypotheses | `hypotheses` (con `status`, `level`, `confidence`) | ⚠️ Solo vía HITL (accept/reject) | ⚠️ Parcial (`code_id` opcional) |
| B1 | sampling dimensions | `memos` (tipo='MUESTREO') | ❌ No | ❌ No |
| B2 | codes + definitions | `categorias` + `CodigoSegmento` | ❌ No (el usuario no edita definiciones fácilmente) | ✅ Sí (vía `CodigoSegmento`) |
| B3 | hypotheses | `hypotheses` | ⚠️ Solo vía HITL | ⚠️ Parcial |
| C06 | prime_mover | `document_processes.prime_mover` | ❌ No | ❌ No |

### 17.2 Qué está mal

**Problema 1: Los memos no son "documentos vivos".** En CGT, los memos son el producto principal del análisis — el investigador los escribe, los reescribe, los expande, los conecta. En nuestro sistema, los agentes generan texto y lo guardan. El investigador no puede editarlo fácilmente. No hay versionado de memos.

**Problema 2: No hay distinción sistema vs. usuario.** El campo `autor_id` en `memos` existe pero siempre es el creador del proyecto (el sistema). No sabemos si un memo fue generado por B1 o modificado por el investigador. No hay `source` (system | user_modified | user_created).

**Problema 3: Los memos son texto plano sin estructura.** Un memo de hipótesis debería tener: categorías vinculadas, incidentes de respaldo, citas textuales, nivel de confianza, estado de verificación. Actualmente es solo `contenido TEXT`.

**Problema 4: El usuario ve outputs finales, no el razonamiento.** Los `paradigm_states` (did_state_expand, paradigm_snapshot) se almacenan pero no se muestran. El usuario ve "categoría saturada" pero no ve POR QUÉ — no ve los incidentes que expandieron el paradigma, ni las propiedades que se añadieron.

**Problema 5: Sin búsqueda rápida de evidencia.** Cuando el investigador está escribiendo un memo, no puede buscar rápidamente incidentes o citas que respalden su afirmación. Tiene que navegar al corpus manualmente.

### 17.3 Qué debemos añadir

#### 17.3.1 Memo versioning + structured fields

```sql
-- Extender la tabla memos
ALTER TABLE memos ADD COLUMN version INT DEFAULT 1;
ALTER TABLE memos ADD COLUMN source VARCHAR(50) DEFAULT 'system';
-- 'system' | 'user_modified' | 'user_created'

ALTER TABLE memos ADD COLUMN linked_category_ids UUID[] DEFAULT '{}';
ALTER TABLE memos ADD COLUMN linked_incident_ids UUID[] DEFAULT '{}';
ALTER TABLE memos ADD COLUMN evidence_quotes TEXT[] DEFAULT '{}';

-- Nueva tabla: memo_versions (paralela a category_definition_versions)
CREATE TABLE memo_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memo_id UUID REFERENCES memos(id),
    version INT NOT NULL,
    contenido TEXT NOT NULL,
    modified_by UUID REFERENCES usuarios(id),
    change_description TEXT,
    creado_en TIMESTAMPTZ DEFAULT now()
);
```

#### 17.3.2 El memo como "documento vivo" — flujo HITL

```
1. Agente genera memo (source='system', version=1)
2. Usuario ve el memo en el frontend (MemoCard component)
3. Usuario puede:
   a. EDITAR contenido → version N+1, source='user_modified'
   b. VINCULAR categorías → linked_category_ids se actualizan
   c. VINCULAR incidentes → linked_incident_ids se actualizan
   d. AGREGAR citas → evidence_quotes se actualizan
   e. ARCHIVAR → estado='ARCHIVADO'
4. Cada edición crea una entrada en memo_versions
5. El historial completo es visible (MemoVersionTimeline)
```

#### 17.3.3 Surface del razonamiento intermedio

| Dato intermedio | Dónde se almacena | Cómo mostrarlo al usuario |
|----------------|-------------------|--------------------------|
| ¿Por qué esta categoría está saturada? | `paradigm_states` (5 iteraciones sin expandir) | `SaturationGapAnalyzer` ya produce GapReport. Mostrar en `ElaborationPanel`: "3 iteraciones sin expandir. rolling_std=0.08. Última expansión: propiedad 'Intensidad' añadida por incidente de 03_Mayte." |
| ¿Qué incidentes expandieron esta categoría? | `paradigm_states.paradigm_snapshot` + `incident_ids` | Botón "Ver incidentes" en `ElaborationPanel` → lista de incidentes con citas que causaron cada expansión |
| ¿Por qué se sugiere este renombre? | `category_definition_versions` (trigger + trigger_detail) | `RenameModal` ya muestra "qué gana" cada nombre sugerido |
| ¿Qué evidencia respalda esta relación? | `converging_incident_ids` + `diverging_incident_ids` | `ElaborationPanel` (TendrilDetail) → lista expandible de citas |

#### 17.3.4 Sistema de búsqueda @ (RAG rápido con colores jerárquicos)

El investigador, mientras edita un memo o explora el Playground, puede invocar **@** para buscar rápidamente:

```
┌─────────────────────────────────────────────────────────────────┐
│  @analizando patrones                                           │
│                                                                  │
│  🟣 CATEGORÍAS (2)                                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Analizando patrones sociales                                ││
│  │ Los periodistas examinan el impacto sistémico de la IA...   ││
│  │ 18 incidentes · 11 docs · v3                               ││
│  └─────────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Analizando el impacto sistémico (CANDIDATO A RENOMBRE)     ││
│  │ ...                                                         ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  🟢 INCIDENTES (5)                                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ "Primero entendí qué hacía la IA con las noticias, luego    ││
│  │  empecé a usarla para chequear datos"                       ││
│  │ 03_Mayte Ciriaco · Doc 2 · Seg 15 · baseline_data          ││
│  └─────────────────────────────────────────────────────────────┘│
│  ...                                                             │
│                                                                  │
│  🟡 CITAS CLAVE (3)                                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ "Hay que entender el impacto antes de decidir si la usas"   ││
│  │ 15_Augusto Towsend · Doc 6 · Seg 22                        ││
│  └─────────────────────────────────────────────────────────────┘│
│  ...                                                             │
└─────────────────────────────────────────────────────────────────┘
```

**Jerarquía visual:**
- 🟣 **Categorías** (primer nivel) — concepts, higher abstraction
- 🟢 **Incidentes** (segundo nivel) — instances of patterns
- 🟡 **Citas clave** (tercer nivel) — raw data excerpts

**Implementación:**
- Componente `MentionSearch` (overlay flotante, activado con @)
- `GET /search/mention?q=text&project_id=id` → RRF fusion sobre categorías + incidentes + segmentos
- Los resultados se agrupan por tipo y se ordenan por relevance score
- Click en un resultado → lo inserta como referencia en el memo (linked_category_ids, linked_incident_ids, evidence_quotes)

### 17.4 Resumen: lo que cambia

| Antes | Ahora |
|-------|-------|
| Memos son texto plano sin estructura | Memos tienen `linked_category_ids`, `linked_incident_ids`, `evidence_quotes` |
| Sin versionado de memos | `memo_versions` registra cada edición con autor y descripción del cambio |
| Sin distinción sistema/usuario | `source` field: system | user_modified | user_created |
| Sin búsqueda rápida | `@` MentionSearch con RRF, agrupado por jerarquía (categorías > incidentes > citas) |
| Usuario ve outputs, no razonamiento | `ElaborationPanel` muestra por qué una categoría está saturada, qué incidentes la expandieron |
| Sin trazabilidad memo→evidencia | Cada memo linkea a categorías, incidentes y citas que lo respaldan |


---

## 19.5 Optimización del sistema de sorting (Theoretical Coding)

### 19.5.1 Principio: sorting estructural ≠ verificación RAG

El sorting de memos opera sobre **contenido ya sintetizado**. Los memos son el producto del open y selective coding. Volver a los datos crudos en cada iteración sería redundante y caro. El RAG solo se activa cuando el sorting revela una tensión que los memos no resuelven.

```
┌─────────────────────────────────────────────────────────────────┐
│ SORTING ESTRUCTURAL (rápido, sin LLM, sin RAG)                   │
│                                                                  │
│ Input:  Memos (con linked_category_ids, evidence_quotes)         │
│         + 12 TheoreticalCodes (evaluation_logic)                 │
│                                                                  │
│ Proceso:                                                         │
│   a) Pre-clasificación FLASH: memo_theoretical_tagger analiza    │
│      cada memo y sugiere afinidad con familias teóricas          │
│   b) El investigador elige una familia                           │
│   c) El sistema agrupa memos por esa familia (estructural)       │
│   d) Muestra: grupos, homeless, thin piles, forced placements    │
│   e) Guarda como Intento N                                       │
│   f) Repite con otra familia                                     │
│                                                                  │
│ Output: SortingLog (N intentos, cada uno con métricas)           │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│ VERIFICACIÓN RAG (bajo demanda, solo cuando hay tensión)         │
│                                                                  │
│ Disparadores:                                                    │
│   • Thin pile (< 3 memos) → "¿Buscamos más evidencia?"           │
│   • Contradicción entre memos → "¿Verificamos contra datos?"     │
│   • Homeless memo recurrente → "¿Buscamos incidentes?"           │
│   • Investigador hace clic en "Verificar"                        │
│                                                                  │
│ Proceso: conceptual_elaborator (PRO) → evidencia                 │
└─────────────────────────────────────────────────────────────────┘
```

### 19.5.2 Nuevo agente: memo_theoretical_tagger (FLASH)

Pre-clasifica cada memo con afinidad a familias teóricas, permitiendo al investigador elegir rápido:

```
Memo H17: "Percibir amenaza DESENCADENA análisis de patrones"
  → Causal (0.85), Proceso (0.70)
Memo H23: "Gestores integran; redactores resisten"
  → Tipología (0.90), Oposición (0.75)
Memo H31: "El análisis se INTENSIFICA cuando..."
  → Condición (0.80), Causal (0.60)
```

### 19.5.3 SortingLog como artefacto central

Cada intento de sorting se registra con métricas (grupos, homeless, forced, thin piles). El investigador puede comparar intentos y crear híbridos. Los grupos que reaparecen en ≥2 intentos son candidatos a secciones del informe.

### 19.5.4 RAG en 3 momentos (nunca automático)

| Momento | Disparador | Acción |
|---------|-----------|--------|
| Thin pile | < 3 memos en un grupo | corpus_scanner (FLASH) busca incidentes → sugiere crear memo o muestrear |
| Contradicción | Dos memos se contradicen | conceptual_elaborator (PRO) busca respaldo → evidencia comparativa |
| Verificación final | Investigador cree haber integrado | cross_family_synthesizer (PRO) verifica cada relación → índice de ajuste global |

---

## 20. Sistema de re-especificación jerárquica (fallback pattern)

### 20.1 Principio

En cada nivel de abstracción, el sistema acumula decisiones: este segmento es baseline, este incidente pertenece a este grupo, esta categoría tiene estas propiedades, esta relación es de tipo proceso. Pero ¿qué pasa si una decisión en un nivel superior revela que una decisión en un nivel inferior fue incorrecta?

El **fallback pattern** permite que cualquier nivel "cuestione" a los niveles inferiores y solicite una re-especificación. Es una mezcla de programación (detección de anomalías) e IA (re-análisis contextual).

```
NIVEL 4 — Theoretical (cross_family_synthesizer)
  │  "La familia Proceso no integra bien → ¿los memos de relación
  │   subestiman la simultaneidad? ¿Hay incidentes mal categorizados?"
  │
  ▼
NIVEL 3 — Core Category (core_category_synthesizer)
  │  "Este candidato a core no unifica → ¿las categorías están
  │   bien definidas? ¿Hay propiedades que no documentamos?"
  │
  ▼
NIVEL 2 — Categories/Relationships (label_critic, conceptual_elaborator)
  │  "Esta etiqueta no captura el patrón → ¿los incidentes del grupo
  │   son realmente intercambiables? ¿Hay outliers?"
  │
  ▼
NIVEL 1 — Incidents (incident_extractor, incident_comparator)
  │  "Este incidente no encaja en ningún grupo → ¿lo extrajimos bien?
  │   ¿Es baseline o interpreted? ¿Aplicamos bien las 4 preguntas?"
  │
  ▼
NIVEL 0 — Raw Data (segmentos, documentos)
     "¿Este segmento fue bien clasificado? ¿Es realmente baseline?
      ¿Hay segmentos no codificados que deberían ser incidentes?"
```

### 20.2 Indicios ya existentes en el sistema actual

El sistema actual ya tiene señales que pueden disparar el fallback:

| Señal | Dónde está | Qué indica |
|-------|-----------|------------|
| `keep_moving = true` | `extracted_incidents` (planeado) | Incidente ambiguo. Posible mala extracción. |
| `glaser_data_type = 'vague'` | `segmentos.tipo_dato_glaser` | Segmento evasivo. ¿Es realmente vague o lo clasificamos mal? |
| `ungrouped_incidents` | `incident_comparator` output (B1) | Incidente no encaja en ningún grupo. |
| `label_critic.verdict = FORCED` | B3 output | Etiqueta no captura el patrón. |
| `diverging_incident_ids` | `ConceptualRelationship` | Incidentes que contradicen la relación. |
| `homeless memo persistente` | `SortingLog` | Memo no encaja en ninguna familia teórica. |
| `eje de comparación vacío` | `SaturationGapAnalyzer` | Falta un extremo de propiedad. ¿O la propiedad está mal definida? |
| `did_state_expand frecuente` | `ParadigmState` | La categoría sigue expandiéndose. ¿O los incidentes están mal asignados? |

### 20.3 Agente central: ReSpecAgent (PRO)

Un agente PRO que monitorea los logs de los últimos análisis y sugiere proactivamente re-especificaciones:

```
ReSpecAgent (PRO):
  Input:  Logs de los últimos N análisis (ElaborationMemo, ParadigmState,
          SortingLog, SaturationGapAnalyzer gaps, label_critic evaluations)
  
  Output: ReSpecSuggestions:
    • "3 incidentes en 'Analizando patrones' tienen keep_moving=true.
       Sugerencia: re-extraer estos incidentes con más contexto."
    • "La propiedad 'Profundidad' tiene el extremo 'superficial' vacío.
       Sugerencia: ¿existe realmente este extremo? ¿O la propiedad
       debería redefinirse como unipolar?"
    • "El memo H45 es homeless en 3 intentos de sorting.
       Sugerencia: ¿el incidente del que surgió H45 está bien
       categorizado? Revisar incidente fuente."
    • "B3 marcó FORCED la etiqueta 'Analizando patrones sociales'.
       Sugerencia: ¿los incidentes del grupo son realmente
       intercambiables? Re-ejecutar B1 (comparator) sobre este grupo."
```

### 20.4 Flujo de re-especificación

```
1. DETECCIÓN (algorítmica + LLM)
   ┌─ Señales algorítmicas: keep_moving count, FORCED count,
   │  homeless persistence, thin piles, eje vacío
   └─ ReSpecAgent (PRO): analiza logs, sugiere re-especificaciones

2. NOTIFICACIÓN (frontend)
   ┌─ Badge en el blob/tendril: "⚠️ 3 incidentes necesitan revisión"
   ├─ Panel de ReSpec: lista de sugerencias priorizadas
   └─ Text box: el investigador puede pedir "revisá la categoría X"

3. RE-ESPECIFICACIÓN (IA + programación)
   ┌─ Target: nivel específico (incidente, categoría, relación)
   ├─ Contexto: se inyecta el contexto del nivel SUPERIOR
   │  (ej: si el nivel 3 pide re-especificar nivel 2, el agente
   │   del nivel 2 recibe POR QUÉ el nivel 3 lo necesita)
   └─ Output: nueva versión del artefacto (incidente re-extraído,
      categoría re-definida, relación re-evaluada)

4. PROPAGACIÓN (en cascada hacia arriba)
   ┌─ Si un incidente se re-extrae → re-ejecutar B1 (comparator)
   │  para ese documento
   ├─ Si una categoría se redefine → re-evaluar饱和ación
   ├─ Si una relación se re-evalúa → actualizar SortingLog
   └─ Si el core category cambia → actualizar Theoretical Playground

5. HITL (en cada paso)
   ┌─ El investigador ve la sugerencia
   ├─ Puede aceptar, modificar, o rechazar
   └─ Si acepta → se ejecuta la re-especificación + propagación
```

### 20.5 Tool: ReSpecTool (invocable desde cualquier nivel)

Cada nivel tiene acceso a una **ReSpecTool** que permite consultar niveles inferiores:

```python
class ReSpecTool:
    """Tool disponible para agentes en cualquier nivel."""
    
    def query_lower_level(
        self,
        from_level: int,        # 0-4
        target_level: int,      # 0-3 (siempre menor que from_level)
        artifact_id: UUID,      # ID del artefacto a re-examinar
        reason: str,            # Por qué se solicita la re-especificación
        context_from_above: str # Qué descubrió el nivel superior
    ) -> ReSpecResult:
        """
        Ejemplo:
          from_level=3 (core_category_synthesizer)
          target_level=2 (categorías)
          artifact_id: uuid de 'Analizando patrones sociales'
          reason: "No encaja como candidato a core. Sus propiedades
                   no explican suficiente variación."
          context_from_above: "El core necesita una categoría que
                   unifique Percibir, Integrar y Resistir. Esta
                   solo cubre Percibir→Analizar."
        
        → Re-ejecuta label_critic sobre esta categoría
        → Si FORCED → re-ejecuta pattern_labeler con nuevo contexto
        → Si MOD → ajusta definición/propiedades
        → Retorna: nueva versión de la categoría o confirmación
        """
```

### 20.6 Frontend: Panel de ReSpec

```
┌─────────────────────────────────────────────────────────────────┐
│ ⚠️ RE-ESPECIFICACIONES SUGERIDAS                    [⟳] [🔇]  │
│                                                                  │
│ ReSpecAgent detectó 5 oportunidades de refinamiento:            │
│                                                                  │
│ 🔴 Nivel 2 → Nivel 1 (3 incidentes)                             │
│   "Analizando patrones" tiene 3 incidentes con keep_moving=true.│
│   Sugerencia: re-extraer con más contexto.                      │
│   [Re-extraer] [Ignorar] [Marcar como revisado]                 │
│                                                                  │
│ 🟡 Nivel 3 → Nivel 2 (1 categoría)                              │
│   "Integrando estratégicamente" fue marcada FORCED por B3.      │
│   Sugerencia: re-ejecutar comparator sobre este grupo.          │
│   [Re-evaluar] [Ignorar]                                        │
│                                                                  │
│ 🟡 Nivel 4 → Nivel 2 (1 relación)                               │
│   Relación "Analizar→Integrar" tiene 2 divergencias sin resolver.│
│   Sugerencia: verificar contra datos con conceptual_elaborator. │
│   [Verificar] [Ignorar]                                         │
│                                                                  │
│ 🟢 Nivel 4 → Nivel 3 (1 memo)                                   │
│   Memo H45 es homeless en 3 intentos de sorting.                │
│   Sugerencia: revisar incidente fuente.                          │
│   [Revisar fuente] [Ignorar]                                    │
│                                                                  │
│ 🟢 Nivel 2 → Nivel 1 (1 propiedad)                              │
│   Propiedad 'Profundidad' tiene extremo 'superficial' vacío.    │
│   Sugerencia: ¿existe este extremo? ¿Redefinir propiedad?      │
│   [Redefinir] [Ignorar] [Marcar límite]                         │
│                                                                  │
│ ── TEXT BOX ────────────────────────────────────────────────── │
│ │ El investigador puede pedir:                                   │
│ │ "Revisá si los incidentes de 'Resistir' están bien extraídos" │
│ │ [Ejecutar]                                                     │
│ └───────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 20.7 Nuevos agentes y piezas para el fallback pattern

| # | Pieza | Tipo | Descripción |
|---|-------|------|-------------|
| 20.1 | `ReSpecAgent` | Prompt PRO | Monitorea logs, sugiere re-especificaciones proactivamente |
| 20.2 | `ReSpecTool` | Servicio Python | Tool invocable desde cualquier nivel para consultar niveles inferiores |
| 20.3 | `ReSpecPanel` | Componente React | Panel de sugerencias priorizadas con acciones |
| 20.4 | `ReSpecTextbox` | Componente React | Text box para que el investigador pida re-especificaciones |
| 20.5 | Propagación en cascada | Servicio Python | Si un artefacto cambia, propagar hacia arriba (re-comparar, re-evaluar) |
| 20.6 | Badge system | Componente React | ⚠️ indicadores en blobs/tendriles que necesitan revisión |
| 20.7 | `GET /analysis/respec-suggestions` | Endpoint API | Devuelve sugerencias del ReSpecAgent |

### 20.8 Conexión con el sistema actual

Las señales ya existen:
- `keep_moving` → en `extracted_incidents` (planeado)
- `verdict = FORCED` → en `label_critic` (planeado)
- `diverging_incident_ids` → en `ConceptualRelationship` (implementado)
- `homeless memo` → en `SortingLog` (planeado)
- `eje vacío` → en `SaturationGapAnalyzer` (implementado)
- `did_state_expand` → en `ParadigmState` (implementado)

Lo que falta es el **agente que las lea juntas** y produzca sugerencias accionables.

### 20.9 Stage-Gate Review: botón de re-especificación al finalizar cada etapa

#### Principio

Al completar cada etapa del análisis, el sistema ofrece al investigador una **pausa de revisión** antes de avanzar. No es obligatoria — pero el botón brilla para señalizar que hay oportunidad de refinar.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  OPEN CODING COMPLETADO                                  [✦ ✦]  │
│  ████████████████████████████████████████████████ 100%           │
│                                                                  │
│  El botón ✦ brilla cuando:                                      │
│  • Todos los docs pasaron por A0→A1→A2                           │
│  • Hay ≥ 3 documentos procesados                                 │
│  • El ReSpecAgent detectó ≥ 1 sugerencia para esta etapa         │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ✦ REVISAR OPEN CODING                          [ignorar →]  │ │
│  │                                                              │ │
│  │ Antes de pasar a Selective Coding, ¿querés revisar?          │ │
│  │                                                              │ │
│  │ • 3 incidentes con keep_moving=true en "Analizando patrones" │ │
│  │ • 1 segmento reclasificado de baseline a properline          │ │
│  │ • 2 documentos sin prime_mover (insufficient_data)           │ │
│  │                                                              │ │
│  │ [Abrir panel de revisión]                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SELECTIVE CODING COMPLETADO                             [✦ ✦]  │
│  ████████████████████████████████████████████████ 100%           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ✦ REVISAR SELECTIVE CODING                      [ignorar →] │ │
│  │                                                              │ │
│  │ Antes del Theoretical Playground, ¿querés revisar?           │ │
│  │                                                              │ │
│  │ • 1 categoría con eje vacío (Profundidad: 'superficial')     │ │
│  │ • 2 categorías candidatas a renombre                         │ │
│  │ • B3 marcó FORCED 1 etiqueta                                 │ │
│  │ • maturity_gate_checker: faltan relaciones documentadas      │ │
│  │                                                              │ │
│  │ [Abrir panel de revisión]                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  THEORETICAL CODING — Sesión activa                      [✦ ]   │
│  ████████████████████████████░░░░░░░░░░░░░░░░░░ 55%             │
│                                                                  │
│  (Durante la sesión, el botón ✦ está disponible pero no brilla  │
│   con intensidad — el investigador puede invocarlo cuando quiera)│
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ ✦ REVISAR THEORETICAL CODING                                 │ │
│  │                                                              │ │
│  │ • 1 memo homeless en 3 intentos de sorting                   │ │
│  │ • 2 relaciones con divergencia sin resolver                  │ │
│  │ • cross_family_synthesizer sugiere híbrido                   │ │
│  │                                                              │ │
│  │ [Abrir panel de revisión]                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Implementación

```python
class StageGateManager:
    """Maneja el botón de revisión al finalizar cada etapa."""
    
    STAGES = {
        "open_coding": {
            "completion_condition": lambda p: all_docs_passed(p, ["A0", "A1", "A2"]) and doc_count(p) >= 3,
            "respec_signals": ["keep_moving_count", "insufficient_prime_mover", "glaser_reclassified"],
            "next_stage": "selective_coding",
        },
        "selective_coding": {
            "completion_condition": lambda p: maturity_gate_passed(p) and core_category_confirmed(p),
            "respec_signals": ["empty_axes", "forced_labels", "rename_candidates", "missing_relationships"],
            "next_stage": "theoretical_playground",
        },
        "theoretical_coding": {
            "completion_condition": lambda p: False,  # Nunca "termina" — es sesión
            "respec_signals": ["homeless_memos", "unresolved_divergence", "thin_piles", "cross_family_tension"],
            "next_stage": None,
        },
    }
    
    def get_stage_status(self, project_id: UUID) -> StageStatus:
        """Retorna: etapa actual, % completado, señales de ReSpec, brillo del botón."""
        current = self._detect_current_stage(project_id)
        config = self.STAGES[current]
        
        # Recolectar señales del ReSpecAgent
        signals = ReSpecAgent(project_id).detect_signals(config["respec_signals"])
        
        # El botón brilla si:
        # - La etapa está completada (para open/selective)
        # - O hay ≥ 3 señales acumuladas (para theoretical/sesión)
        should_glow = (
            config["completion_condition"](project_id) 
            or len(signals) >= 3
        )
        
        return StageStatus(
            stage=current,
            completion_pct=self._calculate_pct(project_id, current),
            signals=signals,
            should_glow=should_glow,
            can_proceed=config["completion_condition"](project_id),
        )
```

#### Componente frontend: StageGateButton

```typescript
interface StageGateButtonProps {
  stage: "open_coding" | "selective_coding" | "theoretical_coding";
  completionPct: number;
  signals: ReSpecSignal[];
  shouldGlow: boolean;
  canProceed: boolean;
}

function StageGateButton({ stage, completionPct, signals, shouldGlow, canProceed }: StageGateButtonProps) {
  const stageLabels = {
    open_coding: "Open Coding",
    selective_coding: "Selective Coding", 
    theoretical_coding: "Theoretical Coding",
  };
  
  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24, zIndex: 50,
      display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 8,
    }}>
      {/* Barra de progreso */}
      <div style={{ fontSize: 11, color: "#8B949E" }}>
        {stageLabels[stage]} · {completionPct}%
      </div>
      
      {/* Botón que brilla */}
      <button
        onClick={() => openReSpecPanel(stage)}
        style={{
          padding: "10px 20px", borderRadius: 8,
          background: shouldGlow ? "#A371F7" : "#21262D",
          border: shouldGlow ? "2px solid #A371F7" : "1px solid #30363D",
          color: shouldGlow ? "#FFF" : "#8B949E",
          fontSize: 14, fontWeight: 600, cursor: "pointer",
          animation: shouldGlow ? "glow 2s ease-in-out infinite" : "none",
          boxShadow: shouldGlow ? "0 0 16px rgba(163,113,247,0.4)" : "none",
        }}
      >
        {shouldGlow ? `✦ Revisar ${stageLabels[stage]}` : `Revisar ${stageLabels[stage]}`}
        {signals.length > 0 && (
          <span style={{
            marginLeft: 8, padding: "2px 8px", borderRadius: 999,
            background: "#F85149", color: "#FFF", fontSize: 11,
          }}>
            {signals.length}
          </span>
        )}
      </button>
      
      {/* Solo mostrar "Continuar" si la etapa está completa */}
      {canProceed && (
        <button
          onClick={() => advanceToNextStage(stage)}
          style={{
            padding: "8px 16px", borderRadius: 6,
            background: "transparent", border: "1px solid #30363D",
            color: "#3FB950", fontSize: 12, cursor: "pointer",
          }}
        >
          Continuar sin revisar →
        </button>
      )}
    </div>
  );
}

// Animación CSS
const glowKeyframes = `
  @keyframes glow {
    0%, 100% { box-shadow: 0 0 8px rgba(163,113,247,0.3); }
    50% { box-shadow: 0 0 20px rgba(163,113,247,0.6); }
  }
`;
```

#### Endpoint

```
GET /projects/{pid}/stage-gate/status
  → { stage, completion_pct, signals: [...], should_glow, can_proceed }

POST /projects/{pid}/stage-gate/advance
  → { from_stage, to_stage }
  → Solo funciona si can_proceed = true
```
