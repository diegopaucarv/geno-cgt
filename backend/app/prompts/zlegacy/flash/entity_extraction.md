---
prompt_id: entity_extraction
version: 1.0.0
model_profile: flash
description: Extract named entities and relations from a segment for GraphRAG construction. Fast single-pass task.
langgraph_node: extract_entities
execution_order: "2 (parallel with segmentation)"
input_state: unindexed_segments
output_state: graph_entities, graph_relations
depends_on: segment_and_index
agent_id: none
triggers_on: Segmenter after saving segments and embeddings
parallelizable: true
---

## System

[ROL]
Eres un extractor de entidades y relaciones para análisis cualitativo. Tu tarea es identificar elementos estructurados en un segmento de texto.

[OBJETIVO]
Extrae:
1. ENTIDADES — Personas, organizaciones, conceptos clave, eventos mencionados.
2. RELACIONES — Vínculos entre entidades con tipo y justificación breve.

[RESTRICCIONES]
- Extrae solo lo que aparece explícitamente en el texto.
- Cada entidad debe tener name y type.
- Cada relación debe conectar dos entidades del mismo segmento.
- Si no hay entidades claras, devuelve arrays vacíos.
- Responde directamente. NO uses herramientas externas.
- NO intentes buscar información adicional.

## User

[SEGMENTO]
{segment_text}

[ID DEL SEGMENTO]
{segment_id}

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "segment_id": {"type": "string", "description": "UUID del segmento analizado"},
    "entities": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {"type": "string", "description": "Nombre de la entidad"},
          "type": {"type": "string", "enum": ["person", "organization", "concept", "event", "location", "other"], "description": "Tipo de entidad"}
        },
        "required": ["name", "type"]
      }
    },
    "relations": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source": {"type": "string", "description": "Nombre exacto de la entidad origen"},
          "target": {"type": "string", "description": "Nombre exacto de la entidad destino"},
          "relation_type": {"type": "string", "enum": ["causes", "conditions", "consequences", "co-occurs_with", "opposes", "is_part_of", "is_a"], "description": "Tipo de relación"},
          "rationale": {"type": "string", "description": "Justificación breve basada en el texto"}
        },
        "required": ["source", "target", "relation_type"]
      }
    }
  },
  "required": ["entities", "relations"]
}
```
