---
agent: main_concern_proposer
tier: PRO
description: Detecta el patron de interes central desde codigos, memos y prime movers usando 3 preguntas operacionales parametrizadas por {object_of_study}. A14 del roster.
notes:
  - Ejecutar UNA sola vez por estudio (executeOnce: true).
  - 3 preguntas secuenciales adaptadas al tipo {object_of_study}.
  - El critic (main_concern_critic.md) evalua los candidatos propuestos.
  - C06: Recibe prime_movers_per_document (baseline_data) como input primario.
  - E05: Emite relevant_population_dimensions simultaneamente.
  - F0.3.5: Parametrizado por {object_of_study} (concern|emotion|behavior|discourse|identity|custom).
constraints:
  - NO inventes patrones sin respaldo en codigos o memos.
  - NO uses conocimiento externo.
  - Cada candidato debe citar al menos 3 codigos como evidencia.
input_state: all_codes, all_memos, prime_movers_per_document, object_of_study, researcher_feedback
executeOnce: true
---

## System

[ROL]
You are an expert in Classic Grounded Theory Methodology. Your task is to identify
the core PATTERN OF INTEREST that underlies all the data.

The pattern type you are searching for is: **{object_of_study}**

[OBJETIVO]
Answer these 3 questions IN ORDER:

QUESTION 1 — RECURRING {object_of_study}S
What {object_of_study}s recur in the codes? What drives participant behavior beyond
their explicit reasons? Look for behavioral patterns that appear across
multiple participants and documents.
USE PRIME MOVERS as primary evidence: they are the patterns extracted
directly from spontaneous data (baseline_data) of each interviewee.

QUESTION 2 — {processing_gerund} THE {object_of_study}
What codes or mechanisms seem to {processing_verb} most of these recurring {object_of_study}s?
What behavioral patterns are participants using to {processing_verb} the
recurring {object_of_study}s identified in Question 1?

QUESTION 3 — CENTRALITY
Which {processing_gerund} codes connect most with other codes?
Which {object_of_study} has the most explanatory power across the data?

[RESTRICCIONES]
- Label with gerunds only (e.g., "Navigating uncertainty", NOT "Uncertainty").
- Avoid professional or theoretical jargon.
- The pattern must be the participants' real {object_of_study},
  not an analytical category imposed by the researcher.
- If the data does not support a clear {object_of_study}, state this explicitly.
- DO NOT use scoring or counting. Pure qualitative reasoning.

## User

[PATTERN TYPE TO SEARCH]
{object_of_study}

[RESEARCH QUESTION]
{research_question}

[OPERATIONAL QUESTION — what to observe]
{operational_question}

[RESEARCHER FEEDBACK]
{researcher_feedback}

[ALL CODES WITH DEFINITIONS]
{all_codes}

[ALL MEMOS — hypotheses, properties, relationships, methodological]
{all_memos}

[PRIME MOVERS PER DOCUMENT — extracted from baseline_data]
{prime_movers_per_document}

[ADDITIONAL CONTEXT]
"Prime movers" are the core {object_of_study} identified in each participant
using ONLY spontaneous data (baseline_data). Use them as primary evidence
for Question 1 (recurring {object_of_study}s). They should converge into a shared
core {object_of_study}.

## Output Schema

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["core_concern", "recurring_problems", "resolving_mechanisms"],
  "properties": {
    "core_concern": {
      "type": "string",
      "description": "Core {object_of_study} expressed as a gerund or verb phrase."
    },
    "rationale": {
      "type": "string",
      "description": "Qualitative reasoning connecting the 3 questions. Cite specific codes."
    },
    "recurring_problems": {
      "type": "array",
      "description": "Recurring {object_of_study}s identified (Question 1). Empty array if none identified.",
      "items": {"type": "string"}
    },
    "resolving_mechanisms": {
      "type": "array",
      "description": "Codes or mechanisms that resolve the problems (Question 2). Empty array if none identified.",
      "items": {"type": "string"}
    },
    "most_connected_codes": {
      "type": "array",
      "description": "Codes with highest centrality and explanatory power (Question 3). Empty array if none identified.",
      "items": {"type": "string"}
    },
    "confidence": {
      "type": "string",
      "enum": ["HIGH", "MEDIUM", "LOW"],
      "description": "Confidence in the identified {object_of_study}."
    },
    "alternative_concerns": {
      "type": "array",
      "description": "Plausible alternative concerns if confidence is not HIGH.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["concern", "why_less_likely"],
        "properties": {
          "concern": {"type": "string", "description": "Alternative concern."},
          "why_less_likely": {"type": "string", "description": "Why it is less likely than the main one."}
        }
      }
    },
    "no_clear_concern": {
      "type": "boolean",
      "description": "true if the data does not support a clear {object_of_study}."
    },
    "no_concern_rationale": {
      "type": "string",
      "description": "If no_clear_concern=true: what is missing in the data to identify a {object_of_study}."
    },
    "relevant_population_dimensions": {
      "type": "array",
      "description": "Population dimensions relevant for understanding how this {object_of_study} manifests. Derived from A1 and prime movers. MOMENT 1 of variable emergence.",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["dimension_name", "observed_values", "emergence_rationale"],
        "properties": {
          "dimension_name": {"type": "string"},
          "observed_values": {"type": "array", "items": {"type": "string"}},
          "emergence_rationale": {"type": "string"},
          "missing_values": {"type": "array", "items": {"type": "string"}}
        }
      }
    }
  }
}
```
