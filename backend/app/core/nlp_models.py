"""
NLP Model Manager — single source of truth for spaCy and Stanza model selection.

Priority: env var > runtime.json > language-derived default.

Language is driven by NLP_LANGUAGE config (default "es").
Individual model overrides: SPACY_MODEL, SPACY_EXCLUDE.
"""

import logging

from app.core.runtime_config import get_config_value

logger = logging.getLogger(__name__)

# ── Language ────────────────────────────────────────────────────────────


def get_nlp_language() -> str:
    """Current NLP language code (e.g. 'es', 'en')."""
    return get_config_value("NLP_LANGUAGE", default="es")


# ── spaCy model-name resolution ─────────────────────────────────────────

SPACY_MODELS: dict[str, str] = {
    "es": "es_core_news_lg",
    "en": "en_core_web_lg",
}


def get_current_spacy_model_name() -> str:
    """
    Resolve the spaCy model name for the current language.

    Priority: SPACY_MODEL env/runtime override > language map > default.
    """
    override = get_config_value("SPACY_MODEL", default=None)
    if override:
        return override
    lang = get_nlp_language()
    return SPACY_MODELS.get(lang, "es_core_news_lg")


def get_spacy_exclude() -> list[str]:
    """Resolve SPACY_EXCLUDE to a list (empty list = load everything)."""
    raw = get_config_value("SPACY_EXCLUDE", default="auto")
    if raw == "auto" or not raw.strip():
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


# ── Lazy-loaded spaCy instance (cached) ─────────────────────────────────

_nlp: "spacy.Language | None" = None
_nlp_loaded_name: str | None = None


def get_current_spacy() -> "spacy.Language":
    """
    Lazy-load and return the spaCy model for the current language.

    The instance is cached globally.  For callers that need custom exclude
    lists or per-document fresh instances, use get_current_spacy_model_name()
    and load manually.
    """
    global _nlp, _nlp_loaded_name

    model_name = get_current_spacy_model_name()

    if _nlp is None or _nlp_loaded_name != model_name:
        import spacy

        exclude = get_spacy_exclude()
        load_kwargs = {}
        if exclude:
            load_kwargs["exclude"] = exclude

        logger.info(
            "Loading spaCy model: %s (exclude=%s)", model_name, exclude or "none"
        )
        _nlp = spacy.load(model_name, **load_kwargs)
        _nlp_loaded_name = model_name

    return _nlp


# ── Stanza ──────────────────────────────────────────────────────────────


def get_current_stanza_lang() -> str:
    """Stanza language code for the current NLP language (same as spaCy lang)."""
    return get_nlp_language()


# ── Model readiness & warmup ───────────────────────────────────────────


def check_models_ready(language: str) -> dict:
    """
    Return which NLP models are downloaded for the given language.

    Returns a dict with keys:
        language, spacy_ready, stanza_ready,
        models_downloaded, models_pending
    """
    spacy_model = SPACY_MODELS.get(language, "es_core_news_lg")

    # ── spaCy ──────────────────────────────────────────────────────
    spacy_ready = False
    try:
        import spacy

        spacy_ready = spacy.util.is_package(spacy_model)
    except Exception:
        pass

    # ── Stanza ─────────────────────────────────────────────────────
    stanza_ready = False
    try:
        import os

        import stanza

        stanza_resources_dir = os.path.join(
            os.path.expanduser("~"), "stanza_resources", language
        )
        stanza_ready = os.path.isdir(stanza_resources_dir)
    except Exception:
        pass

    models_downloaded: list[str] = []
    models_pending: list[str] = []

    if spacy_ready:
        models_downloaded.append(spacy_model)
    else:
        models_pending.append(spacy_model)

    if stanza_ready:
        models_downloaded.append(f"stanza_{language}")
    else:
        models_pending.append(f"stanza_{language}")

    return {
        "language": language,
        "spacy_ready": spacy_ready,
        "stanza_ready": stanza_ready,
        "models_downloaded": models_downloaded,
        "models_pending": models_pending,
    }


def warmup_language(language: str, progress_callback=None) -> None:
    """
    Download (if needed) and warm up NLP models for a language.

    Args:
        language: Language code (e.g. 'es', 'en').
        progress_callback: Optional callable(progress: float, message: str)
            called as each model is processed.
    """
    import os

    spacy_model = SPACY_MODELS.get(language, "es_core_news_lg")

    total_steps = 2  # spaCy + Stanza
    current_step = 0

    def _update(message: str, step_delta: int = 0) -> None:
        nonlocal current_step
        if step_delta:
            current_step += step_delta
        progress = current_step / total_steps if total_steps > 0 else 0.0
        if progress_callback:
            progress_callback(progress, message)

    # ── spaCy ──────────────────────────────────────────────────────
    import spacy

    if not spacy.util.is_package(spacy_model):
        _update(f"Downloading spaCy model: {spacy_model}...")
        spacy.cli.download(spacy_model)
        _update(f"spaCy model {spacy_model} installed", step_delta=1)
    else:
        _update(f"spaCy model {spacy_model} already present", step_delta=1)

    # ── Stanza ─────────────────────────────────────────────────────
    try:
        import stanza

        stanza_resources_dir = os.path.join(
            os.path.expanduser("~"), "stanza_resources", language
        )
        if not os.path.isdir(stanza_resources_dir):
            _update(f"Downloading Stanza model for {language}...")
            stanza.download(language)
            _update(f"Stanza model for {language} installed", step_delta=1)
        else:
            _update(f"Stanza model for {language} already present", step_delta=1)
    except ImportError:
        _update("Stanza not installed — skipping", step_delta=1)
    except Exception:
        _update("Stanza download failed", step_delta=1)

    # Optionally trigger a load to warm the models in memory
    try:
        get_current_spacy()
        _update("spaCy model loaded into memory")
    except Exception:
        _update("spaCy warm-up skipped")
