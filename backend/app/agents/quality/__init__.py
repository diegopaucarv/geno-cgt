"""Quality evaluation package.

Proporciona evaluacion algoritmica de codigos (regex + TEI + heuristicas)
para reducir llamadas LLM al critic. O6 del plan de optimizaciones.
"""

from app.agents.quality.scorer import (
    compare_codes_for_redundancy,
    evaluate_codes_algorithmic,
    validate_coding_style,
)

__all__ = [
    "compare_codes_for_redundancy",
    "evaluate_codes_algorithmic",
    "validate_coding_style",
]
