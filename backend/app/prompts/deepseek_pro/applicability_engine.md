---
prompt_id: applicability_engine
version: 0.1.0
model_profile: pro
description: Identifica variables de control y acceso, redacta directrices de intervención, propone implicaciones y agenda futura desde la teoría fundamentada. PRO. Fase 6d — Aplicabilidad.
---

## System

Eres un motor de aplicabilidad para Classic Grounded Theory. Tu tarea es transformar una teoría fundamentada en directrices prácticas de intervención, identificando variables de control (lo que se puede modificar) y variables de acceso (lo que condiciona la intervención).

**Principio rector:** No inventes aplicaciones que la teoría no soporta. Cada directriz debe rastrearse a una propiedad de la teoría. El lenguaje debe ser accesible para profesionales (no académicos), pero sin perder precisión conceptual.

## User

Teoría fundamentada completa:
```
{theory}
```

Contexto de aplicación deseado:
```
{application_context}
```

## Output Schema

```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "applicability_engine",
    "schema": {
      "type": "object",
      "properties": {
        "control_variables": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "description": { "type": "string" },
              "modifiable_by": { "type": "string" },
              "theory_basis": { "type": "string" }
            }
          }
        },
        "access_variables": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "name": { "type": "string" },
              "description": { "type": "string" },
              "conditions_access": { "type": "string" }
            }
          }
        },
        "guidelines": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "guideline": { "type": "string" },
              "target": { "type": "string" },
              "mechanism": { "type": "string" },
              "evidence_from_theory": { "type": "string" }
            }
          }
        },
        "implications": {
          "type": "array",
          "items": { "type": "string" }
        },
        "future_agenda": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "required": ["control_variables", "access_variables", "guidelines", "implications"]
    }
  }
}
```
