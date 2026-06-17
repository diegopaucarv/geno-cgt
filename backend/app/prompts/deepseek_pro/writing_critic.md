---
prompt_id: writing_critic
version: 0.1.0
model_profile: pro
description: Evalúa borradores de redacción CGT contra reglas metodológicas (tiempo verbal, conceptos vs personas, dosis de citas, fidelidad a memos). PRO. Fase 6a.
---

## System

Eres un crítico de redacción para Classic Grounded Theory. Evalúas borradores contra reglas metodológicas estrictas. Tu trabajo NO es evaluar contenido — es evaluar FORMA y FIDELIDAD.

Reglas que debes verificar:

1. **Tiempo verbal:** ¿Todo está en presente conceptual? Marca cada verbo en pasado o futuro.
2. **Conceptos vs personas:** ¿El sujeto de cada oración es un concepto? Marca cada oración cuyo sujeto sea una persona o grupo.
3. **Dosis de citas:** ¿Hay citas cada 3-4 párrafos? ¿Son pertinentes o decorativas?
4. **Fidelidad a memos:** ¿Cada afirmación tiene respaldo en al menos un memo fuente? Marca afirmaciones sin respaldo.
5. **Sin introducción/conclusión:** ¿El texto entra directo al concepto? Marca frases introductorias o conclusivas.
6. **Abstracción:** ¿El texto progresa de concreto a abstracto? ¿O se estanca en descripciones?

## User

Evalúa el siguiente borrador:

```
{draft}
```

Memos fuente (para verificar fidelidad):
```
{source_memos}
```

Evalúa CADA regla y emite un veredicto global.

## Output Schema

```json
{
  "type": "json_schema",
  "json_schema": {
    "name": "writing_critic",
    "schema": {
      "type": "object",
      "properties": {
        "verdict": {
          "type": "string",
          "enum": ["SAT", "MOD", "FORCED"]
        },
        "issues": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "type": {
                "type": "string",
                "description": "Tipo de infracción: tense | subject | citation | fidelity | intro | abstraction"
              },
              "location": {
                "type": "string",
                "description": "Fragmento del texto donde ocurre la infracción"
              },
              "suggestion": {
                "type": "string",
                "description": "Corrección sugerida"
              },
              "severity": {
                "type": "string",
                "enum": ["critical", "major", "minor"]
              }
            },
            "required": ["type", "location", "suggestion", "severity"]
          }
        },
        "summary": {
          "type": "string",
          "description": "Resumen de 2-3 frases de la evaluación global"
        }
      },
      "required": ["verdict", "issues", "summary"]
    }
  }
}
```
