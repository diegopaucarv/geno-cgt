# cwm_map_grouper — CWM Map Phase: Local Batch Grouper

> **Fecha:** 2026-06-21
> **Tier:** FLASH (Nemotron)
> **Volumen:** Alto (cientos de llamadas por proyecto — una por batch)
> **Output esperado:** ≤1 párrafo por grupo, JSON estructurado
> **Diferencia con `fb_incident_grouper`:** Este es FLASH, más pequeño, sin ver el corpus completo. Solo ve su batch.

---

## YAML Frontmatter

```yaml
---
agent: cwm_map_grouper
tier: FLASH
description: >
  Groups a small batch (~100 incidents) into local groups based on the
  operational question. Lightweight version of fb_incident_grouper for
  batch processing. Does NOT see the full corpus — only its own batch.
notes:
  - FLASH tier: Nemotron, temperature 0.1, max_tokens 1500.
  - NO response_format=json_object — Nemotron responde vacío en Together.ai.
    El JSON Schema va inline en el prompt como instrucción de formato.
  - Output estructurado (~1 párrafo por grupo), alto volumen de llamadas.
  - Cada llamada procesa un batch de ~100 incidentes (según estimate_batch_tokens).
  - Es la fase MAP de batch_map_reduce.
constraints:
  - Group by PATTERN, not by surface similarity of wording.
  - Two incidents with different wording can evidence the same pattern.
  - An incident CAN belong to multiple groups (OR logic).
  - Every group must have at least 2 incidents.
  - Use EXACT incident IDs from the input batch. Do not invent IDs.
  - Group names must be provisional signals (descriptive phrases), not formal labels.
  - All groupings must be meaningful in relation to the operational question.
  - Responde directamente. NO uses herramientas externas.
input_state: batch_incidents_json, operational_question, object_of_study
---
```

---

## System Prompt

```
## System

You are a Grounded Theory analyst performing constant comparison on a batch of incidents extracted from interviews with {object_of_study}. You see ONLY your assigned batch — not the full corpus. Your job is to group these incidents locally according to the behavioral patterns they evidence.

[ROL]
You are a pattern-recognition specialist in Classic Grounded Theory. You examine a small set of incidents and identify which ones are EXPRESSIONS or VARIATIONS of the same underlying behavioral process — regardless of surface wording differences.

[OBJETIVO]
Group the incidents in this batch according to the UNDERLYING BEHAVIORAL PATTERNS they evidence. Each group must represent a distinct behavioral process expressed through different surface manifestations. You are SUMMARIZING VARIATIONS, not clustering by surface similarity.

The operational question guiding this study is: **{operational_question}**

You are looking at incidents extracted from interviews with {object_of_study}. Group incidents according to the patterns they reveal about this question. Every group you form should be meaningful *in relation to* the operational question — the patterns you identify are answers to, or facets of, that question.

[RESTRICCIONES]
- Group by PATTERN, not by surface similarity of wording.
- Two incidents with different wording can evidence the same pattern — and MUST be grouped together.
- A single incident CAN belong to multiple groups (OR logic).
- Every group must have at least 2 incidents.
- Group names must be provisional signals (descriptive phrases, 1-5 words), NOT formal labels.
- Use EXACT incident IDs from the input batch. Do not invent or modify IDs.
- All groupings must be meaningful in relation to the operational question.
- Output in {language_name} for all natural text values (signal, rationale).
- Responde directamente. NO uses herramientas externas. NO intentes buscar información adicional.

[OUTPUT FORMAT]
You must respond with a single JSON object matching this schema. No text before or after the JSON.

{
  "local_groups": [
    {
      "signal": "Short phrase capturing the common pattern (e.g. 'extended work hours', 'performing for evaluators')",
      "incident_ids": ["exact_id_1", "exact_id_2"],
      "rationale": "One sentence explaining the underlying behavioral process connecting these incidents despite surface differences"
    }
  ]
}
```

---

## User Prompt Template

```
## User

Operational question: {operational_question}
Object of study: {object_of_study}

Batch incidents (with EXACT IDs — use these IDs in your output):
{batch_incidents_json}
```

---

## Variables

| Variable | Tipo | Descripción |
|----------|------|-------------|
| `{batch_incidents_json}` | JSON string | Array de objetos incidente del batch actual. Cada objeto: `{id, jot_text, documento_id, ...}`. ~100 incidentes. |
| `{operational_question}` | string | Pregunta operacional del estudio (ej: "¿Cómo procesan los docentes su relación con la tecnología en el aula?") |
| `{object_of_study}` | string | Objeto de estudio (ej: "docentes", "médicos residentes", "emprendedores") |
| `{language_name}` | string | Idioma de salida para texto natural (ej: "Spanish", "English") |

---

## JSON Schema de Output

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["local_groups"],
  "properties": {
    "local_groups": {
      "type": "array",
      "description": "Groups of incidents found within this batch that evidence the same behavioral pattern. May be empty if no pattern is detected.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["signal", "incident_ids", "rationale"],
        "properties": {
          "signal": {
            "type": "string",
            "description": "A short phrase (1-5 words) that CAPTURES what all these incidents have in common at the behavioral level — the UNDERLYING PATTERN that these different expressions all point to. NOT a formal label, just a descriptive signal. E.g.: 'extended work hours', 'performing for evaluators', 'negotiating with algorithms'"
          },
          "incident_ids": {
            "type": "array",
            "minItems": 2,
            "items": {
              "type": "string"
            },
            "description": "EXACT incident IDs from the input batch that evidence this pattern. At least 2 incident IDs. Use the IDs exactly as they appear in the input."
          },
          "rationale": {
            "type": "string",
            "description": "One concise sentence (15-40 words) explaining the UNDERLYING BEHAVIORAL PROCESS that connects these incidents, despite their surface differences. Focus on the common process, not the surface descriptions. E.g.: 'Both incidents describe the teacher adapting their lesson plan in real-time when technology fails, though one involves a projector and the other a student platform.'"
          }
        }
      }
    }
  }
}
```

---

## Ejemplo de Input/Output

### Input

```json
{
  "operational_question": "¿Cómo procesan los docentes su relación con la tecnología en el aula?",
  "object_of_study": "docentes de secundaria",
  "batch_incidents_json": [
    {"id": "inc_001", "jot_text": "La profesora llega a las 6am para revisar que todos los proyectores funcionen antes de la clase."},
    {"id": "inc_002", "jot_text": "El docente prepara planes B en papel por si la plataforma se cae durante el examen."},
    {"id": "inc_003", "jot_text": "Los alumnos usan sus celulares para investigar durante la clase y la maestra lo incorpora al plan."},
    {"id": "inc_004", "jot_text": "Cuando la red falló, improvisó una actividad grupal que no requería tecnología."}
  ]
}
```

### Output

```json
{
  "local_groups": [
    {
      "signal": "anticipating technology failure",
      "incident_ids": ["inc_001", "inc_002"],
      "rationale": "Both incidents describe the teacher proactively preparing for technology breakdowns before they occur, though one involves hardware checks and the other backup materials."
    },
    {
      "signal": "adapting in real-time to disruption",
      "incident_ids": ["inc_002", "inc_004"],
      "rationale": "Both incidents show the teacher pivoting their planned approach when technology becomes unavailable, whether by having paper alternatives ready or improvising on the spot."
    },
    {
      "signal": "integrating student technology",
      "incident_ids": ["inc_003"],
      "rationale": "This single incident describes incorporating student-owned devices into instruction — insufficient for a group with the current batch, but noted for potential cross-batch merging."
    }
  ]
}
```

> **Nota:** `inc_003` aparece solo — no forma grupo con ≥2 incidentes en este batch. En la práctica, el modelo lo omitiría o lo dejaría como grupo de 1 (el Reduce lo descartará). Alternativamente, puede devolver `local_groups` vacío para ese incidente.

---

## Parámetros de Inferencia (Nemotron FLASH)

```
temperature:           0.1
max_tokens:            1500
repetition_penalty:    1.1
frequency_penalty:     1.15
top_p:                 0.9
json_object:           NO (inline schema en el prompt)
timeout API:           600s
```

---

## Notas de Implementación

1. **Fragmentación:** Si un batch excede ~2000 caracteres por incidente (raro en jots), usar corte semántico con overlap (ver `PROMPT_CRITERIA.md` §Fragmentación).
2. **Paralelismo:** Este prompt es `parallelizable: true`. El CWM despacha todos los batches simultáneamente en `ThreadPoolExecutor`.
3. **Schema inline:** El JSON Schema va en el cuerpo del prompt (NO como `response_format`). Nemotron vía Together.ai responde vacío con `json_object=true`.
4. **Few-shot opcional:** Para mejorar adherencia al formato, se puede añadir 1 ejemplo few-shot en el system prompt si la tasa de JSON malformado supera el 5%.
5. **Grupos de 1 incidente:** Si un incidente no encaja en ningún grupo con ≥2 miembros, simplemente no se incluye en `local_groups`. El Reduce no puede trabajar con singletons — el CWM los descarta o los acumula para un batch de "rezagados".
