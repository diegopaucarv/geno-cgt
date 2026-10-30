"""
FUENTE ÚNICA de defaults de configuración del sistema.

Consumidores:
  - app.core.config         → EDITABLE_DEFAULTS como fallback de cada _cfg()
  - app.core.runtime_config → EDITABLE_DEFAULTS (fallbacks de get_config_value)
                              e INTERNAL_DEFAULTS (ruta del runtime.json)
  - app.api.v1.config_info  → expone al panel ⚙ el subconjunto de sus schemas

Prioridad efectiva: env var > runtime.json > EDITABLE_DEFAULTS.
"""

EDITABLE_DEFAULTS: dict[str, str] = {
    # ── LLM Models ──
    "MODEL_PRO": "deepseek-ai/DeepSeek-V4-Flash-1017",
    "MODEL_PRO_MAX_TOKENS": "8192",
    "MODEL_PRO_TEMPERATURE": "0.3",
    "MODEL_FLASH": "nvidia/NVIDIA-Nemotron-3.5-Super-VL",
    "MODEL_FLASH_MAX_TOKENS": "4096",
    "MODEL_FLASH_TEMPERATURE": "0.1",
    "MODEL_FLASH_REPETITION_PENALTY": "1.1",
    "MODEL_FLASH_TOP_P": "0.9",
    # ── Segmentation ──
    "SEGMENTATION_MODE": "progressive",
    "SEGMENTATION_REINERT": "false",
    "NLP_CONCURRENCY": "1",
    # ── NLP ──
    "NLP_LANGUAGE": "es",
    "SPACY_MODEL": "",  # vacío = resolver desde NLP_LANGUAGE
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
}

# ── Defaults de infraestructura (NO editables en runtime) ─────────────
# Se resuelven una sola vez al importar el módulo; cambiarlos exige reiniciar.
INTERNAL_DEFAULTS: dict[str, str] = {
    "RUNTIME_CONFIG_PATH": "/app/config/runtime.json",
}
