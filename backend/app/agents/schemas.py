"""JSON Schemas para structured output (O1 del plan de optimizaciones).

Forzan al LLM a devolver JSON con estructura exacta via response_format.
Eliminan retries por parseo fallido. Compatible con Together.ai y OpenAI.

Uso:
    from app.agents.schemas import CRITIC_SCHEMA
    response = llm.chat(..., response_format=CRITIC_SCHEMA)
"""

# ── Code Critic Schema (FLASH) ────────────────────────────────────
CRITIC_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_critic_output",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "all_valid": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "code_name": {"type": "string"},
                            "problem": {
                                "type": "string",
                                "enum": [
                                    "wrong_style",
                                    "vague_definition",
                                    "redundant",
                                    "not_grounded",
                                    "missing_properties",
                                ],
                            },
                            "suggestion": {"type": "string"},
                        },
                        "required": ["code_name", "problem", "suggestion"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["all_valid", "issues"],
            "additionalProperties": False,
        },
    },
}

# ── Plan Executor Plan Schema ─────────────────────────────────────
PLAN_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "agent_plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string", "minLength": 10},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "minimum": 1},
                            "action": {"type": "string"},
                            "description": {"type": "string"},
                            "input": {"type": "object"},
                        },
                        "required": ["id", "action", "description", "input"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                    "maxItems": 10,
                },
                "success_criteria": {"type": "string", "minLength": 5},
            },
            "required": ["goal", "steps", "success_criteria"],
            "additionalProperties": False,
        },
    },
}

# ── Saturation Reflection Schema ───────────────────────────────────
REFLECTION_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "saturation_reflection",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "narrative_summary": {"type": "string", "maxLength": 500},
                "prioritized_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "impact": {
                                "type": "string",
                                "enum": ["high", "medium", "low"],
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["action", "impact"],
                        "additionalProperties": False,
                    },
                    "maxItems": 5,
                },
                "saturation_confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                },
                "blind_spots": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["narrative_summary", "prioritized_actions"],
            "additionalProperties": False,
        },
    },
}

# ── Theme Grouper Schema (FLASH) ───────────────────────────────────
THEME_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "theme_grouper_output",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "themes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "indicators": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "suggested_gerundio": {"type": "string"},
                        },
                        "required": ["name", "indicators", "suggested_gerundio"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["themes"],
            "additionalProperties": False,
        },
    },
}

# ── Code Namer Schema (FLASH) ──────────────────────────────────────
NAMER_SCHEMA: dict = {
    "type": "json_schema",
    "json_schema": {
        "name": "code_namer_output",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "suggestions": {
                    "type": "array",
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "style_used": {
                                "type": "string",
                                "enum": [
                                    "gerundio",
                                    "in_vivo",
                                    "nominalizacion",
                                    "parafrasis",
                                    "tema_subtema",
                                    "causal",
                                ],
                            },
                            "rationale": {"type": "string"},
                        },
                        "required": ["name", "style_used", "rationale"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["suggestions"],
            "additionalProperties": False,
        },
    },
}
