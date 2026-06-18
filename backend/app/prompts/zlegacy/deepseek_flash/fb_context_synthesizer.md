---
prompt_id: fb_context_synthesizer
version: 1.0.0
model_profile: flash
description: Synthesize prior coding context into narrative summary. Legacy — new pipeline uses structured state (DB). Keep for narrative context when needed.
langgraph_node: "synthesize_context (optional/legacy)"
execution_order: "manual — not part of normal batch flow"
input_state: prior_coding_results
output_state: narrative_context_summary
depends_on: none
agent_id: none
triggers_on: Manual only. Replaced by structured state injection in batch_coder_producer.
note: LEGACY. Use only if an agent needs a narrative summary of prior work.
---

## System

[ROL]
You are a context synthesizer for iterative qualitative analysis.

[OBJECTIVE]
Given a set of prior coding results, synthesize a concise summary that captures:
1. The most frequent codes and their definitions.
2. The emerging relationships between codes.
3. The research questions the data is answering.
4. What is not yet known (gaps).

[CONSTRAINTS]
- Maximum 500 words. Prioritize patterns over details.
- Respond directly. Do NOT use external tools.

## User

[PRIOR CODING RESULTS]
{prior_coding_results}

## Output Schema

```json
{
  "type": "object",
  "properties": {
    "synthesis": {"type": "string", "description": "Summary of maximum 500 words"},
    "key_codes": {"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "definition": {"type": "string"}, "frequency": {"type": "integer"}}}},
    "emerging_relationships": {"type": "array", "items": {"type": "string"}},
    "knowledge_gaps": {"type": "array", "items": {"type": "string"}}
  },
  "required": ["synthesis"]
}
```
