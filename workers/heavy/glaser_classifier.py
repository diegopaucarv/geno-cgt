"""
Glaser Data Classifier — 3-Step with Validator Loop.

Step 1 (PRO): Classify full document text by wrapping passages in XML tags.
Step 2 (FLASH): Validate XML structure, return feedback if invalid.
Step 3: Extract baseline_data segments for downstream analysis.

Validator loop: classify → validate → feedback → re-classify → ... (max 3 rounds).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Valid Glaser tag types ──
VALID_TAGS = {
    "baseline_data",
    "interviewer_context",
    "processual_data",
    "contextual_data",
}

# ── Default classifier prompt (overridable via env var) ──
DEFAULT_CLASSIFIER_PROMPT = """## System

[ROL]
Eres un clasificador de datos cualitativos segun la metodologia Glaser.

[OBJETIVO]
1. Clasifica cada segmento del texto en EXACTAMENTE uno de estos tipos:
   - baseline_data: datos centrales del fenomeno estudiado
   - interviewer_context: preguntas o intervenciones del entrevistador
   - processual_data: descripciones de procesos, secuencias, cambios
   - contextual_data: informacion de contexto, setting, background
2. Envuelve CADA segmento en su tag XML correspondiente.
3. NO dejes texto fuera de tags.

[RESTRICCIONES]
- Usa SOLO los 4 tags permitidos.
- Cada bloque de texto debe estar envuelto en EXACTAMENTE un tag.
- Los tags NO deben solaparse.
- Preserva el texto original sin modificarlo.
- Responde directamente. NO uses herramientas externas.

## Task

<texto>
{raw_text}
</texto>

Return the full text with XML tags wrapping each classified segment."""


# ═══════════════════════════════════════════════════════════════════════
# Step 1: XML Tag Classification (PRO tier)
# ═══════════════════════════════════════════════════════════════════════


def _step1_classify_xml(
    raw_text: str, llm_client: Any, feedback: str | None = None
) -> str:
    """Classify full document text by wrapping passages in XML tags.

    Uses PRO tier. Injects validator feedback if this is a retry round.
    """
    import os as _os

    prompt_template = _os.getenv("GLASER_CLASSIFIER_PROMPT", DEFAULT_CLASSIFIER_PROMPT)

    user_content = prompt_template.replace("{raw_text}", raw_text)
    if feedback:
        user_content += f"\n\n[FEEDBACK DEL VALIDADOR]\n{feedback}\n\nCorrige los tags XML segun el feedback anterior."

    # Use LLM client's chat method directly
    try:
        response = llm_client.chat(
            messages=[
                {"role": "user", "content": user_content},
            ],
            model=None,  # default PRO
            max_tokens=8192,
            temperature=0.3,
        )
        return (response.get("content") or "").strip()
    except Exception as e:
        logger.error("Step 1 (classify XML) failed: %s", e)
        # Fallback: wrap everything as baseline_data
        escaped = (
            raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f"<baseline_data>{escaped}</baseline_data>"


# ═══════════════════════════════════════════════════════════════════════
# Step 2: Structure Validation (FLASH + algorithmic fallback)
# ═══════════════════════════════════════════════════════════════════════


def _step2_validate_xml(xml_text: str, llm_client: Any) -> dict:
    """Validate XML structure. Uses LLM, falls back to algorithmic."""
    # Try LLM validation first
    try:
        response = llm_client.chat(
            messages=[
                {
                    "role": "user",
                    "content": f"""Valida la estructura XML del siguiente texto clasificado.

Reglas:
- Todo el texto debe estar dentro de EXACTAMENTE un tag XML
- Solo se permiten los tags: baseline_data, interviewer_context, processual_data, contextual_data
- Los tags no deben solaparse ni anidarse
- Cada tag debe estar correctamente cerrado

Texto a validar:
{xml_text[:8000]}

Responde SOLO con un JSON:
{{
  "valid": true/false,
  "issues": ["issue 1", "issue 2"],
  "suggested_fixes": "instrucciones especificas para el clasificador"
}}""",
                }
            ],
            model=None,  # default PRO
            max_tokens=1500,
            temperature=0.1,
        )
        content = response.get("content") or ""
        # Parse JSON from response
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.warning("Step 2 (validate XML) LLM call failed: %s", e)

    # Fallback to algorithmic validation
    return _algorithmic_validate_xml(xml_text)


# ═══════════════════════════════════════════════════════════════════════
# Step 3: Baseline Selection
# ═══════════════════════════════════════════════════════════════════════


def _step3_extract_baseline(xml_text: str) -> list[str]:
    """Extract all baseline_data content from classified XML."""
    matches = re.findall(r"<baseline_data>(.*?)</baseline_data>", xml_text, re.DOTALL)
    return [m.strip() for m in matches if m.strip()]


def _map_xml_tags_to_segments(session, documento_id: str, xml_text: str) -> int:
    """Map XML-tagged regions back to DB segments for backward compatibility."""
    # Get all segments ordered by position
    rows = session.execute(
        text(
            "SELECT id, texto, posicion FROM segmentos "
            "WHERE documento_id = :did ORDER BY posicion"
        ),
        {"did": documento_id},
    ).fetchall()

    if not rows:
        return 0

    classified = 0
    for row in rows:
        seg_id = str(row[0])
        seg_text = row[1] or ""

        # Try to find this segment's text in the classified XML
        escaped = (
            seg_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        tag_type = "baseline_data"  # default

        for tag in VALID_TAGS:
            if f"<{tag}>" in xml_text and escaped in xml_text:
                # Check if this segment falls within this tag's boundaries
                tag_start = xml_text.find(f"<{tag}>")
                tag_end = xml_text.find(f"</{tag}>", tag_start)
                seg_start = xml_text.find(escaped)
                if tag_start < seg_start < tag_end:
                    tag_type = tag
                    break

        session.execute(
            text("UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"),
            {"tipo": tag_type, "sid": seg_id},
        )
        classified += 1

    return classified


# ═══════════════════════════════════════════════════════════════════════
# Algorithmic XML validation (fallback, no LLM)
# ═══════════════════════════════════════════════════════════════════════


def _algorithmic_validate_xml(xml_text: str) -> dict:
    """Regex-based XML structure validation. No LLM."""
    issues = []

    # Check for text outside tags
    stripped = re.sub(r"<[^>]+>", "", xml_text)
    # Remove whitespace-only content
    if not stripped.strip():
        issues.append("No text content found")

    # Check tag balance
    for tag in VALID_TAGS:
        opens = len(re.findall(f"<{tag}>", xml_text))
        closes = len(re.findall(f"</{tag}>", xml_text))
        if opens != closes:
            issues.append(f"Unbalanced {tag}: {opens} opens, {closes} closes")

    # Check for unknown tags
    all_tags = set(re.findall(r"</?(\w+)>", xml_text))
    unknown = all_tags - VALID_TAGS
    if unknown:
        issues.append(f"Unknown tags: {', '.join(unknown)}")

    # Check for overlapping tags (simplistic: no nested allowed)
    if re.search(r"<\w+>.*<\w+>.*</\w+>.*</\w+>", xml_text):
        issues.append("Possible overlapping tags detected")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "suggested_fixes": (
            "Fix the issues above and ensure all text is properly wrapped in exactly one tag."
            if issues
            else ""
        ),
    }


# ═══════════════════════════════════════════════════════════════════════
# Main orchestrator: 3-step classifier with validator loop
# ═══════════════════════════════════════════════════════════════════════


def classify_document_with_validation(
    documento_id: str,
    proyecto_id: str,
    session,
    llm_client: Any,
    max_validation_rounds: int = 3,
) -> dict:
    """Run the 3-step Glaser classifier with validator loop.

    Returns:
        dict with status, validation_rounds, baseline_tags_count, segments_classified
    """
    # ── Get raw text ──
    row = session.execute(
        text("SELECT metadatos FROM documentos WHERE id = :did"),
        {"did": documento_id},
    ).fetchone()

    if not row:
        return {"status": "error", "reason": "Document not found"}

    meta = row[0] or {}
    if isinstance(meta, str):
        meta = json.loads(meta)

    raw_text = meta.get("texto_preprocesado") or meta.get("texto_extraido") or ""
    if not raw_text:
        return {"status": "error", "reason": "No text available for classification"}

    # ── Validator loop ──
    xml_text = ""
    feedback = None
    validation_result = None
    rounds = 0

    for round_num in range(1, max_validation_rounds + 1):
        rounds = round_num

        # Step 1: Classify
        logger.info(
            "Glaser round %d/%d: classifying doc=%s, feedback=%s",
            round_num,
            max_validation_rounds,
            documento_id[:8],
            "yes" if feedback else "no",
        )
        xml_text = _step1_classify_xml(raw_text, llm_client, feedback)

        # Step 2: Validate
        validation_result = _step2_validate_xml(xml_text, llm_client)
        logger.info(
            "Glaser round %d/%d: validation valid=%s, issues=%d",
            round_num,
            max_validation_rounds,
            validation_result.get("valid"),
            len(validation_result.get("issues", [])),
        )

        if validation_result.get("valid"):
            break

        feedback = validation_result.get("suggested_fixes") or ""

    # ── Step 3: Baseline selection ──
    baseline_tags = _step3_extract_baseline(xml_text or "")
    logger.info(
        "Glaser complete: %d baseline tags extracted (rounds=%d)",
        len(baseline_tags),
        rounds,
    )

    # ── Persist results ──
    meta["texto_clasificado"] = xml_text or ""
    meta["baseline_tags"] = baseline_tags
    session.execute(
        text("UPDATE documentos SET metadatos = :meta WHERE id = :did"),
        {"meta": json.dumps(meta), "did": documento_id},
    )

    # ── Map XML tags back to segments ──
    segments_classified = _map_xml_tags_to_segments(
        session, documento_id, xml_text or ""
    )

    session.commit()

    return {
        "status": "completed",
        "validation_rounds": rounds,
        "baseline_tags_count": len(baseline_tags),
        "segments_classified": segments_classified,
        "valid": validation_result.get("valid", False) if validation_result else False,
    }
