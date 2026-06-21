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

# ── System prompt (instructions, NO raw text) ──
CLASSIFIER_SYSTEM_PROMPT = """[ROL]
Eres un clasificador de datos cualitativos. Tu tarea es envolver pasajes de texto en tags XML segun su tipo de dato.

[REGLAS ABSOLUTAS]
1. SOLO puedes usar estos 4 tags: <baseline_data>, <interviewer_context>, <processual_data>, <contextual_data>
2. NO uses ningun otro tag. Si un pasaje no encaja en ninguna categoria, usa <baseline_data>.
3. TODO el texto del input DEBE estar dentro de algun tag. No puede haber texto suelto fuera de tags.
4. Cada bloque de texto dentro de un tag debe ser un pasaje continuo del texto original.
5. NO modifiques, resumas, ni reordenes el texto. Preservalo exactamente como esta.
6. NO uses tags anidados. Los tags no deben solaparse.
7. NO uses markdown code fences. Devuelve SOLO el XML.

[TIPOS DE DATO]
- <baseline_data>: datos centrales del fenomeno. Lo que la persona dice, piensa, siente o hace respecto al tema principal. La mayoria del texto debe ir aqui.
- <interviewer_context>: preguntas o intervenciones del entrevistador. Si el texto no es una entrevista, no uses este tag.
- <processual_data>: descripciones de secuencias temporales, pasos, etapas, cambios en el tiempo, narrativas de eventos.
- <contextual_data>: descripciones del entorno fisico, social o institucional. Background que no es parte del fenomeno central pero lo contextualiza."""


# ── Validator system prompt ──
VALIDATOR_SYSTEM_PROMPT = """[ROL]
Eres un validador de estructura XML. Tu UNICA tarea es verificar que un texto clasificado cumpla con reglas estructurales exactas.

[REGLAS A VERIFICAR]
1. Todo el texto debe estar dentro de EXACTAMENTE un tag XML (no puede haber texto suelto fuera de tags).
2. Solo se permiten estos tags: baseline_data, interviewer_context, processual_data, contextual_data.
3. Los tags no deben solaparse ni anidarse.
4. Cada tag de apertura debe tener su cierre correspondiente (balanceados).
5. No deben existir tags inventados o desconocidos.

[FORMATO DE RESPUESTA]
Responde EXCLUSIVAMENTE con este JSON:
{
  "valid": true,
  "issues": [],
  "suggested_fixes": ""
}

Si hay problemas, suggested_fixes debe ser una instruccion concreta y especifica sobre QUE tags estan mal, DONDE, y COMO arreglarlos. Menciona nombres exactos de tags problematicos."""


# ═══════════════════════════════════════════════════════════════════════
# Step 1: XML Tag Classification (PRO tier)
# ═══════════════════════════════════════════════════════════════════════


def _step1_classify_xml(
    raw_text: str, llm_client: Any, feedback: str | None = None
) -> str:
    """Classify full document text by wrapping passages in XML tags.

    Sends system instructions as 'system' role, raw text + feedback as 'user'.
    Uses PRO tier.
    """
    import os as _os

    # System prompt optionally overridable via env var
    system_prompt = _os.getenv("GLASER_CLASSIFIER_SYSTEM", CLASSIFIER_SYSTEM_PROMPT)

    user_content = f"<texto>\n{raw_text}\n</texto>"
    if feedback:
        user_content = (
            f"[FEEDBACK DEL VALIDADOR — Corrige estos problemas]\n{feedback}\n\n"
            + user_content
        )

    try:
        response = llm_client.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            model=None,  # default PRO
            max_tokens=8192,
            temperature=0.3,
        )
        result = (response.get("content") or "").strip()
        # Strip markdown code fences if model wrapped XML in them
        if result.startswith("```"):
            result = re.sub(r"^```(?:xml)?\s*\n?", "", result)
            result = re.sub(r"\n?```\s*$", "", result)
        # If result is empty, fall through to fallback
        if not result:
            raise ValueError("Empty response from LLM")
        return result
    except Exception as e:
        logger.error(
            "Step 1 (classify XML) failed: %s — falling back to all-baseline", e
        )
        escaped = (
            raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        return f"<baseline_data>{escaped}</baseline_data>"


# ═══════════════════════════════════════════════════════════════════════
# Step 2: Structure Validation (FLASH + algorithmic fallback)
# ═══════════════════════════════════════════════════════════════════════


def _step2_validate_xml(xml_text: str, llm_client: Any) -> dict:
    """Validate XML structure. Uses FLASH tier for speed, falls back to algorithmic."""
    # Run algorithmic first — catches 80% of issues without LLM cost
    algo_result = _algorithmic_validate_xml(xml_text)
    if algo_result["valid"]:
        return algo_result

    # Algorithmic found issues — use FLASH to provide better suggestions
    try:
        issues_text = "\n".join(f"- {i}" for i in algo_result["issues"])
        response = llm_client.chat(
            messages=[
                {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"El validador algoritmico encontro estos problemas:\n{issues_text}\n\nTexto clasificado (primeros 6000 chars):\n{xml_text[:6000]}\n\nGenera el JSON con suggested_fixes concretos para que el clasificador corrija estos problemas.",
                },
            ],
            model=llm_client.FLASH if hasattr(llm_client, "FLASH") else None,
            max_tokens=1000,
            temperature=0.1,
        )
        content = response.get("content") or ""
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            llm_result = json.loads(json_match.group(0))
            # Merge: use algorithmic result but with LLM suggested_fixes
            algo_result["suggested_fixes"] = llm_result.get(
                "suggested_fixes",
                "Fix the structural issues listed above. Check tag names and balance.",
            )
            return algo_result
    except Exception as e:
        logger.warning(
            "Step 2 FLASH validation failed: %s — using algorithmic result", e
        )

    return algo_result


# ═══════════════════════════════════════════════════════════════════════
# Step 3: Baseline Selection
# ═══════════════════════════════════════════════════════════════════════


def _step3_extract_baseline(xml_text: str) -> list[str]:
    """Extract all baseline_data content from classified XML."""
    matches = re.findall(r"<baseline_data>(.*?)</baseline_data>", xml_text, re.DOTALL)
    return [m.strip() for m in matches if m.strip()]


# ═══════════════════════════════════════════════════════════════════════
# Algorithmic XML validation (no LLM)
# ═══════════════════════════════════════════════════════════════════════


def _algorithmic_validate_xml(xml_text: str) -> dict:
    """Regex-based XML structure validation. Catches 80% of issues instantly."""
    issues = []

    # 1. Naked text outside tags
    # Strip all valid tags and their content — whatever remains is naked text
    naked = xml_text
    for tag in VALID_TAGS:
        naked = re.sub(f"<{tag}>.*?</{tag}>", "", naked, flags=re.DOTALL)
    naked = naked.strip()
    if naked:
        # Sample the first 100 chars of naked text
        sample = naked[:100] + ("..." if len(naked) > 100 else "")
        issues.append(f'Naked text outside tags: "{sample}"')

    # 2. Tag balance
    for tag in VALID_TAGS:
        opens = len(re.findall(f"<{tag}>", xml_text))
        closes = len(re.findall(f"</{tag}>", xml_text))
        if opens != closes:
            issues.append(f"Unbalanced <{tag}>: {opens} opens, {closes} closes")

    # 3. Unknown/invented tags
    all_tags = set(re.findall(r"</?(\w+)>", xml_text))
    unknown = all_tags - VALID_TAGS
    if unknown:
        issues.append(f"Unknown tags: {', '.join(sorted(unknown))}")

    # 4. Overlapping tags (forbidden: no nesting allowed)
    # Detect pattern: <tagA>...<tagB>...</tagA>...</tagB>
    tag_pattern = "|".join(VALID_TAGS)
    if re.search(
        f"<({tag_pattern})>.*<({tag_pattern})>.*</\\1>.*</\\2>", xml_text, re.DOTALL
    ):
        issues.append(
            "Overlapping or nested tags detected — tags must be sequential, not nested"
        )

    suggested = ""
    if issues:
        unknown_str = ", ".join(sorted(unknown)) if unknown else ""
        suggested = (
            f"ARREGLA ESTOS PROBLEMAS ESTRUCTURALES: {'. '.join(issues)}. "
            + (
                f"Tags NO PERMITIDOS detectados: {unknown_str}. SOLO usa: {', '.join(sorted(VALID_TAGS))}. "
                if unknown
                else ""
            )
            + "Asegurate de que TODO el texto este dentro de tags y que cada tag este bien cerrado."
        )

    return {"valid": len(issues) == 0, "issues": issues, "suggested_fixes": suggested}


# ═══════════════════════════════════════════════════════════════════════
# Backward compatibility: map XML tags to individual DB segments
# ═══════════════════════════════════════════════════════════════════════


def _map_xml_tags_to_segments(session, documento_id: str, xml_text: str) -> int:
    """Map classified XML back to DB segments using positional/text matching.

    Since the classifier may slightly reorder text, we do fuzzy matching:
    for each segment, find the longest common substring in the XML text
    and determine which tag it falls within.
    """
    rows = session.execute(
        text(
            "SELECT id, texto, posicion FROM segmentos "
            "WHERE documento_id = :did ORDER BY posicion"
        ),
        {"did": documento_id},
    ).fetchall()

    if not rows:
        return 0

    # Build tag boundaries: list of (start, end, tag_name)
    boundaries = []
    for tag in VALID_TAGS:
        for m in re.finditer(f"<{tag}>(.*?)</{tag}>", xml_text, re.DOTALL):
            boundaries.append((m.start(), m.end(), tag))
    boundaries.sort()

    classified = 0
    for row in rows:
        seg_id = str(row[0])
        seg_text = (row[1] or "").strip()
        if not seg_text:
            continue

        # Find best matching tag: search for the segment text within each tag block
        assigned_tag = "baseline_data"  # default fallback

        for start, end, tag in boundaries:
            block = xml_text[start:end]
            # Try exact substring match
            if seg_text in block:
                assigned_tag = tag
                break
            # Try first 50 chars of segment (fuzzy match)
            head = seg_text[:50]
            if head in block:
                assigned_tag = tag
                break

        session.execute(
            text("UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"),
            {"tipo": assigned_tag, "sid": seg_id},
        )
        classified += 1

    return classified


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

        # Step 2: Validate (algorithmic first, FLASH only if needed)
        validation_result = _step2_validate_xml(xml_text, llm_client)
        logger.info(
            "Glaser round %d/%d: valid=%s, issues=%d",
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
        "Glaser complete: %d baseline tags extracted (rounds=%d, valid=%s)",
        len(baseline_tags),
        rounds,
        validation_result.get("valid", False) if validation_result else False,
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
