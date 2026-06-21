"""
Glaser Markdown Tag Parser

Parses the output of fa_glaser_data_classifier, which returns full document text
with Markdown comment tags delimiting sections by Glaser data type:

    <!-- baseline_data -->...<!-- /baseline_data -->
    <!-- properline_data -->...<!-- /properline_data -->
    <!-- interpreted_data -->...<!-- /interpreted_data -->
    <!-- vague_data -->...<!-- /vague_data -->
    <!-- interviewer_context -->...<!-- /interviewer_context -->

Only baseline_data is extracted for segmentation. Other types are stored as metadata.
Includes a retry loop (max 3 attempts) for when the LLM fails to tag correctly.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ── Supported Glaser data types ──────────────────────────────────────

GLASER_TYPES = [
    "baseline_data",
    "properline_data",
    "interpreted_data",
    "vague_data",
    "interviewer_context",
]

# Regex to extract tagged sections. Uses DOTALL so newlines inside tags are captured.
TAG_PATTERN = re.compile(
    r"<!--\s*(baseline_data|properline_data|interpreted_data|vague_data|interviewer_context)\s*-->\s*"
    r"(.*?)"
    r"<!--\s*/\1\s*-->",
    re.DOTALL,
)


def parse_glaser_tags(
    tagged_text: str,
    max_retries: int = 3,
    retry_callback: Optional[callable] = None,
) -> dict:
    """Parse Glaser-tagged document text into typed sections.

    Args:
        tagged_text: Full document text with <!-- type --> tags inserted.
        max_retries: Maximum retry attempts if baseline_data is empty/missing.
        retry_callback: Optional async callback(tagged_text, error_msg) -> new_tagged_text
            called when a retry is needed. Must return the re-tagged text from the LLM.

    Returns:
        {
            "status": "ok" | "error",
            "sections": {
                "baseline_data": str,
                "properline_data": str,
                "interpreted_data": str,
                "vague_data": str,
                "interviewer_context": str,
            },
            "error": str | None,
            "retries": int,
            "total_chars": int,
            "tagged_chars": int,
        }
    """
    for attempt in range(max_retries):
        matches = TAG_PATTERN.findall(tagged_text)
        sections: dict[str, str] = {t: "" for t in GLASER_TYPES}

        for tag_type, content in matches:
            cleaned = content.strip()
            if cleaned:
                sections[tag_type] = (
                    sections[tag_type] + (" " if sections[tag_type] else "") + cleaned
                )

        total_tagged = sum(len(v) for v in sections.values())
        total_raw = len(tagged_text.strip())
        baseline = sections.get("baseline_data", "").strip()

        # ── Validation ──
        if len(baseline) >= 50:
            return {
                "status": "ok",
                "sections": sections,
                "error": None,
                "retries": attempt,
                "total_chars": total_raw,
                "tagged_chars": total_tagged,
            }

        # ── Retry conditions ──
        if attempt < max_retries - 1 and retry_callback:
            error_msg = (
                f"baseline_data is empty or too short ({len(baseline)} chars). "
                f"Found {len(matches)} tag blocks across types: "
                f"{[(t, len(c.strip())) for t, c in matches]}. "
                "Ensure ALL text is tagged and baseline_data contains at least 50 chars "
                "of content directly answering the research question."
            )
            logger.warning(
                "Glaser parse attempt %d/%d failed: %s",
                attempt + 1,
                max_retries,
                error_msg,
            )
            try:
                tagged_text = retry_callback(tagged_text, error_msg)
            except Exception as e:
                logger.error("Retry callback failed: %s", e)
                break
        elif attempt < max_retries - 1:
            logger.warning(
                "Glaser parse attempt %d/%d failed but no retry_callback provided.",
                attempt + 1,
                max_retries,
            )
        else:
            logger.error(
                "Glaser parse failed after %d attempts. baseline_data: %d chars, "
                "total tagged: %d/%d chars.",
                max_retries,
                len(baseline),
                total_tagged,
                total_raw,
            )

    # ── Final attempt: fallback — treat entire text as baseline_data ──
    logger.warning("All retries exhausted. Falling back: entire text → baseline_data.")
    return {
        "status": "error",
        "sections": {
            **{t: "" for t in GLASER_TYPES},
            "baseline_data": tagged_text.strip(),
        },
        "error": f"Failed to parse Glaser tags after {max_retries} attempts. "
        f"Using entire text as baseline_data.",
        "retries": max_retries,
        "total_chars": len(tagged_text.strip()),
        "tagged_chars": len(tagged_text.strip()),
    }


def extract_baseline_text(tagged_text: str) -> str:
    """Convenience: extract only baseline_data from tagged text (no retry)."""
    result = parse_glaser_tags(tagged_text, max_retries=1)
    return result["sections"].get("baseline_data", "")


def has_valid_tags(tagged_text: str) -> bool:
    """Quick check: does the text contain at least one valid Glaser tag pair?"""
    return bool(TAG_PATTERN.search(tagged_text))
