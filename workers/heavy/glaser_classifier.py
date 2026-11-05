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

from app.core.runtime_config import get_config_value
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ── Valid Glaser tag types ──
VALID_TAGS = {
    "baseline_data",
    "interviewer_context",
    "processual_data",
    "contextual_data",
}


class ClassificationUnavailable(RuntimeError):
    """El LLM no devolvió una clasificación utilizable.

    Antes, `_step1_classify_xml` envolvía todo el documento en
    `<baseline_data>` y seguía como si nada: el documento quedaba con sus N
    segmentos en `baseline_data`, `status="completed"` y `valid=True`. Nada
    distinguía eso de una clasificación real, así que la degradación pasaba
    inadvertida hasta que los incidentes extraídos no tenían sentido.
    """


def _baseline_fallback_xml(raw_text: str) -> str:
    """Fallback conservador: el documento entero como baseline.

    Solo se usa para dejar los segmentos en un valor conocido cuando la
    clasificación falla; el llamador debe marcar el resultado como degradado.
    """
    escaped = raw_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"<baseline_data>{escaped}</baseline_data>"


def _mentions_glaser_tag(xml_text: str) -> bool:
    """True cuando la respuesta contiene al menos un tag Glaser."""
    return any(f"<{tag}" in xml_text for tag in VALID_TAGS)


# ── System prompt (instructions, NO raw text) ──
CLASSIFIER_SYSTEM_PROMPT = """[ROL]
Eres un clasificador de datos cualitativos. Tu tarea es envolver pasajes de texto en tags XML segun su tipo de dato. DEBES usar al menos 2 tipos de tag diferentes.

[REGLAS ABSOLUTAS]
1. SOLO puedes usar estos 4 tags: <baseline_data>, <interviewer_context>, <processual_data>, <contextual_data>
2. NUNCA uses <baseline_data> como categoria por defecto. Si un pasaje no encaja claramente en baseline_data, usa <contextual_data>.
3. TODO el texto del input DEBE estar dentro de algun tag. No puede haber texto suelto fuera de tags.
4. Cada bloque de texto dentro de un tag debe ser un pasaje continuo del texto original.
5. NO modifiques, resumas, ni reordenes el texto. Preservalo exactamente como esta.
6. NO uses tags anidados. Los tags no deben solaparse.
7. NO uses markdown code fences. Devuelve SOLO el XML.
8. USA AL MENOS 2 TIPOS DE TAG DIFERENTES. Si todo el texto es de un solo tipo, estas clasificando mal.

[TIPOS DE DATO — definiciones ESTRICTAS]
- <baseline_data>: SOLO pasajes donde el hablante exprese EXPLICITAMENTE: lo que PIENSA (opiniones, creencias, juicios), lo que SIENTE (emociones, afectos, valoraciones), o lo que HACE (acciones, comportamientos, practicas) respecto al tema central. NO incluyas narraciones, descripciones de contexto, introducciones, ni secuencias temporales aqui.
- <interviewer_context>: SOLO preguntas o intervenciones del entrevistador. Identificalas por signos de interrogacion, frases como "cuenteme sobre...", "podria explicar...", o cambios de tema iniciados por otra persona. Si no hay entrevistador, no uses este tag.
- <processual_data>: SOLO descripciones de secuencias temporales explicitas: pasos ("primero... luego..."), etapas, cambios en el tiempo ("antes... ahora..."), narrativas de eventos con principio y fin, o verbos de transformacion ("empezo a...", "dejo de...", "se convirtio en...").
- <contextual_data>: descripciones del entorno fisico, social, institucional o historico. Background, setting, datos demograficos, fechas, lugares, roles. Tambien introducciones, transiciones, y pasajes que no expresan contenido sustantivo del fenomeno."""


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


def _resolve_project_prompt(session: Any, proyecto_id: str | None) -> tuple[str, str]:
    """Prompt Glaser propio del proyecto: (prompt, source).

    Devuelve ("", "") cuando no hay override (fila inexistente, NULL, cadena
    vacía o solo espacios) o cuando la lectura falla. Abre SIEMPRE su propia
    sesión (nunca la del llamador): un error de BD aquí no debe envenenar la
    transacción que luego hace `UPDATE documentos`. Es fail-safe a propósito,
    porque la columna no existe si la migración 017 aún no ha corrido.
    """
    if not proyecto_id:
        return "", ""

    db = None
    try:
        from database import SessionLocal

        db = SessionLocal()
        row = db.execute(
            text("SELECT glaser_classifier_prompt FROM proyectos WHERE id = :pid"),
            {"pid": str(proyecto_id)},
        ).fetchone()
    except Exception as exc:  # noqa: BLE001 — best-effort: nunca romper la tarea
        logger.warning(
            "Glaser: no se pudo leer el prompt del proyecto %s (%s: %s); "
            "se usará el prompt global/integrado",
            (proyecto_id or "-")[:8],
            type(exc).__name__,
            exc,
        )
        if db is not None:
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
        return "", ""
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:  # noqa: BLE001
                pass

    if not row or row[0] is None:
        return "", ""

    prompt = str(row[0]).strip()
    if not prompt:
        return "", ""
    return prompt, "project"


def _resolve_system_prompt(
    session: Any | None = None, proyecto_id: str | None = None
) -> tuple[str, str]:
    """System instructions for step 1: (prompt, source).

    Priority:
        1. Override del proyecto (proyectos.glaser_classifier_prompt) → "project"
        2. env GLASER_CLASSIFIER_SYSTEM > runtime.json GLASER_CLASSIFIER_PROMPT
           (⚙ panel)                                                        → "global"
        3. built-in CLASSIFIER_SYSTEM_PROMPT                               → "builtin"

    An empty configured value means "fall to the next tier". Called without
    arguments it behaves as before (global/builtin tiers only).
    """
    proj_prompt, _ = _resolve_project_prompt(session, proyecto_id)
    if proj_prompt:
        return proj_prompt, "project"

    configured = str(
        get_config_value(
            "GLASER_CLASSIFIER_PROMPT",
            env_var="GLASER_CLASSIFIER_SYSTEM",
            default="",
        )
        or ""
    ).strip()
    if configured:
        return configured, "global"

    return CLASSIFIER_SYSTEM_PROMPT, "builtin"


def _prompt_mentions_all_tags(prompt: str) -> bool:
    """True si el prompt menciona (apertura o cierre) los 4 tags de Glaser."""
    return all(f"<{tag}>" in prompt or f"</{tag}>" in prompt for tag in VALID_TAGS)


def _step1_classify_xml(
    raw_text: str,
    llm_client: Any,
    feedback: str | None = None,
    *,
    session: Any | None = None,
    proyecto_id: str | None = None,
) -> str:
    """Classify full document text by wrapping passages in XML tags.

    Sends system instructions as 'system' role, raw text + feedback as 'user'.
    Uses PRO tier. The system instructions come from config (see below), so the
    Glaser prompt can be edited from the ⚙ panel or per project without a
    restart.
    """
    # Instructions come from config (see _resolve_system_prompt).
    system_prompt, prompt_source = _resolve_system_prompt(
        session=session, proyecto_id=proyecto_id
    )
    logger.info(
        "Glaser prompt: source=%s, project=%s, len=%d",
        prompt_source,
        (proyecto_id or "-")[:8],
        len(system_prompt),
    )
    if prompt_source == "project" and not _prompt_mentions_all_tags(system_prompt):
        # Se respeta el prompt del usuario; solo se avisa.
        logger.warning(
            "Glaser prompt del proyecto %s no menciona los 4 tags válidos %s",
            (proyecto_id or "-")[:8],
            sorted(VALID_TAGS),
        )

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
            # Sin override explícito: el presupuesto del tier PRO
            # (MODEL_PRO_MAX_TOKENS, 131072 por defecto) es el único que deja
            # sitio al razonamiento. DeepSeek V4 / Nemotron son modelos de
            # razonamiento: para un documento de ~30 segmentos emiten ~32 000
            # caracteres de `reasoning_content` antes del XML. Con un cap
            # pequeño (4096 u 8192) el razonamiento agota el budget, `content`
            # llega vacío y la clasificación degrada en silencio a
            # `<baseline_data>` para todo el documento.
            temperature=0.3,
            cache_key=str(proyecto_id) if proyecto_id else None,
        )
        result = (response.get("content") or "").strip()
        # Strip markdown code fences if model wrapped XML in them
        if result.startswith("```"):
            result = re.sub(r"^```(?:xml)?\s*\n?", "", result)
            result = re.sub(r"\n?```\s*$", "", result)
        # If result is empty, the reasoning budget was exhausted or the call
        # failed: let the caller mark the document as degraded.
        if not result:
            raise ClassificationUnavailable(
                "Empty response from LLM"
                f" (finish_reason={response.get('finish_reason')}"
                f", reasoning_chars={len(response.get('reasoning_content') or '')})"
            )
        if not _mentions_glaser_tag(result):
            raise ClassificationUnavailable(
                "LLM response contains no Glaser tag"
                f" (chars={len(result)}, head={result[:80]!r})"
            )
        return result
    except ClassificationUnavailable:
        raise
    except Exception as e:
        raise ClassificationUnavailable(f"{type(e).__name__}: {e}") from e


# ═══════════════════════════════════════════════════════════════════════
# Step 2: Structure Validation (FLASH + algorithmic fallback)
# ═══════════════════════════════════════════════════════════════════════


def _step2_validate_xml(
    xml_text: str, llm_client: Any, cache_key: str | None = None
) -> dict:
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
            model=get_config_value(
                "MODEL_FLASH",
                default="accounts/fireworks/models/nemotron-lightning-3p5-30b-a3b",
            ),
            max_tokens=1000,
            temperature=0.1,
            cache_key=cache_key,
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


def _has_nested_tags(xml_text: str) -> bool:
    """True when a valid tag opens while a previous one is still open.

    Nesting is forbidden (passages must be sequential), so a depth-first scan is
    enough: any opening tag seen at depth > 0 is a violation. The previous
    implementation used a single-regex lookahead that also matched perfectly
    sequential multi-tag output, forcing three validator rounds on every
    correctly classified document.
    """
    depth = 0
    for match in re.finditer(r"<(/?)(\w+)>", xml_text):
        if match.group(2) not in VALID_TAGS:
            continue
        if match.group(1):
            depth = max(0, depth - 1)
        elif depth > 0:
            return True
        else:
            depth = 1
    return False


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
    if _has_nested_tags(xml_text):
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
        dict with status, validation_rounds, baseline_tags_count,
        segments_classified. ``status`` is ``"degraded"`` (not ``"completed"``)
        when Step 1 never produced a usable classification; the conservative
        all-baseline mapping is still persisted so downstream state is defined,
        but callers must not treat that as success.
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
    unavailable: str | None = None

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
        try:
            xml_text = _step1_classify_xml(
                raw_text, llm_client, feedback, session=session, proyecto_id=proyecto_id
            )
        except ClassificationUnavailable as exc:
            # Reintentar con feedback no sirve: el modelo no está devolviendo
            # clasificación alguna. Se corta el loop y se marca degradado.
            unavailable = str(exc)
            logger.error(
                "Glaser round %d/%d: clasificación no disponible doc=%s: %s",
                round_num,
                max_validation_rounds,
                documento_id[:8],
                exc,
            )
            xml_text = _baseline_fallback_xml(raw_text)
            break

        # Step 2: Validate (algorithmic first, FLASH only if needed)
        validation_result = _step2_validate_xml(
            xml_text, llm_client, cache_key=str(proyecto_id) if proyecto_id else None
        )
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
        "status": "degraded" if unavailable else "completed",
        "validation_rounds": rounds,
        "baseline_tags_count": len(baseline_tags),
        "segments_classified": segments_classified,
        "valid": bool(
            unavailable is None and validation_result and validation_result.get("valid")
        ),
        "reason": unavailable,
    }
