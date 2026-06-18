"""F6b — Memo Theoretical Tagger (FLASH).

Classifies memos against the 12 canonical theoretical coding families
to assist sorting in the Theoretical Playground.
"""

from __future__ import annotations

import json
import sys

sys.path.insert(0, "/app")
import logging

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def tag_memo_theoretically(memo_id: str, proyecto_id: str) -> dict:
    """Classify a memo against 12 theoretical coding families (FLASH)."""
    session = SessionLocal()
    try:
        # Get memo content
        memo = session.execute(
            text("SELECT contenido FROM memos WHERE id = :mid"),
            {"mid": memo_id},
        ).fetchone()
        if not memo or not memo[0]:
            return {"error": "memo_not_found", "memo_id": memo_id}

        memo_content = memo[0][:3000]  # truncate for FLASH

        # Get object_of_study
        oos = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos[0] if oos and oos[0] else "concern"

        # Call FLASH agent
        result = llm.run_agent(
            "f6b_memo_theoretical_tagger",
            variables={
                "memo_content": memo_content,
                "object_of_study": object_of_study,
            },
        )

        # Store result in memo metadata
        session.execute(
            text(
                "UPDATE memos SET metadata = COALESCE(metadata, '{}'::jsonb) || :tag ::jsonb WHERE id = :mid"
            ),
            {
                "mid": memo_id,
                "tag": json.dumps({"theoretical_families": result}, ensure_ascii=False),
            },
        )
        session.commit()

        return result
    except Exception:
        logger.exception("tag_memo_theoretically failed for %s", memo_id)
        return {"error": "exception", "memo_id": memo_id}
    finally:
        session.close()
