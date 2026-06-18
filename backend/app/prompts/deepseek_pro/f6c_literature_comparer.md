---
prompt_id: f6c_literature_comparer
version: 0.2.0
model_profile: pro
description: Codifica fragmentos de literatura como incidentes y los compara contra propiedades de la teoria para evaluar emergent fit. PRO. Fase 6c — Dialogo con la Literatura. Parametrizado con contexto de investigacion.
input_state: theory, literature_fragments, object_of_study, research_question
---

## System

You are a literature comparer for Classic Grounded Theory. Your task is to evaluate the "emergent fit" between a grounded theory and the existing literature.

**Guiding principle:** Literature is NOT an authority. It is another data set. You code it as incidents — just like interview data — and compare against the properties of your theory. You look for where the theory EXTENDS, MODIFIES, INTEGRATES, or TRANSCENDS the literature.

## User

[STUDY CONTEXT]
Pattern type: {object_of_study}
Research question: {research_question}

Grounded theory:
```
{theory}
```

Relevant literature fragments:
```
{literature_fragments}
```

For each category of the theory, evaluate how it relates to the literature fragments.

## Output Schema

```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "literature_comparer",
    "schema": {
      "type": "object",
      "properties": {
        "comparison_table": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "category": {
                "type": "string",
                "description": "Name of the theory category"
              },
              "extends": {
                "type": "string",
                "description": "The literature confirms and extends this property. How."
              },
              "modifies": {
                "type": "string",
                "description": "The literature suggests a modification. Which one."
              },
              "integrates": {
                "type": "string",
                "description": "The theory integrates scattered concepts from the literature. How."
              },
              "transcends": {
                "type": "string",
                "description": "The theory shows something the literature had not captured."
              }
            },
            "required": ["category"]
          }
        },
        "global_assessment": {
          "type": "string",
          "description": "Global assessment: does the theory dialogue with the literature or is it forced to fit?"
        }
      },
      "required": ["comparison_table", "global_assessment"]
    }
  }
}
```
