# agent2_agent_contracts.md — Prerequisite Changes 2, 3, 7

**Date:** 2026-06-21
**Status:** Implemented
**Design Reference:** `/Documentacion/cgt_alignment/7-MicroOrchestrators-Final.md` (lines 370–448)

---

## Executive Summary

Three prerequisite changes were implemented to prepare the GT agent contracts for the ChainOrchestrator v3 system:

| Change | Description | Files Modified |
|--------|-------------|----------------|
| **CHANGE 2** | Add `_self_evaluation` to agent output schemas | 28 schema files (7 agents × 4 languages) |
| **CHANGE 3** | Refactor `run_agent()` to accept `conversation_history` and return `AgentOutput` | `workers/heavy/llm_client.py` + 4 caller fixups |
| **CHANGE 7** | ReactRunner exposes conversation history | `backend/app/agents/react_runner.py` |

---

## CHANGE 2: `_self_evaluation` in Agent Output Schemas

### Affected Agents (7 Priority)

| Agent ID | Directory | Description |
|----------|-----------|-------------|
| `a1` | `agents/a1/` | Population context builder |
| `a2` | `agents/a2/` | Process identifier |
| `a3` | `agents/a3/` | Sense maker |
| `util_punctuator` | `agents/util_punctuator/` | Text corrector |
| `fb_incident_grouper` | `agents/fb_incident_grouper/` | B1 Incident grouper |
| `fb_code_generator` | `agents/fb_code_generator/` | B2 Code generator |
| `fd_category_synthesizer` | `agents/fd_category_synthesizer/` | FD Category synthesizer |

### What Was Added

Each `schema.{lang}.json` file (4 languages × 7 agents = 28 files) received:

1. `"_self_evaluation"` added to the top-level `required` array
2. `_self_evaluation` property added as the **last** entry in `properties`

The `_self_evaluation` schema:

```json
{
  "_self_evaluation": {
    "type": "object",
    "properties": {
      "needs_retry": {
        "type": "boolean",
        "description": "true if you consider your output is incomplete..."
      },
      "retry_reason": {
        "type": ["string", "null"],
        "description": "ONLY if needs_retry=true. CONCRETE and ACTIONABLE..."
      },
      "suggested_action": {
        "type": "string",
        "enum": ["proceed", "retry", "escalate_to_hitl", "skip", "abort"],
        "description": "Recommended action..."
      }
    },
    "required": ["needs_retry", "suggested_action"]
  }
}
```

Descriptions are localized for each language:
- **en**: English descriptions
- **es**: Spanish descriptions
- **de**: German descriptions
- **pt**: Portuguese descriptions

### Schema Compatibility

- Agents with `additionalProperties: false` (like `util_punctuator`, `fb_incident_grouper`, `fd_category_synthesizer`) still work — `_self_evaluation` is an explicit property, so it's allowed.
- Agents already parse `_self_evaluation` automatically (see CHANGE 3 below).
- Agents without `_self_evaluation` in output (pre-migration or non-priority) use `DEFAULT_SELF_EVAL` fallback.

---

## CHANGE 3: Refactored `run_agent()` with `AgentOutput`

### File: `workers/heavy/llm_client.py`

### New Dataclasses

```python
@dataclass
class SelfEval:
    """Parsed _self_evaluation from agent output."""
    needs_retry: bool
    retry_reason: str | None
    suggested_action: str  # "proceed" | "retry" | "escalate_to_hitl" | "skip" | "abort"

@dataclass
class AgentOutput:
    """Resultado estructurado de una ejecución de agente."""
    success: bool
    data: dict                    # The parsed JSON output
    tokens_used: int              # Total tokens for this call
    conversation: list[dict]      # Full conversation messages
    self_eval: SelfEval | None = None  # Parsed _self_evaluation from data
    error: str | None = None
    iterations: int = 0
```

### New `run_agent()` Signature

```python
def run_agent(
    self,
    agent_id: str,
    variables: dict[str, str],
    max_tokens: int | None = None,
    temperature: float | None = None,
    language: str | None = None,
    history: list[dict] | None = None,
    override_user_prompt: str | None = None,
    conversation_history: list[dict] | None = None,  # NEW
) -> AgentOutput:  # Changed from dict
```

### `conversation_history` Injection

When `conversation_history` is provided, `_call_llm()` injects it as additional messages BEFORE the `history` messages and the current user prompt:

```python
messages = [{"role": "system", "content": system_prompt}]
if conversation_history:
    messages.extend(conversation_history)  # Retry history first
if history:
    messages.extend(history)               # Current conversation
messages.append({"role": "user", "content": user_prompt})
```

### `_self_evaluation` Parsing

After `_call_llm()` returns, `run_agent()` parses `_self_evaluation` from the output:

1. If `"_self_evaluation"` is present in the data dict → parse into `SelfEval`
2. If `"_self_evaluation"` is missing → log info, use `DEFAULT_SELF_EVAL` fallback
3. If parsing fails → log warning, use default

### Backward Compatibility

`AgentOutput` supports dict-like access for backward compatibility with 60+ existing callers:

```python
output["codes"]           → output.data["codes"]       # __getitem__
output.get("codes", [])   → output.data.get("codes")   # .get()
"codes" in output         → "codes" in output.data     # __contains__
list(output.keys())       → list(output.data.keys())   # .keys()
output.items()            → output.data.items()        # .items()
```

Special keys `"error"` and `"mock_note"` are also handled at the AgentOutput level.

### `_call_llm()` Changes

- **Return type:** `dict[str, Any]` → `tuple[dict[str, Any], list[dict]]` (result + conversation)
- **New parameter:** `conversation_history: list[dict] | None = None`
- Conversation now includes system, user, assistant messages (with reasoning_content preserved)

### Caller Fixups

| File | Change |
|------|--------|
| `workers/heavy/algorithmic_checks.py` | Updated `isinstance(response, dict)` check |
| `workers/heavy/comparator.py` | Updated `isinstance(response, dict)` check |
| `workers/heavy/labeler.py` | Updated `isinstance(gen_response, dict)` check |
| `backend/app/agents/self_refiner.py` | Access `.data` for `json.dumps()` |
| `workers/heavy/incident_extractor.py` | Unpack `(result, _)` tuple from `_call_llm()` |

---

## CHANGE 7: ReactRunner Exposes Conversation History

### File: `backend/app/agents/react_runner.py`

### What Changed

1. **`__init__`**: Added `self._conversation: list[dict[str, Any]] = []`

2. **`run()` override**: Replaces `BaseAgent.run()` to capture full conversation history:
   - System prompt → appended to `_conversation`
   - Each iteration: user prompt → appended to `_conversation`, then assistant + observation captured from `_step()` additions to `history`
   - Final conversation attached to `result.data["_conversation"]`

### Conversation Format

Each entry follows the format:
```python
{"role": "system", "content": str}       # System prompt
{"role": "user", "content": str}         # User prompts
{"role": "assistant", "content": str, "reasoning_content": str}  # LLM responses
```

Observation messages from tool calls:
```python
{"role": "user", "content": "Observation: {result}"}
```

### Compatibility with Together.ai

The conversation format is compatible with Together.ai's API. Reasoning content is preserved in assistant messages.

---

## Fallback: DEFAULT_SELF_EVAL

Defined in `workers/heavy/llm_client.py`:

```python
DEFAULT_SELF_EVAL: dict[str, Any] = {
    "needs_retry": False,
    "retry_reason": None,
    "suggested_action": "proceed",
}
```

This is used when:
- An agent's output doesn't include `_self_evaluation`
- An agent's `_self_evaluation` fails to parse

Allows progressive migration — agents without `_self_evaluation` always `proceed`.

---

## Pre-Evaluation Answers

### Will old agents (without `_self_evaluation`) still work?
**YES.** The `DEFAULT_SELF_EVAL` fallback ensures they behave as before (always proceed). A warning is logged.

### Will old callers of `run_agent()` break?
**NO.** `AgentOutput` supports dict-like access (`__getitem__`, `.get()`, `__contains__`, `.keys()`, `.items()`) so existing callers that access response fields like `response.get("codes", [])` continue working.

### Is ReactRunner's conversation compatible with Together.ai API format?
**YES.** Messages use standard `{role, content}` format with optional `reasoning_content` field, matching Together.ai's expected message format.

---

## Post-Validation

### How to verify `_self_evaluation` is parsed from agent output
```python
output = llm.run_agent("a1", variables={...})
assert isinstance(output, AgentOutput)
assert output.self_eval is not None
assert output.self_eval.suggested_action in ["proceed", "retry", "escalate_to_hitl", "skip", "abort"]
```

### How to verify `conversation_history` injection works
```python
retry_history = [
    {"role": "system", "content": "You are an agent..."},
    {"role": "user", "content": "Analyze this text..."},
    {"role": "assistant", "content": '{"codes": [...]}'},
]
output = llm.run_agent("fb_code_generator", variables={...}, conversation_history=retry_history)
assert len(output.conversation) > len(retry_history)  # New messages appended
```

### How to verify fallback for agents without `_self_evaluation`
```python
# Agent without _self_evaluation in schema
output = llm.run_agent("fb_indicators_extractor", variables={...})
assert output.self_eval is not None  # Should have DEFAULT_SELF_EVAL
assert output.self_eval.needs_retry == False
assert output.self_eval.suggested_action == "proceed"
```

---

## Files Modified Summary

```
CHANGE 2 — Schema files (28 files):
  backend/app/prompts/agents/a1/schema.{en,es,de,pt}.json
  backend/app/prompts/agents/a2/schema.{en,es,de,pt}.json
  backend/app/prompts/agents/a3/schema.{en,es,de,pt}.json
  backend/app/prompts/agents/util_punctuator/schema.{en,es,de,pt}.json
  backend/app/prompts/agents/fb_incident_grouper/schema.{en,es,de,pt}.json
  backend/app/prompts/agents/fb_code_generator/schema.{en,es,de,pt}.json
  backend/app/prompts/agents/fd_category_synthesizer/schema.{en,es,de,pt}.json

CHANGE 3 — Core changes:
  workers/heavy/llm_client.py
    - Added SelfEval, AgentOutput dataclasses
    - Added DEFAULT_SELF_EVAL constant
    - Modified run_agent() signature and return type
    - Modified _call_llm() signature, return type, and message building
    - Added _self_evaluation parsing logic

CHANGE 3 — Caller fixups:
  backend/app/agents/self_refiner.py         (json.dumps compatibility)
  workers/heavy/algorithmic_checks.py         (isinstance check)
  workers/heavy/comparator.py                 (isinstance check)
  workers/heavy/labeler.py                    (isinstance check)
  workers/heavy/incident_extractor.py         (tuple unpacking)

CHANGE 7 — ReactRunner:
  backend/app/agents/react_runner.py
    - Added _conversation tracking
    - Added run() override with conversation capture
```
