# Prompt Engineering Criteria — DeepSeek Pro & Flash

> Derivado de: `pro/` + `flash/` (viejo sistema) → `deepseek_pro/` + `deepseek_flash/` (nuevo)
> Aplica a todos los prompts del sistema CGT.

---

## 1. Asignación de tier

| Tier | Modelo | Cuándo usarlo | Ejemplos |
|---|---|---|---|
| **FLASH** | DeepSeek V3 | Extracción, clasificación, resumen. Tareas con input→output claro, baja ambigüedad. Sin razonamiento elaborado | Extraer indicadores (b2a), extraer entidades, extraer incidentes, resumir documento, clasificar tipo de dato |
| **PRO** | DeepSeek R1 | Generación, síntesis, evaluación, razonamiento cualitativo. Tareas con alta ambigüedad que requieren juicio | Generar códigos (b2b), evaluar SAT/MOD/FORCED, sintetizar cross-doc, identificar main concern, generar hipótesis |

### Regla de quiebre (breakdown)

Toda tarea compleja se descompone así:

```
[FLASH] pre-procesamiento → [ALGORÍTMICO] filtrado → [PRO] razonamiento cualitativo
```

Lo que puede hacer el código (similitud de embeddings, deduplicación, filtros) **nunca** va en el prompt del LLM. Va en `algorithmic_checks.py`.

---

## 2. Estructura de archivo

### Formato YAML (.md)

```yaml
---
agent: id_unico
tier: PRO | FLASH
description: Una línea explicando qué hace
notes:
  - Nota de implementación 1
  - Nota de implementación 2
constraints:
  - Regla anti-alucinación 1
  - Regla anti-alucinación 2
---

## System
[ROL]
... rol + objetivo + reglas + marco analítico ...

## User
... inputs con {variables} ...

## Output Schema
```json
{... schema ...}
```
```

### Reglas

- **System**: rol, objetivo, restricciones, marco conceptual. Lo que el modelo necesita saber antes de ver los datos.
- **User**: los datos concretos. `{variables}` con nombres descriptivos.
- **Output Schema**: JSON Schema en bloque ` ```json ``` `. **No** va dentro de System ni User.
- Variables usan `{single_braces}` — Python `.format()` las reemplaza.
- El schema se extrae ANTES de `.format()` — sin riesgo de conflicto de llaves.

---

## 3. JSON Schema — reglas DeepSeek

### Lo que SÍ funciona

| Regla | Ejemplo |
|---|---|
| `additionalProperties: false` en todo objeto | Evita campos alucinados |
| Max 3 niveles de anidamiento | `{obj: {arr: [{prop: value}]}}` |
| `description` en cada campo | Aunque parezca redundante |
| `enum` para valores acotados | `"enum": ["SAT", "MOD", "FORCED"]` |
| Arrays pueden ser vacíos | `"type": "array"` sin `minItems` |
| Tipos explícitos en items | `"items": {"type": "string"}` |

### Lo que NO funciona

| Anti-patrón | Por qué | Alternativa |
|---|---|---|
| `oneOf` / `anyOf` / `allOf` | DeepSeek los ignora frecuentemente | Aplanar con `type: string` + `description` explicando las opciones |
| `$defs` / `$ref` | No los resuelve consistentemente | Duplicar la definición inline |
| `minLength` / `maxLength` / `pattern` | Baja adherencia | Usar `description` con la restricción: "max 500 chars" |
| Schemas de más de 4 niveles | Se pierde en la estructura | Aplanar |

---

## 4. Anti-alucinación — checklist por prompt

Todo prompt debe incluir **explícitamente** estas instrucciones (en System, no solo en constraints):

- [ ] "Usa solo la información proporcionada. No inventes datos, entrevistados ni citas."
- [ ] "Si no hay suficiente evidencia para X, responde exactamente: 'Sin evidencia suficiente.'"
- [ ] "Si es el primer caso/entrevistado, responde: 'N/A — primer caso.'"
- [ ] Arrays vacíos permitidos cuando no hay resultados: `"type": "array"` sin `minItems`
- [ ] Toda afirmación debe estar anclada en evidencia concreta de los datos proporcionados

---

## 5. Variables estándar (naming convention)

| Variable | Qué contiene | Quién la inyecta |
|---|---|---|
| `{population_assumption}` | Supuesto poblacional (gerundio) | `_get_population_assumption()` |
| `{population_context}` | A1: surprising_details acumulados | Agents pipeline |
| `{processes}` | A2: process_description por documento | Agents pipeline |
| `{existing_codes}` | Categorías existentes (nombre + definición) | Agents pipeline |
| `{existing_hypotheses}` | Hipótesis no rechazadas | Agents pipeline |
| `{segments}` | Textos crudos de segmentos | Agents pipeline |
| `{indicators}` | Salida pre-procesada de FLASH (b2a) | Agents pipeline |

---

## 6. Mapeo completo de agentes (tier + breakdown)

| Agente | Tier | FLASH pre | PRO main | Estado |
|---|---|---|---|---|
| A1 — Population Context | PRO | — | Síntesis acumulativa 3 dimensiones | ✅ `.md` |
| A2 — Process Identifier | PRO | `preclassify_glaser()` (algorítmico) | Identificar proceso + comparar | ✅ `.md` |
| A3 — Sense Maker | PRO | — | Proponer/modificar hipótesis con sense_status | ✅ `.md` |
| B1 — Sampling Distiller | PRO | `filter_empty_dimensions()` (algorítmico) | Dimensiones de variación + criterios | ✅ `.md` |
| B2a — Indicator Extractor | **FLASH** | — | Extraer indicadores de comportamiento | ✅ `.md` |
| B2b — Code Generator | PRO | — | Generar códigos en gerundio desde indicadores | ✅ `.md` |
| B2.5 — Grounding | **ALGORÍTMICO** | `prescreen_segments_against_codes()` + pgvector | — | ✅ `agents_b.py` |
| B2 Critic — Code Evaluator | PRO | `prescreen` (overlap stats inyectados) | Evaluar SAT/MOD/FORCED | 🔴 crear |
| B3 — Hypothesis Generator | PRO | `deduplicate_hypotheses()` (algorítmico) | Generar hipótesis con tipos + related_codes | ✅ `.md` |
| Map Synthesis | PRO | — | Síntesis intra-doc por código (3-8 oraciones + evidencia) | 🔴 portar |
| Reduce Synthesis | PRO | — | Consolidación inter-doc (propiedades, tipos, condiciones, acción) | 🔴 portar |
| Incident Extractor | **FLASH** | — | Extraer incidentes con citas exactas + paradigma | ✅ `.md` (flash) |
| Incident Extractor PRO | PRO | — | Mismo que FLASH pero con stricter quality | 🔴 portar |
| Clusterizador (A04) | PRO | Similitud embeddings (algorítmico inyectado) | 6-step clustering | 🔴 portar |
| Main Concern Proposer (A14) | PRO | — | 5 preguntas GT → main_concern | ✅ `.md` (huérfano) |
| Main Concern Critic (A14) | PRO | — | Evaluar main_concern propuesto | ✅ `.md` (huérfano) |
| Core Emergence Proposer (A15) | PRO | — | Identificar core category candidates | ✅ `.md` (huérfano) |
| Core Emergence Critic (A15) | PRO | — | Evaluar candidatos a core | ✅ `.md` (huérfano) |
| Interchangeability Tester (A16) | PRO | FLASH: extraer esencias de incidentes | Comparar esencias → INTERCAMBIABLES/NO | 🔴 crear |
