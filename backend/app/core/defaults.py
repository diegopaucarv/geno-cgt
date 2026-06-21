"""
FUENTE ÚNICA de defaults para toda la config editable del sistema.

Importado por config.py (para get_config_value) y config_info.py (para schemas).
Cambia un valor aquí y se propaga a todo el sistema automáticamente.
"""

EDITABLE_DEFAULTS: dict[str, str] = {
    # ── LLM Models ──
    "MODEL_PRO": "deepseek-ai/DeepSeek-V4-Pro",
    "MODEL_PRO_MAX_TOKENS": "8192",
    "MODEL_PRO_TEMPERATURE": "0.3",
    "MODEL_FLASH": "nvidia/nemotron-3-ultra-550b-a55b",
    "MODEL_FLASH_MAX_TOKENS": "4096",
    "MODEL_FLASH_TEMPERATURE": "0.1",
    "MODEL_FLASH_REPETITION_PENALTY": "1.1",
    "MODEL_FLASH_TOP_P": "0.9",
    # ── Segmentation ──
    "SEGMENTATION_MODE": "progressive",
    "SEGMENTATION_REINERT": "false",
    "NLP_CONCURRENCY": "1",
    # ── CGT ──
    "DEFAULT_POPULATION_ASSUMPTION": (
        "hábitos hipotéticos de comportamiento que procesan "
        "preocupaciones similares o más amplias en la vida diaria "
        "del participante"
    ),
    "DEFAULT_OBJECT_OF_STUDY": "concern",
    # ── System ──
    "ENVIRONMENT": "dev",
    "ORCHESTRATION_MODE": "celery",
    "USE_GPU": "false",
    # ── Advanced ──
    "CODING_STYLES": "gerundio,in_vivo",
    "GLASER_CLASSIFIER_PROMPT": "",
    "MODEL_FLASH_FREQUENCY_PENALTY": "1.15",
    "MODEL_PRO_FREQUENCY_PENALTY": "0.0",
    "MODEL_PRO_REPETITION_PENALTY": "1.0",
    "MODEL_PRO_TOP_P": "1.0",
    "SPACY_EXCLUDE": "auto",
    "NLP_PROFILE": "low",
    "AGENTIC_MODE": "false",
    "AGENTIC_ORCHESTRATOR": "false",
    "RUNTIME_CONFIG_PATH": "/app/config/runtime.json",
}
