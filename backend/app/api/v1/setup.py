"""
Setup API — NLP model download and initialization endpoints.

GET  /api/v1/setup/status      → current environment/model state
POST /api/v1/setup/initialize  → trigger model download (background)
GET  /api/v1/setup/progress    → download progress (polling)
"""

import logging
import threading

from app.core.nlp_models import (
    check_models_ready,
    get_nlp_language,
    warmup_language,
)
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["setup"])

# ── Module-level progress tracker ──────────────────────────────────────

_download_lock = threading.Lock()
_download_progress: dict = {
    "status": "idle",  # idle | downloading | done | error
    "progress": 0.0,
    "message": "",
    "language": "",
}


def _progress_callback(progress: float, message: str) -> None:
    """Update the module-level progress dict."""
    with _download_lock:
        _download_progress["status"] = "downloading"
        _download_progress["progress"] = round(progress, 3)
        _download_progress["message"] = message


# ── Endpoints ──────────────────────────────────────────────────────────


@router.get("/setup/status")
async def get_setup_status():
    """
    Return the current environment state: language, which models
    are downloaded, and overall readiness.
    """
    language = get_nlp_language()
    ready = check_models_ready(language)

    all_ready = ready["spacy_ready"] and ready["stanza_ready"]
    progress = (
        1.0
        if all_ready
        else (0.5 if ready["spacy_ready"] or ready["stanza_ready"] else 0.0)
    )

    message = (
        "All models ready"
        if all_ready
        else ("Some models pending download" if ready["models_pending"] else "Unknown")
    )

    return {
        "language": ready["language"],
        "spacy_ready": ready["spacy_ready"],
        "stanza_ready": ready["stanza_ready"],
        "models_downloaded": ready["models_downloaded"],
        "models_pending": ready["models_pending"],
        "progress": progress,
        "message": message,
    }


@router.post("/setup/initialize")
async def initialize_setup(body: dict):
    """
    Trigger model download for a language in a background thread.

    Body: {"language": "es"}
    """
    language = body.get("language", get_nlp_language())

    with _download_lock:
        if _download_progress["status"] == "downloading":
            return {
                "status": "already_running",
                "language": _download_progress["language"],
                "message": _download_progress["message"],
            }
        _download_progress["status"] = "downloading"
        _download_progress["progress"] = 0.0
        _download_progress["message"] = "Starting download..."
        _download_progress["language"] = language

    def _run_warmup() -> None:
        try:
            warmup_language(language, progress_callback=_progress_callback)
            with _download_lock:
                _download_progress["status"] = "done"
                _download_progress["progress"] = 1.0
                _download_progress["message"] = f"All models ready for {language}"
        except Exception as exc:
            logger.exception("Model warmup failed for language=%s", language)
            with _download_lock:
                _download_progress["status"] = "error"
                _download_progress["message"] = str(exc)

    thread = threading.Thread(target=_run_warmup, daemon=True)
    thread.start()

    return {"status": "started", "language": language}


@router.get("/setup/progress")
async def get_setup_progress():
    """
    Return the current download progress (polling endpoint).

    Returns the module-level _download_progress dict.
    """
    with _download_lock:
        return dict(_download_progress)
