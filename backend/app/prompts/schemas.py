"""
JSON Schemas para respuestas estructuradas de todos los agentes CGT.

Cada agente tiene un schema que el LLMClient inyecta como [OUTPUT FORMAT]
al final del system prompt. Esto garantiza respuestas parseables.
"""

from typing import Any

# ═══════════════════════════════════════════════════════════════════════
# A1 — POPULATION_CONTEXT_BUILDER
# ═══════════════════════════════════════════════════════════════════════

A1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["surprising_details", "language_patterns", "data_production_context"],
    "properties": {
        "surprising_details": {
            "type": "string",
            "description": "Qué revela este documento sobre la población que no sabíamos. Integrar lo nuevo con lo existente.",
        },
        "language_patterns": {
            "type": "string",
            "description": "Metáforas, eufemismos, estructuras discursivas, términos nativos.",
        },
        "data_production_context": {
            "type": "string",
            "description": "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.",
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════
# A2 — PROCESS_IDENTIFIER
# ═══════════════════════════════════════════════════════════════════════

A2_FIRST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["process_description"],
    "properties": {
        "process_description": {
            "type": "string",
            "description": "Descripción en gerundio del proceso central que el entrevistado intenta resolver continuamente, con 2-3 oraciones de explicación.",
        }
    },
}

A2_COMPARE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "process_description",
        "similarity_to_previous",
        "difference_from_previous",
    ],
    "properties": {
        "process_description": {
            "type": "string",
            "description": "Descripción en gerundio del proceso central de ESTE entrevistado.",
        },
        "similarity_to_previous": {
            "type": "string",
            "description": "En qué se PARECE al proceso del entrevistado anterior.",
        },
        "difference_from_previous": {
            "type": "string",
            "description": "En qué se DIFERENCIA del proceso del entrevistado anterior.",
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════
# A3 — SENSE_MAKER
# ═══════════════════════════════════════════════════════════════════════

A3_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["sense_status", "hypotheses"],
    "properties": {
        "sense_status": {
            "type": "string",
            "enum": ["modifies", "changes_substantially", "no_change"],
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "level", "evidence"],
                "properties": {
                    "text": {"type": "string", "description": "Hipótesis completa."},
                    "level": {
                        "type": "string",
                        "enum": ["general", "specific", "emergent"],
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Evidencia concreta que la apoya.",
                    },
                },
            },
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════
# B1 — SAMPLING_DISTILLER
# ═══════════════════════════════════════════════════════════════════════

B1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["sampling_dimensions"],
    "properties": {
        "sampling_dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "name",
                    "description",
                    "contrast_criteria",
                    "extreme_criteria",
                    "consistent_criteria",
                ],
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "contrast_criteria": {"type": "string"},
                    "extreme_criteria": {"type": "string"},
                    "consistent_criteria": {"type": "string"},
                },
            },
        }
    },
}

# ═══════════════════════════════════════════════════════════════════════
# B2 — OPEN_CODER
# ═══════════════════════════════════════════════════════════════════════

B2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["codes"],
    "properties": {
        "codes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "code_name",
                    "definition",
                    "indicators",
                    "variations",
                    "relationship_to_existing",
                ],
                "properties": {
                    "code_name": {
                        "type": "string",
                        "description": "Nombre en gerundio.",
                    },
                    "definition": {"type": "string"},
                    "indicators": {"type": "array", "items": {"type": "string"}},
                    "variations": {"type": "string"},
                    "relationship_to_existing": {"type": "string"},
                },
            },
        }
    },
}

# ═══════════════════════════════════════════════════════════════════════
# B3 — HYPOTHESIS_GENERATOR
# ═══════════════════════════════════════════════════════════════════════

B3_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["hypotheses"],
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "level", "evidence"],
                "properties": {
                    "text": {"type": "string"},
                    "level": {
                        "type": "string",
                        "enum": ["general", "specific", "emergent"],
                    },
                    "evidence": {"type": "string"},
                },
            },
        }
    },
}

# ═══════════════════════════════════════════════════════════════════════
# D1 — CORE_CONCERN_FINDER
# ═══════════════════════════════════════════════════════════════════════

D1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["core_concern_candidates"],
    "properties": {
        "core_concern_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "statement",
                    "rationale",
                    "supporting_codes",
                    "supporting_memos",
                ],
                "properties": {
                    "statement": {"type": "string"},
                    "rationale": {"type": "string"},
                    "supporting_codes": {"type": "array", "items": {"type": "string"}},
                    "supporting_memos": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}

# ═══════════════════════════════════════════════════════════════════════
# D2 — INTERCHANGEABILITY_TESTER
# ═══════════════════════════════════════════════════════════════════════

D2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdict", "rationale"],
    "properties": {
        "verdict": {"type": "string", "enum": ["valid", "refine", "split"]},
        "rationale": {"type": "string"},
        "suggested_action_if_not_valid": {"type": "string"},
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S1 — MAIN_CONCERN_PROPOSER (A14)
# ═══════════════════════════════════════════════════════════════════════

S1_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["main_concern_candidates"],
    "properties": {
        "main_concern_candidates": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": [
                    "statement",
                    "rationale",
                    "supporting_code_ids",
                    "orphan_patterns",
                ],
                "properties": {
                    "statement": {"type": "string"},
                    "rationale": {"type": "string"},
                    "supporting_code_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "supporting_memo_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "orphan_patterns": {"type": "array", "items": {"type": "string"}},
                    "theoretical_grab": {
                        "type": "string",
                        "enum": ["Alto", "Medio", "Bajo"],
                    },
                },
            },
        },
        "cross_cutting_observations": {"type": "string"},
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S2 — MAIN_CONCERN_CRITIC
# ═══════════════════════════════════════════════════════════════════════

S2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["evaluations", "ranked_recommendation"],
    "properties": {
        "evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "candidate_statement",
                    "verdict",
                    "rationale",
                    "grounding_assessment",
                ],
                "properties": {
                    "candidate_statement": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["SAT", "MOD", "FORCED"]},
                    "rationale": {"type": "string"},
                    "grounding_assessment": {"type": "string"},
                    "coverage_ratio": {"type": "number", "minimum": 0, "maximum": 1},
                    "abstraction_assessment": {
                        "type": "string",
                        "enum": ["adequate", "too_concrete", "too_abstract"],
                    },
                    "suggestion": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "ranked_recommendation": {"type": "string"},
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S3 — CORE_EMERGENCE_PROPOSER (A15)
# ═══════════════════════════════════════════════════════════════════════

S3_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["core_category_candidates"],
    "properties": {
        "core_category_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "code_id",
                    "code_label",
                    "why_central",
                    "theoretical_grab",
                ],
                "properties": {
                    "code_id": {"type": "string"},
                    "code_label": {"type": "string"},
                    "why_central": {"type": "string"},
                    "relation_to_core_concern": {
                        "type": "string",
                        "enum": [
                            "is_the_core",
                            "processes",
                            "conditions",
                            "consequences",
                            "strategies",
                        ],
                    },
                    "theoretical_grab": {
                        "type": "string",
                        "enum": ["Alto", "Medio", "Bajo"],
                    },
                    "connected_code_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "connected_code_count": {"type": "integer"},
                    "limitations": {"type": "string"},
                },
            },
        },
        "no_core_detected": {"type": "boolean"},
        "no_core_rationale": {"type": "string"},
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S4 — CORE_EMERGENCE_CRITIC (A16) — FLASH
# ═══════════════════════════════════════════════════════════════════════

S4_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["verdicts"],
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["code_id", "code_label", "verdict", "rationale"],
                "properties": {
                    "code_id": {"type": "string"},
                    "code_label": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["valid", "refine", "split"]},
                    "rationale": {"type": "string"},
                    "interchangeable_pairs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "incident_a_doc": {"type": "string"},
                                "incident_b_doc": {"type": "string"},
                                "why_interchangeable": {"type": "string"},
                            },
                        },
                    },
                    "non_interchangeable_pairs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "incident_a_doc": {"type": "string"},
                                "incident_b_doc": {"type": "string"},
                                "why_different": {"type": "string"},
                            },
                        },
                    },
                    "suggested_action_if_not_valid": {"type": "string"},
                },
            },
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S5 — SELECTIVE_REDUCTION_PROPOSER (NEW_SR)
# ═══════════════════════════════════════════════════════════════════════

S5_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["reduced_codes", "discarded_codes", "reduction_summary"],
    "properties": {
        "reduced_codes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "new_label",
                    "entity_type",
                    "definition",
                    "source_code_ids",
                    "relation_to_core",
                ],
                "properties": {
                    "new_label": {"type": "string"},
                    "entity_type": {
                        "type": "string",
                        "enum": ["core_category", "related_category", "secondary_code"],
                    },
                    "definition": {"type": "string"},
                    "source_code_ids": {"type": "array", "items": {"type": "string"}},
                    "relation_to_core": {
                        "type": "string",
                        "enum": [
                            "is_the_core",
                            "processes",
                            "conditions",
                            "consequences",
                            "strategies",
                        ],
                    },
                    "properties_inherited": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "gradient": {"type": "string"},
                                "source_code_id": {"type": "string"},
                            },
                        },
                    },
                    "interchangeability_rationale": {"type": "string"},
                    "needs_more_data": {"type": "boolean"},
                },
            },
        },
        "discarded_codes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "code_id",
                    "code_label",
                    "discard_rationale",
                    "discard_category",
                ],
                "properties": {
                    "code_id": {"type": "string"},
                    "code_label": {"type": "string"},
                    "discard_rationale": {"type": "string"},
                    "discard_category": {
                        "type": "string",
                        "enum": [
                            "unrelated_to_core",
                            "descriptive_not_behavioral",
                            "single_occurrence",
                            "superseded_by_fusion",
                        ],
                    },
                },
            },
        },
        "reduction_summary": {
            "type": "object",
            "required": [
                "original_code_count",
                "reduced_code_count",
                "discarded_count",
                "fusion_groups_count",
            ],
            "properties": {
                "original_code_count": {"type": "integer"},
                "reduced_code_count": {"type": "integer"},
                "discarded_count": {"type": "integer"},
                "fusion_groups_count": {"type": "integer"},
                "reduction_ratio": {"type": "number"},
                "methodological_notes": {"type": "string"},
            },
        },
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S6 — SELECTIVE_REDUCTION_CRITIC
# ═══════════════════════════════════════════════════════════════════════

S6_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["discard_evaluations", "fusion_evaluations"],
    "properties": {
        "discard_evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["code_id", "code_label", "verdict", "rationale"],
                "properties": {
                    "code_id": {"type": "string"},
                    "code_label": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["SAT", "MOD", "FORCED"]},
                    "rationale": {"type": "string"},
                    "suggested_action": {"type": "string"},
                },
            },
        },
        "fusion_evaluations": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["new_label", "source_code_ids", "verdict", "rationale"],
                "properties": {
                    "new_label": {"type": "string"},
                    "source_code_ids": {"type": "array", "items": {"type": "string"}},
                    "verdict": {"type": "string", "enum": ["SAT", "MOD", "FORCED"]},
                    "rationale": {"type": "string"},
                    "codes_to_remove_from_fusion": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "suggested_action": {"type": "string"},
                },
            },
        },
        "false_positives": {"type": "array", "items": {"type": "string"}},
        "false_negatives": {"type": "array", "items": {"type": "string"}},
        "overall_assessment": {"type": "string"},
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S7 — CORE_SATURATION_PROPOSER (A25)
# ═══════════════════════════════════════════════════════════════════════

S7_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["category_id", "document_id", "proposed_expansions"],
    "properties": {
        "category_id": {"type": "string"},
        "document_id": {"type": "string"},
        "proposed_expansions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["expansion_type", "description", "evidence_quote"],
                "properties": {
                    "expansion_type": {
                        "type": "string",
                        "enum": [
                            "new_property",
                            "dimensional_expansion",
                            "new_condition",
                            "new_consequence",
                            "new_strategy",
                        ],
                    },
                    "target_element": {"type": "string"},
                    "new_element_name": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                    "incident_index": {"type": "integer"},
                    "expansion_nature": {
                        "type": "string",
                        "enum": ["dimensional", "essential"],
                    },
                    "relation_to_core": {"type": "string"},
                },
            },
        },
        "confirmed_only": {"type": "boolean"},
        "synthesis_note": {"type": "string"},
    },
}

# ═══════════════════════════════════════════════════════════════════════
# S8 — CORE_SATURATION_CRITIC — FLASH
# ═══════════════════════════════════════════════════════════════════════

S8_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["expansion_verdicts", "did_state_expand"],
    "properties": {
        "expansion_verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["expansion_index", "verdict", "rationale"],
                "properties": {
                    "expansion_index": {"type": "integer"},
                    "expansion_type": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["SAT", "MOD", "FORCED"]},
                    "rationale": {"type": "string"},
                    "covered_by_property": {"type": "string"},
                    "suggested_refinement": {"type": "string"},
                },
            },
        },
        "did_state_expand": {"type": "boolean"},
        "expansion_count": {"type": "integer"},
        "confirmation_count": {"type": "integer"},
        "saturation_note": {"type": "string"},
    },
}

# ── Mapa: agent_id → schema ──────────────────────────────────────────

AGENT_SCHEMAS: dict[str, dict] = {
    # Phase 2-3 — Open Coding
    "a1": A1_SCHEMA,
    "a2_first": A2_FIRST_SCHEMA,
    "a2_compare": A2_COMPARE_SCHEMA,
    "a3": A3_SCHEMA,
    "b1": B1_SCHEMA,
    "b2": B2_SCHEMA,
    "b3": B3_SCHEMA,
    # Phase 4d — Core Concern (legacy, merged into S1-S4)
    "d1": D1_SCHEMA,
    "d2": D2_SCHEMA,
    # Phase 5b — Selective Coding (nuevos)
    "main_concern_proposer": S1_SCHEMA,
    "main_concern_critic": S2_SCHEMA,
    "core_emergence_proposer": S3_SCHEMA,
    "core_emergence_critic": S4_SCHEMA,
    "selective_reduction_proposer": S5_SCHEMA,
    "selective_reduction_critic": S6_SCHEMA,
    "core_saturation_proposer": S7_SCHEMA,
    "core_saturation_critic": S8_SCHEMA,
}
