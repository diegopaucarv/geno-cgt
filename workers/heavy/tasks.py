"""
Agentes CGT — Fase A: procesamiento por documento (con prompt library).

A1. POPULATION_CONTEXT_BUILDER — memoria de largo plazo
A2. PROCESS_IDENTIFIER — memoria de corto plazo por documento
A3. SENSE_MAKER — hipótesis emergentes (desde doc 3)

Pipeline: A1 → A2 → (si doc_count ≥ 3) A3

Los prompts se cargan desde /app/prompts/. No están hardcodeados.
El `population_assumption` (supuesto poblacional) viene del proyecto.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from celery import Celery
from sqlalchemy import text

sys.path.insert(0, "/app")

from algorithmic_checks import (
    check_output_references,
    classify_segments_batch,
)
from database import SessionLocal
from llm_client import LLMClient

logger = logging.getLogger(__name__)


# ── Translation Pattern (T1): leer idioma del proyecto ──
def _set_language_from_project(session, proyecto_id: str) -> str:
    """Lee proyectos.language y configura el LLMClient. Retorna el idioma."""
    try:
        row = session.execute(
            text("SELECT language FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        lang = row[0] if row and row[0] else "es"
        LLMClient.set_user_language(lang)
        return lang
    except Exception:
        LLMClient.set_user_language("es")
        return "es"


def _get_coding_style_instruction(session, proyecto_id: str) -> str:
    """Read coding_style_instruction from project config, with fallback."""
    try:
        from app.core.coding_styles import get_default_style_instruction

        row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        if row and row[0] and isinstance(row[0], dict):
            instr = row[0].get("coding_style_instruction", "")
            if instr:
                return instr
        return get_default_style_instruction()
    except Exception:
        return "Nombra cada código con un GERUNDIO (-ando/-iendo)."


# ── Pipeline log streaming ──────────────────────


# ── Pipeline log streaming ──────────────────────


def _plog(project_id: str, message: str):
    """Push a log line to Redis. Works in Celery child processes."""
    try:
        import json as _j
        import os as _os
        import time as _t

        import redis as _r

        rr = _r.Redis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        rr.rpush(
            f"pipeline_logs:{project_id}", _j.dumps({"ts": _t.time(), "msg": message})
        )
        rr.expire(f"pipeline_logs:{project_id}", 3600)
    except Exception:
        pass


# Monkey-patch the logger to also push to Redis
import logging as _logging

_original_info = _logging.Logger.info
_original_debug = _logging.Logger.debug
_original_warning = _logging.Logger.warning
_original_error = _logging.Logger.error


class _RedisLogger:
    project_id = ""


def _make_patched(original, level):
    def patched(self, msg, *args, **kwargs):
        original(self, msg, *args, **kwargs)
        if _RedisLogger.project_id:
            try:
                formatted = msg % args if args else msg
                _plog(_RedisLogger.project_id, f"[{level}] {formatted}")
            except Exception:
                pass

    return patched


_logging.Logger.info = _make_patched(_original_info, "INFO")
_logging.Logger.debug = _make_patched(_original_debug, "DEBUG")
_logging.Logger.warning = _make_patched(_original_warning, "WARN")
_logging.Logger.error = _make_patched(_original_error, "ERROR")


def _pipeline_log_to(project_id: str):
    _RedisLogger.project_id = project_id
    _plog(project_id, f"Pipeline log activado para proyecto {project_id[:8]}...")


from kombu import Exchange, Queue

app = Celery("heavy_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
app.conf.update(
    task_queues=(
        Queue("heavy", Exchange("heavy", type="direct"), routing_key="heavy"),
        Queue("nlp", Exchange("nlp", type="direct"), routing_key="nlp"),
    ),
)
llm = LLMClient()


def _get_population_assumption(session, proyecto_id: str) -> str:
    """Obtiene el supuesto poblacional del proyecto, o el default."""
    row = session.execute(
        text("SELECT supuesto_poblacional FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if row and row[0]:
        return row[0]
    return "hábitos hipotéticos de comportamiento que procesan preocupaciones similares"


# ═══════════════════════════════════════════════════════════════════════
# A1: POPULATION_CONTEXT_BUILDER
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="a1_build_population_context")
def a1_build_population_context(documento_id: str, proyecto_id: str) -> dict:
    session = SessionLocal()
    try:
        pop_assumption = _get_population_assumption(session, proyecto_id)

        # Fetch operational question from Nemotron output
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = pa_data.get("research_question", {})
        operational_question = rq_data.get("operational_question", "")
        oos_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        existing = session.execute(
            text(
                "SELECT surprising_details, language_patterns, data_production_context, source_document_ids, version FROM population_contexts WHERE proyecto_id = :pid ORDER BY version DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        segments = session.execute(
            text(
                "SELECT texto FROM segmentos WHERE documento_id = :did ORDER BY posicion LIMIT 15"
            ),
            {"did": documento_id},
        ).fetchall()

        if not segments:
            return {"error": "documento sin segmentos", "documento_id": documento_id}

        existing_context = ""
        if existing:
            existing_context = f"DETALLES: {existing[0]}\nLENGUAJE: {existing[1]}\nPRODUCCIÓN: {existing[2]}"

        response = llm.run_agent(
            agent_id="fa_population_context",
            variables={
                "population_assumption": pop_assumption,
                "existing_context": existing_context or "(sin contexto previo)",
                "segments": "\n---\n".join(r[0] for r in segments)[:8000],
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
            },
            temperature=0.3,
        )

        if response.get("mock_note"):
            return {"error": "mock fallback", "note": response["mock_note"]}

        # Validate: don't save empty outputs, but don't block the pipeline
        sd = (response.get("surprising_details") or "").strip()
        lp = (response.get("language_patterns") or "").strip()
        dpc = (response.get("data_production_context") or "").strip()
        all_empty = not sd and not lp and not dpc
        if all_empty:
            logger.info(
                "A1: empty response for doc=%s — skipping population context update (non-fatal)",
                documento_id,
            )
            return {"status": "skipped_empty", "documento_id": documento_id}

        new_version = (existing[4] + 1) if existing else 1
        new_source_ids = list(existing[3]) if existing else []
        if documento_id not in new_source_ids:
            new_source_ids.append(documento_id)

        result = session.execute(
            text(
                "INSERT INTO population_contexts (id, proyecto_id, surprising_details, language_patterns, data_production_context, source_document_ids, version) VALUES (gen_random_uuid(), :pid, :sd, :lp, :dpc, :sids, :ver) RETURNING id"
            ),
            {
                "pid": proyecto_id,
                "sd": sd,
                "lp": lp,
                "dpc": dpc,
                "sids": json.dumps(new_source_ids),
                "ver": new_version,
            },
        )
        session.commit()
        new_id = str(result.fetchone()[0])

        return {
            "population_context_id": new_id,
            "version": new_version,
            "changed_dimensions": [
                d
                for d in [
                    "surprising_details",
                    "language_patterns",
                    "data_production_context",
                ]
                if response.get(d, "").strip()
                and "Sin cambios" not in response.get(d, "")
            ],
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# A2: PROCESS_IDENTIFIER
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="a2_identify_process")
def a2_identify_process(documento_id: str, proyecto_id: str) -> dict:
    session = SessionLocal()
    try:
        pop_assumption = _get_population_assumption(session, proyecto_id)

        # Fetch operational question from Nemotron output
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = pa_data.get("research_question", {})
        operational_question = rq_data.get("operational_question", "")
        processing_verb = (
            pa_data.get("processing_verb", "resolve")
            if isinstance(pa_data, dict)
            else "resolve"
        )
        oos_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        previous = session.execute(
            text(
                "SELECT process_description, documento_id FROM document_processes WHERE proyecto_id = :pid ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        segments = session.execute(
            text(
                "SELECT texto FROM segmentos WHERE documento_id = :did ORDER BY posicion LIMIT 8"
            ),
            {"did": documento_id},
        ).fetchall()
        segments_text = "\n\n".join(r[0] for r in segments)

        agent_id = "fa_process_identifier"
        prev_process = (
            previous[0] if previous else "(primer documento — sin comparación)"
        )
        is_first = not previous

        task_section = (
            "[TAREA]\n"
            "Identifica el proceso central que este participante intenta resolver\n"
            "continuamente. Nómbralo con un gerundio y explica en 2-3 oraciones\n"
            "qué acciones concretas en los segmentos revelan este proceso.\n"
            "No busques lo que el participante dice explícitamente que le preocupa.\n"
            "Busca el patrón de comportamiento que subyace a sus acciones.\n"
            "Para similarity_to_previous y difference_from_previous, responde 'N/A'."
            if is_first
            else "[TAREA]\n"
            "1. Identifica el proceso central de ESTE participante (gerundio + 2-3 oraciones).\n"
            "2. ¿En qué se PARECE al proceso del participante anterior?\n"
            "   ¿Es el mismo proceso con distinta manifestación?\n"
            "3. ¿En qué se DIFERENCIA ESENCIALMENTE?\n"
            "   No detalles superficiales sino diferencias en el patrón de comportamiento."
        )

        # F2.1: Leer clasificación Glaser ya persistida para este documento
        glaser_summary = session.execute(
            text(
                "SELECT tipo_dato_glaser, COUNT(*) FROM segmentos "
                "WHERE documento_id = :did AND tipo_dato_glaser IS NOT NULL "
                "GROUP BY tipo_dato_glaser"
            ),
            {"did": documento_id},
        ).fetchall()
        glaser_hint_text = (
            ", ".join(f"{row[0]}: {row[1]}" for row in glaser_summary)
            or "(sin clasificar)"
        )
        task_section_with_hint = task_section + (
            "\n\n[CLASIFICACIÓN GLASER DE ESTE DOCUMENTO]\n"
            f"Distribución: {glaser_hint_text}\n"
            "Usa esto como contexto para tu análisis del proceso."
        )

        response = llm.run_agent(
            agent_id=agent_id,
            variables={
                "population_assumption": pop_assumption,
                "previous_process": prev_process,
                "segments": segments_text,
                "task_section": task_section_with_hint,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
                "coding_style_instruction": _get_coding_style_instruction(
                    session, proyecto_id
                ),
                "processing_verb": processing_verb,
            },
            temperature=0.3,
        )

        if response.get("mock_note"):
            return {"error": "mock fallback"}

        # Validate: don't save empty outputs
        pd = (response.get("process_description") or "").strip()
        stp = (response.get("similarity_to_previous") or "").strip()
        dfp = (response.get("difference_from_previous") or "").strip()
        if not pd:
            logger.info(
                "A2: empty process_description for doc=%s — skipping (non-fatal)",
                documento_id,
            )
            return {"status": "skipped_empty", "documento_id": documento_id}

        result = session.execute(
            text(
                "INSERT INTO document_processes (id, documento_id, proyecto_id, process_description, similarity_to_previous, difference_from_previous, previous_document_id) VALUES (gen_random_uuid(), :did, :pid, :pd, :stp, :dfp, :prevd) RETURNING id"
            ),
            {
                "did": documento_id,
                "pid": proyecto_id,
                "pd": pd,
                "stp": stp or None,
                "dfp": dfp or None,
                "prevd": str(previous[1]) if previous else None,
            },
        )
        session.commit()
        new_id = str(result.fetchone()[0])

        return {
            "document_process_id": new_id,
            "process_description": pd,
            "is_first_document": is_first,
            "has_comparison": not is_first,
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# A3: SENSE_MAKER
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="a3_make_sense")
def a3_make_sense(proyecto_id: str) -> dict:
    session = SessionLocal()
    try:
        doc_count = session.execute(
            text("SELECT COUNT(*) FROM document_processes WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if doc_count < 3:
            return {
                "skipped": True,
                "reason": f"Solo {doc_count} docs. Se necesitan ≥ 3.",
            }

        pop_assumption = _get_population_assumption(session, proyecto_id)

        # Fetch operational question from Nemotron output
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = pa_data.get("research_question", {})
        operational_question = rq_data.get("operational_question", "")
        oos_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        pop_ctx = session.execute(
            text(
                "SELECT surprising_details FROM population_contexts WHERE proyecto_id = :pid ORDER BY version DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        processes = session.execute(
            text(
                "SELECT process_description FROM document_processes WHERE proyecto_id = :pid ORDER BY creado_en"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        existing = session.execute(
            text(
                "SELECT text, status FROM hypotheses WHERE project_id = :pid AND status != 'rejected'"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        is_first_time = len(existing) == 0

        processes_text = "\n".join(
            f"Doc {i + 1}: {p[0]}" for i, p in enumerate(processes)
        )
        hyp_text = (
            "\n".join(f"- [{h[1]}] {h[0]}" for h in existing)
            if existing
            else "(sin hipótesis previas)"
        )

        task_section = (
            "[TAREA]\n"
            "Es la primera vez que buscamos sentido en estos datos.\n"
            "¿Qué ideas o hipótesis tentativas podrían darle sentido\n"
            "a los patrones y diferencias hallados hasta ahora?\n"
            "Propón posibilidades. NO las verifiques.\n"
            "Cada idea debe estar anclada en evidencia concreta de los datos.\n"
            "Para sense_status, responde 'no_change' (es el primer análisis)."
            if is_first_time
            else "[TAREA]\n"
            "Ya tenemos hipótesis establecidas. Evalúa si los nuevos datos\n"
            "las MODIFICAN (matizan), las CAMBIAN SUSTANCIALMENTE (refutan),\n"
            "o NO LAS CAMBIAN (son consistentes).\n"
            "Para cada cambio, propón la hipótesis actualizada con su evidencia."
        )

        response = llm.run_agent(
            agent_id="fa_sense_maker",
            variables={
                "population_assumption": pop_assumption,
                "population_context": pop_ctx[0] if pop_ctx else "",
                "processes": processes_text,
                "existing_hypotheses": hyp_text,
                "task_section": task_section,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
            },
            temperature=0.4,
        )

        if response.get("mock_note"):
            return {"error": "mock fallback"}

        new_count = 0
        modified_count = 0
        for hyp in response.get("hypotheses", []):
            hyp_text = hyp.get("text", "").strip()
            if not hyp_text:
                continue
            existing_hyp = session.execute(
                text(
                    "SELECT id FROM hypotheses WHERE project_id = :pid AND text = :txt"
                ),
                {"pid": proyecto_id, "txt": hyp_text},
            ).fetchone()
            if existing_hyp:
                session.execute(
                    text(
                        "UPDATE hypotheses SET status='candidate', level=:lvl WHERE id=:hid"
                    ),
                    {"lvl": hyp.get("level", "emergent"), "hid": existing_hyp[0]},
                )
                modified_count += 1
            else:
                session.execute(
                    text(
                        "INSERT INTO hypotheses (id, project_id, text, level, confidence, status) VALUES (gen_random_uuid(), :pid, :txt, :lvl, 0.5, 'candidate')"
                    ),
                    {
                        "pid": proyecto_id,
                        "txt": hyp_text,
                        "lvl": hyp.get("level", "emergent"),
                    },
                )
                new_count += 1
        session.commit()

        return {
            "sense_status": response.get("sense_status", "no_change"),
            "new_hypotheses": new_count,
            "modified_hypotheses": modified_count,
            "total_documents": doc_count,
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Funciones auxiliares del pipeline
# ═══════════════════════════════════════════════════════════════════════


def _ensure_segmented(session, documento_id: str) -> None:
    """Verifica que el doc tenga segmentos. Lanza error si no."""
    count = session.execute(
        text("SELECT COUNT(*) FROM segmentos WHERE documento_id = :did"),
        {"did": documento_id},
    ).fetchone()[0]
    if count > 0:
        return
    raise RuntimeError(
        f"Doc {documento_id} sin segmentos — el orchestrator no debio despachar agentes"
    )


BATCH_SIZE = 25  # segments per AI call for large documents


def _classify_glaser_types_for_doc(
    session, documento_id: str, use_llm_fallback: bool = True
) -> int:
    """F2.1: Clasifica todos los segmentos de un documento via AI en batch.

    Envía TODOS los segmentos en lotes de BATCH_SIZE a un modelo PRO.
    La IA hace explication de texte: clasifica cada segmento y detecta
    preguntas del autor (→ 'interviewer_context').

    Sin capa algorítmica. Sin FLASH por segmento.

    Persiste en segmentos.tipo_dato_glaser.

    Returns:
        Número de segmentos clasificados.
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

    # Build segment list for the batch classifier
    all_segments = [
        {"id": str(r[0]), "text": r[1] or "", "posicion": r[2]} for r in rows
    ]

    # Check project config for interviewer flag
    allow_interviewer = False
    try:
        proj = session.execute(
            text(
                "SELECT population_assumption FROM proyectos p "
                "JOIN documentos d ON d.proyecto_id = p.id "
                "WHERE d.id = :did"
            ),
            {"did": documento_id},
        ).fetchone()
        if proj and proj[0] and isinstance(proj[0], dict):
            allow_interviewer = proj[0].get("allow_interviewer_as_baseline", False)
    except Exception:
        pass

    classified = 0
    total = len(all_segments)
    batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    logger.info(
        "Glaser batch classification: doc=%s, %d segments → %d batch(es) [BATCH_SIZE=%d]",
        documento_id[:8],
        total,
        batches,
        BATCH_SIZE,
    )

    for batch_idx in range(batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = all_segments[start:end]

        logger.info(
            "Glaser batch %d/%d: %d segments",
            batch_idx + 1,
            batches,
            len(batch),
        )

        if not use_llm_fallback:
            # Conservative default: everything baseline
            for s in batch:
                session.execute(
                    text(
                        "UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"
                    ),
                    {"tipo": "baseline_data", "sid": s["id"]},
                )
                classified += 1
            continue

        results = classify_segments_batch(
            batch,
            llm_client=llm,
            allow_interviewer_as_baseline=allow_interviewer,
        )

        for r in results:
            glaser_type = r.get("glaser_data_type")
            if glaser_type:
                session.execute(
                    text(
                        "UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"
                    ),
                    {"tipo": glaser_type, "sid": r["segment_id"]},
                )
                classified += 1

    session.commit()
    logger.info(
        "Glaser classification complete: %d/%d segments (doc=%s, batches=%d)",
        classified,
        total,
        documento_id[:8],
        batches,
    )
    return classified


def _anchor_segments(session, documento_id: str, full_text: str) -> None:
    """A2: Calcula first_10, start_char, end_char para cada segmento."""
    import re as _re
    import sys as _sys

    _sys.path.insert(0, "/app")
    try:
        from workers.nlp.segmentador import AnchorBasedReconstructor

        reconstructor = AnchorBasedReconstructor()
    except Exception as e:
        logger.warning("AnchorBasedReconstructor no disponible: %s", e)
        return

    segments = session.execute(
        text(
            "SELECT id, texto FROM segmentos WHERE documento_id = :did ORDER BY posicion"
        ),
        {"did": documento_id},
    ).fetchall()

    if not segments:
        return

    # Preparar datos para el reconstructor
    seg_data = []
    for seg_id, seg_text in segments:
        words = seg_text.split()
        first_10 = " ".join(words[:10]) if len(words) >= 10 else seg_text[:100]
        # Estimar length: contar oraciones en el texto del segmento
        length = len(_re.split(r"[.!?]+", seg_text))
        seg_data.append(
            {
                "id": str(seg_id),
                "first_10": first_10,
                "length": max(1, length),
                "text": seg_text,
            }
        )

    # Reconstruir
    try:
        reconstructed = reconstructor.reconstruct(full_text, seg_data)
    except Exception as e:
        logger.warning("Reconstructor fallo: %s", e)
        return

    # Actualizar DB
    updated = 0
    for rec in reconstructed:
        if rec.get("is_exact_match") or rec.get("start_char") is not None:
            session.execute(
                text(
                    "UPDATE segmentos SET first_10 = :f10, start_char = :sc, "
                    "end_char = :ec, is_exact_match = :iem WHERE id = :sid"
                ),
                {
                    "f10": rec.get("first_10", ""),
                    "sc": rec.get("start_char"),
                    "ec": rec.get("end_char"),
                    "iem": rec.get("is_exact_match", False),
                    "sid": rec["id"],
                },
            )
            updated += 1

    session.commit()
    logger.info(
        "A2 anchors: %d/%d segmentos anclados (doc=%s)",
        updated,
        len(segments),
        documento_id,
    )


def _extract_prime_mover(session, documento_id: str, proyecto_id: str) -> dict | None:
    """C06: Extrae prime mover usando SOLO baseline_data. Se adapta al object_of_study."""
    # Obtener configuracion del proyecto
    config = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    pa_data = config[0] if config and config[0] else {}
    obj = "concern"  # default
    if isinstance(pa_data, dict):
        obj = pa_data.get("object_of_study", "concern")
        operational_question = pa_data.get("research_question", {}).get(
            "operational_question", ""
        )
    else:
        operational_question = ""

    # Obtener baseline_data segments
    baseline = session.execute(
        text(
            "SELECT texto FROM segmentos WHERE documento_id = :did "
            "AND (tipo_dato_glaser = 'baseline_data' OR tipo_dato_glaser IS NULL) "
            "ORDER BY posicion LIMIT 10"
        ),
        {"did": documento_id},
    ).fetchall()

    if len(baseline) < 2:
        return {"prime_mover": "", "insufficient_data": True}

    segments_text = "\n---\n".join(r[0] for r in baseline)
    doc_name = session.execute(
        text("SELECT original_filename FROM documentos WHERE id = :did"),
        {"did": documento_id},
    ).fetchone()

    response = llm.run_agent(
        "fa_prime_mover_extractor",
        variables={
            "document_name": doc_name[0] if doc_name else "",
            "baseline_segments": segments_text[:6000],
            "object_of_study": obj,
            "operational_question": operational_question or "(not yet generated)",
            "coding_style_instruction": _get_coding_style_instruction(
                session, proyecto_id
            ),
        },
        temperature=0.3,
    )

    return {
        "prime_mover": response.get("prime_mover", ""),
        "description": response.get("description", ""),
        "confidence": response.get("confidence", "LOW"),
        "insufficient_data": response.get("insufficient_data", False),
    }


# ═══════════════════════════════════════════════════════════════════════
# Agents B — wrappers Celery (implementación en agents_b.py)
# Pipeline A — con soporte de checkpoint/resume
# ═══════════════════════════════════════════════════════════════════════

import signal as _signal

from celery import Task as _CeleryTask


class AbortableTask(_CeleryTask):
    """Tarea Celery que puede ser abortada limpiamente con SIGTERM.

    Cuando se llama revoke(task_id, terminate=True, signal='SIGTERM'),
    el worker recibe la señal y la tarea puede hacer cleanup en finally.
    """

    def __init__(self):
        self._aborted = False
        self._original_sigterm = None

    def __call__(self, *args, **kwargs):
        self._original_sigterm = _signal.getsignal(_signal.SIGTERM)
        _signal.signal(_signal.SIGTERM, self._handle_sigterm)
        try:
            return super().__call__(*args, **kwargs)
        finally:
            if self._original_sigterm:
                _signal.signal(_signal.SIGTERM, self._original_sigterm)

    def _handle_sigterm(self, signum, frame):
        self._aborted = True
        logger.warning("Task %s received SIGTERM — aborting gracefully", self.name)
        if self._original_sigterm:
            _signal.signal(_signal.SIGTERM, self._original_sigterm)
        raise TaskCancelledError(task_id=self.request.id if self.request else "")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Mark PipelineTask as failed so frontend can detect & abort pipeline."""
        try:
            from database import SessionLocal
            from sqlalchemy import text

            s = SessionLocal()
            s.execute(
                text(
                    "UPDATE pipeline_tasks SET status = 'failed' "
                    "WHERE celery_task_id = :tid AND status != 'completed'"
                ),
                {"tid": task_id},
            )
            s.commit()
            s.close()
        except Exception:
            pass


class TaskCancelledError(Exception):
    """La tarea fue cancelada vía SIGTERM."""

    def __init__(self, task_id: str = ""):
        super().__init__(f"Task {task_id} cancelled")
        self.task_id = task_id


@app.task(
    name="process_document_agents_a",
    base=AbortableTask,
    bind=True,
)
def process_document_agents_a(
    self,
    documento_id: str,
    proyecto_id: str,
    resume_from_step: str | None = None,
) -> dict:
    """
    Procesa un documento con agentes A (A1→A2→PrimeMover→A3).

    Soporta resume: si se canceló a mitad, al re-ejecutar con
    resume_from_step, limpia los pasos "in_progress" y continúa
    desde el primer paso no completado.
    """
    from agents.checkpoint_helpers import (
        checkpoint,
        cleanup_step,
        load_checkpoints,
    )
    from agents.transitions import transition as transit

    results: dict[str, Any] = {"documento_id": documento_id}
    session = SessionLocal()
    _set_language_from_project(session, proyecto_id)

    try:
        _pipeline_log_to(proyecto_id)
        logger.info("🧠 Open Coding iniciado — doc=%s", documento_id)

        # ── Detectar punto de resume ──
        completed: set[str] = set()
        if resume_from_step:
            completed, dirty = load_checkpoints(session, documento_id)
            for step in dirty:
                cleanup_step(session, step, documento_id)
            logger.info(
                "Resume: %d steps completed, %d dirty cleaned. Starting from '%s'",
                len(completed),
                len(dirty),
                resume_from_step,
            )

        # ── Step 0: Segmentation ──
        STEP = "segmentation"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            _ensure_segmented(session, documento_id)
            # F2.1: Pre-clasificar tipo de dato Glaser para cada segmento
            _classify_glaser_types_for_doc(session, documento_id, use_llm_fallback=True)
            checkpoint(session, documento_id, STEP, "completed")

        # ── Step 0.5: F2.3 — Extract patterns & incidents (unified PRO call) ──
        # Replaces old per-segment extract_incident (~13 FLASH) + extract_core_pattern (1 PRO)
        # + _extract_prime_mover (1 FLASH). ONE PRO call does all three.
        STEP = "extract_incidents"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("F2.3: Extracting patterns & incidents doc %s", documento_id)
            try:
                from pattern_extractor import (
                    extract_patterns_and_incidents as _extract_pi,
                )

                pi_result = _extract_pi(documento_id, proyecto_id)
                results["patterns"] = pi_result.get("patterns", [])
                results["incidents_extracted"] = pi_result.get("incidents_count", 0)
                results["document_signals"] = pi_result.get("document_signals", {})
                logger.info(
                    "F2.3: %d patterns, %d incidents doc %s",
                    len(results["patterns"]),
                    results["incidents_extracted"],
                    documento_id,
                )
            except Exception as e:
                logger.warning("Pattern extraction failed: %s", e)
                results["patterns"] = []
                results["incidents_extracted"] = 0
                results["document_signals"] = {}
            checkpoint(session, documento_id, STEP, "completed")

        # ── Step 0.7: F2.5 — Every 3 documents, verify pattern convergence (PRO) ──
        if self._aborted:
            raise TaskCancelledError()
        doc_count = session.execute(
            text(
                "SELECT COUNT(*) FROM document_processes "
                "WHERE proyecto_id = :pid AND prime_mover_confidence IS NOT NULL"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if doc_count >= 3 and doc_count % 3 == 0:
            logger.info(
                "F2.5: Dispatching verify_core_pattern for project=%s (doc %d)",
                proyecto_id[:8],
                doc_count,
            )
            try:
                app.send_task(
                    "verify_core_pattern",
                    args=[proyecto_id],
                    queue="heavy",
                )
                results["pattern_verification_dispatched"] = True
            except Exception as e:
                logger.warning("F2.5 verify_core_pattern dispatch failed: %s", e)
                results["pattern_verification_dispatched"] = False

        # ── Update estado → procesando ──
        session.execute(
            text("UPDATE documentos SET estado = 'procesando' WHERE id = :did"),
            {"did": documento_id},
        )
        session.commit()

        # ── Step 1: A1 — Population Context ──
        STEP = "a1_population_context"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("A1: Contexto poblacional doc %s", documento_id)
            results["population_context"] = a1_build_population_context(
                documento_id, proyecto_id
            )
            checkpoint(session, documento_id, STEP, "completed")
            # A1 is auxiliary — don't block the pipeline on empty context

        # ── Step 2: A2 — Process Identification ──
        STEP = "a2_identify_process"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("A2: Proceso doc %s", documento_id)
            results["document_process"] = a2_identify_process(documento_id, proyecto_id)
            checkpoint(session, documento_id, STEP, "completed")
            # A2 is auxiliary — don't block pipeline on empty process description

        # ── Step 3: Prime Mover (already extracted by F2.3 unified call) ──
        # skip — prime_mover is in results["document_signals"] from extract_patterns_and_incidents

        # ── Step 4: A3 — Sense Making ──
        STEP = "a3_make_sense"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("A3: Sentido emergente proyecto %s", proyecto_id)
            results["sense_making"] = a3_make_sense(proyecto_id)
            checkpoint(session, documento_id, STEP, "completed")

        # ── Transition: mark ready + maybe trigger Phase B ──
        transit(
            session,
            documento_id,
            proyecto_id,
            "procesando",
            "process_document_agents_a",
            True,
        )

        return results

    except TaskCancelledError:
        logger.warning(
            "Task process_document_agents_a cancelled for doc=%s", documento_id
        )
        return {"status": "cancelled", "documento_id": documento_id}
    except Exception as e:
        transit(
            session,
            documento_id,
            proyecto_id,
            "procesando",
            "process_document_agents_a",
            False,
        )
        raise
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Agentes B — wrappers Celery (F2.3: Comparator / Labeler / Critic)
# ═══════════════════════════════════════════════════════════════════════

# ── Legacy imports (deprecated — keep for reference) ──
from agents_b import (
    b1_distill_sampling,
    b2_5_assign_codes_to_segments,
    b2_open_code,
    b3_generate_hypotheses,
    update_hypotheses_incremental,
)

# ── New F2.3 agent imports ──
from comparator import b1_group_incidents
from config_critic import critique_configuration
from core_category_proposer import propose_core_categories as _propose_core_categories
from label_critic import b3_critique_labels
from labeler import b2_label_groups
from synthesizer import synthesize_categories as _synthesize_categories

# ── Legacy tasks (deprecated — kept for backward compatibility) ──


@app.task(name="b1_distill_sampling")  # DEPRECATED: use b1_compare_incidents instead
def task_b1_distill_sampling(proyecto_id: str) -> dict:
    return b1_distill_sampling(proyecto_id)


@app.task(name="b2_open_code")  # DEPRECATED: use b2_label_groups instead
def task_b2_open_code(proyecto_id: str) -> dict:
    return b2_open_code(proyecto_id)


@app.task(name="b3_generate_hypotheses")  # DEPRECATED: use b3_critique_labels instead
def task_b3_generate_hypotheses(proyecto_id: str) -> dict:
    return b3_generate_hypotheses(proyecto_id)


# ── New F2.3 tasks ──


@app.task(name="b1_compare_incidents")
def task_b1_compare_incidents(proyecto_id: str, incremental: bool = False) -> dict:
    """Redirect to new AI-only grouper."""
    return b1_group_incidents(proyecto_id, incremental)


@app.task(name="b2_label_groups")
def task_b2_label_groups(proyecto_id: str) -> dict:
    return b2_label_groups(proyecto_id)


@app.task(name="b3_critique_labels")
def task_b3_critique_labels(groups_json: str, labels_json: str) -> dict:
    """Standalone label critique (FLASH). Returns {issues: [...]} — empty issues = good.

    Also called internally by B2's concept-by-concept SelfRefinement loop.
    """
    return b3_critique_labels(groups_json, labels_json)


@app.task(name="synthesize_categories")
def task_synthesize_categories(
    proyecto_id: str, batch_start_doc_index: int = 1
) -> dict:
    """Category synthesizer: merges new categories from the current 3-doc batch
    with previous categories from earlier batches.

    Runs AFTER B2/B3 completes. Receives ALL categories, separates them into
    previous (docs < batch_start) and new (docs >= batch_start), and calls the
    AI (fd_category_synthesizer, PRO) to produce a unified deduplicated set.

    Args:
            proyecto_id: Project UUID.
            batch_start_doc_index: 1-based index of the first doc in the current batch.
                    Batch 1 (docs 1-3) → batch_start=1 (no previous, just records).
                    Batch 2 (docs 4-6) → batch_start=4 (merges with docs 1-3).
                    Batch 3 (docs 7-9) → batch_start=7 (merges with docs 1-6).
    """
    return _synthesize_categories(proyecto_id, batch_start_doc_index)


@app.task(name="critique_configuration")
def task_critique_configuration(proyecto_id: str, batch_start: int) -> dict:
    """Configuration Critic: reviews emerging theoretical configuration after every
    3-doc batch (post-synthesizer). Evaluates concerns, population reconfigurations,
    and coding style adequacy.

    Dispatched from process_synthesis_agents_b after the synthesizer and
    update_hypotheses complete.

    Reads current categories and hypotheses from DB, then calls the critic.

    Args:
        proyecto_id: Project UUID.
        batch_start: 1-based index of the first document in the current batch.
    """
    s = SessionLocal()
    try:
        # ── Load categories (same shape as synthesizer produces) ──
        cat_rows = s.execute(
            text(
                "SELECT id, nombre, definicion FROM categorias WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        categories = []
        for cr in cat_rows:
            cat_id = str(cr[0])
            # Count incident groups linked to this category
            inc_count = s.execute(
                text(
                    "SELECT COUNT(*) FROM incident_groups "
                    "WHERE proyecto_id = :pid AND label = :name"
                ),
                {"pid": proyecto_id, "name": cr[1]},
            ).fetchone()

            # Count docs linked to this category
            doc_count = s.execute(
                text(
                    "SELECT COUNT(DISTINCT d.id) "
                    "FROM codigos_segmento cs "
                    "JOIN segmentos seg ON cs.segmento_id = seg.id "
                    "JOIN documentos d ON seg.documento_id = d.id "
                    "WHERE cs.categoria_id = :cid "
                    "AND d.proyecto_id = :pid"
                ),
                {"cid": cat_id, "pid": proyecto_id},
            ).fetchone()

            categories.append(
                {
                    "id": cat_id,
                    "label": cr[1] or "",
                    "definition": cr[2] or "",
                    "incident_count": inc_count[0] if inc_count else 0,
                    "doc_count": doc_count[0] if doc_count else 0,
                }
            )

        # ── Load hypotheses ──
        hyp_rows = s.execute(
            text(
                "SELECT text, level, confidence "
                "FROM hypotheses "
                "WHERE project_id = :pid AND status = 'candidate'"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        hypotheses = []
        for hr in hyp_rows:
            hypotheses.append(
                {
                    "text": hr[0] or "",
                    "level": hr[1] or "general",
                    "confidence": float(hr[2]) if hr[2] else 0.0,
                }
            )

        return critique_configuration(proyecto_id, batch_start, categories, hypotheses)
    finally:
        s.close()


@app.task(name="update_hypotheses")
def task_update_hypotheses(proyecto_id: str) -> dict:
    """Recurring hypotheses agent: runs after each synthesizer to update
    relationship notes between categories. Grows over time.

    Reads all existing hypotheses memos + all current categories with their
    indicators + which documents they appear in. Calls AI to evaluate
    cross-category relationships and stores the growing note in memos.
    """
    return update_hypotheses_incremental(proyecto_id)


# ═══════════════════════════════════════════════════════════════════════
# F2.3 — Pattern & Incident Extractor (replaces old per-segment extract_incident)
# ═══════════════════════════════════════════════════════════════════════

from pattern_extractor import extract_patterns_and_incidents as _extract_pi_impl


@app.task(name="extract_incident")
def task_extract_incident(segment_id: str, proyecto_id: str) -> dict:
    """DEPRECATED: Use extract_patterns_and_incidents (unified PRO call per doc).
    Kept for backward compatibility. Redirects to unified extractor."""
    logger.warning(
        "extract_incident called directly for seg=%s — redirecting to unified extractor",
        segment_id[:8],
    )
    return {
        "status": "deprecated",
        "message": "Use extract_patterns_and_incidents instead",
    }


@app.task(name="extract_core_pattern")
def task_extract_core_pattern(documento_id: str, proyecto_id: str) -> dict:
    """DEPRECATED: Core pattern now extracted as part of extract_patterns_and_incidents.
    Kept for backward compatibility."""
    return _extract_pi_impl(documento_id, proyecto_id)


# ═══════════════════════════════════════════════════════════════════════
# F5.4 — Literature Dialogue
# ═══════════════════════════════════════════════════════════════════════

from literature import compare_literature as _compare_literature_impl
from literature import critique_literature_dialogue as _critique_literature_impl


@app.task(name="f6c_literature_comparer")
def task_literature_comparer(proyecto_id: str, literature_fragments: list[str]) -> dict:
    """F5.4: Compara fragmentos de literatura contra la teoría fundamentada (PRO)."""
    return _compare_literature_impl(proyecto_id, literature_fragments)


@app.task(name="f6c_literature_critic")
def task_literature_critic(comparison_table: dict, proyecto_id: str = None) -> dict:
    """F5.4: Evalúa si el diálogo con literatura fuerza coincidencias o trata la literatura como autoridad (PRO)."""
    return _critique_literature_impl(comparison_table, proyecto_id)


# ═══════════════════════════════════════════════════════════════════════
# F5.5 — Applicability
# ═══════════════════════════════════════════════════════════════════════

from applicability import critique_applicability as _critique_applicability_impl
from applicability import generate_applicability as _generate_applicability_impl


@app.task(name="f6d_applicability_engine")
def task_applicability_engine(proyecto_id: str) -> dict:
    """F5.5: Genera directrices de aplicabilidad desde la teoría fundamentada (PRO)."""
    return _generate_applicability_impl(proyecto_id)


@app.task(name="f6d_applicability_critic")
def task_applicability_critic(directrices: dict, proyecto_id: str = None) -> dict:
    """F5.5: Evalúa si las directrices de aplicabilidad son genuinas, accesibles y modificables (PRO)."""
    return _critique_applicability_impl(directrices, proyecto_id)


# ═══════════════════════════════════════════════════════════════════════
# F5.3 / Fase 6a — Redacción Natural: Writer + Critic + Gap Feeler
# ═══════════════════════════════════════════════════════════════════════

from writer import critique_section as _critique_section_impl
from writer import feel_gaps as _feel_gaps_impl
from writer import write_section as _write_section_impl


@app.task(name="f6a_natural_writer")
def task_natural_writer(sorting_group_id: str, proyecto_id: str) -> dict:
    """F5.3: Redacta una sección teórica desde memos ordenados (PRO)."""
    return _write_section_impl(sorting_group_id, proyecto_id)


@app.task(name="f6a_writing_critic")
def task_writing_critic(draft: str, memo_ids: list[str], proyecto_id: str) -> dict:
    """F5.3: Evalúa un borrador contra reglas CGT (PRO)."""
    return _critique_section_impl(draft, memo_ids, proyecto_id)


@app.task(name="f6a_gap_feeler")
def task_gap_feeler(draft: str, project_id: str) -> list[dict]:
    """F5.3: Monitorea escritura en background detectando huecos (FLASH, non-blocking)."""
    return _feel_gaps_impl(draft, project_id)


# ═══════════════════════════════════════════════════════════════════════
# F5.6: ReSpecAgent — Re-especificacion jerarquica
# ═══════════════════════════════════════════════════════════════════════

from respect_agent import evaluate_respec_signals as _evaluate_respec_signals
from respect_agent import query_lower_level as _query_lower_level


@app.task(name="evaluate_respec_signals")
def task_evaluate_respec_signals(proyecto_id: str) -> dict:
    """F5.6: Evalua senales de re-especificacion (ambiguos, rechazados, divergentes, huerfanos)."""
    return _evaluate_respec_signals(proyecto_id)


@app.task(name="query_lower_level")
def task_query_lower_level(
    entity_type: str, entity_id: str, direction: str = "down"
) -> dict:
    """F5.6: Baja un nivel de abstraccion para re-examinar una entidad."""
    return _query_lower_level(entity_type, entity_id, direction)


@app.task(
    name="process_synthesis_agents_b",
    base=AbortableTask,
    bind=True,
)
def process_synthesis_agents_b(self, proyecto_id: str) -> dict:
    """F2.3 Pipeline: Comparator (B1) → Labeler (B2 + Critic B3 loop) → Grounding → Hypotheses.

    New flow (post-F2.3 refactor):
      1. B1: incident_comparator (PRO) — compares extracted_incidents, creates groups
      2. B2: pattern_labeler (PRO + FLASH critic) — labels groups with SelfRefinement
      3. B2.5: assign codes to segments (grounding, RAG evidence)
      4. B17: update saturation
      5. B18: rebuild prototype cache
      6. B3: generate hypotheses (updated to use incident_groups)
      7. Synthesizer: merge new categories with previous ones (async)
      8. Recurring Hypotheses: update relationship notes (async)
      9. Configuration Critic: review concerns, population, coding style (async)
      10. Transition all docs: listo → sintetizado
    """
    results: dict[str, Any] = {"proyecto_id": proyecto_id}

    # ── Check abort ──
    if self._aborted:
        raise TaskCancelledError()

    s = SessionLocal()
    _set_language_from_project(s, proyecto_id)
    try:
        _pipeline_log_to(proyecto_id)
        logger.info("🔗 Phase B iniciado — proyecto=%s", proyecto_id)

        # ── B1: Incident Grouper (AI-only, no pre-filter) ──
        if self._aborted:
            raise TaskCancelledError()
        _checkpoint_step(s, proyecto_id, "b1_compare_incidents", "in_progress")
        logger.info("B1: Grouping incidents %s", proyecto_id)
        results["comparator"] = b1_group_incidents(proyecto_id)
        _checkpoint_step(s, proyecto_id, "b1_compare_incidents", "completed")

        # ── F2.3 B2: Pattern Labeler (PRO + SelfRefinement loop) ──
        if self._aborted:
            raise TaskCancelledError()
        _checkpoint_step(s, proyecto_id, "b2_label_groups", "in_progress")
        logger.info("B2: Etiquetando grupos %s", proyecto_id)
        results["labeler"] = b2_label_groups(proyecto_id)
        _checkpoint_step(s, proyecto_id, "b2_label_groups", "completed")

        # ── B2.5: Grounding (assign codes to segments + RAG evidence) ──
        if self._aborted:
            raise TaskCancelledError()
        _checkpoint_step(s, proyecto_id, "b2_5_assign_codes", "in_progress")
        logger.info("B2.5: Grounding %s", proyecto_id)
        results["grounding"] = b2_5_assign_codes_to_segments(proyecto_id)
        _checkpoint_step(s, proyecto_id, "b2_5_assign_codes", "completed")

        # ── B17: SaturationCalculator ──
        try:
            app.send_task("update_saturation", args=[proyecto_id], queue="nlp")
        except Exception:
            pass

        # ── B18: Prototype cache rebuild ──
        try:
            __rebuild_cache(proyecto_id)
        except Exception:
            pass

        # ── B3: Hypotheses (updated to use incident_groups) ──
        if self._aborted:
            raise TaskCancelledError()
        _checkpoint_step(s, proyecto_id, "b3_generate_hypotheses", "in_progress")
        logger.info("B3: Hipotesis %s", proyecto_id)
        results["hypotheses"] = b3_generate_hypotheses(proyecto_id)
        _checkpoint_step(s, proyecto_id, "b3_generate_hypotheses", "completed")

        # ── Synthesizer: merge new categories with previous ones ──
        # Calculate batch_start_doc_index based on total document count.
        # Batch 1: docs 1-3 (batch_start=1), Batch 2: docs 4-6 (batch_start=4), etc.
        batch_start = 1
        try:
            total_docs = s.execute(
                text("SELECT COUNT(*) FROM documentos WHERE proyecto_id = :pid"),
                {"pid": proyecto_id},
            ).fetchone()[0]
            batch_start = ((total_docs - 1) // 3) * 3 + 1 if total_docs > 0 else 1
            logger.info(
                "Dispatching synthesizer: project=%s batch_start=%d (total_docs=%d)",
                proyecto_id[:8],
                batch_start,
                total_docs,
            )
            app.send_task(
                "synthesize_categories",
                args=[proyecto_id, batch_start],
                queue="heavy",
            )
        except Exception:
            logger.exception("Failed to dispatch synthesizer for %s", proyecto_id)

        # ── Recurring Hypotheses: update relationship notes after each synthesizer ──
        try:
            logger.info(
                "Dispatching update_hypotheses (recurring) for project %s",
                proyecto_id[:8],
            )
            app.send_task(
                "update_hypotheses",
                args=[proyecto_id],
                queue="heavy",
            )
        except Exception:
            logger.exception("Failed to dispatch update_hypotheses for %s", proyecto_id)

        # ── Configuration Critic: review concerns, population, coding style ──
        try:
            logger.info(
                "Dispatching config_critic for project %s (batch_start=%d)",
                proyecto_id[:8],
                batch_start,
            )
            app.send_task(
                "critique_configuration",
                args=[proyecto_id, batch_start],
                queue="heavy",
            )
        except Exception:
            logger.exception("Failed to dispatch config_critic for %s", proyecto_id)

        # ── Transition all docs: listo → sintetizado ──
        _transition_docs_to_sintetizado(s, proyecto_id)

        return results

    except TaskCancelledError:
        _checkpoint_step(s, proyecto_id, "cancelled", "completed")
        return {"status": "cancelled", "proyecto_id": proyecto_id}
    except Exception:
        logger.exception("process_synthesis_agents_b failed for %s", proyecto_id)
        # Push error to pipeline logs so overlay shows it even if worker crashes
        try:
            _plog(
                proyecto_id,
                "[ERROR] Phase B (synthesis) FAILED — check worker-heavy logs",
            )
        except Exception:
            pass
        raise
    finally:
        s.close()


def _checkpoint_step(session, proyecto_id: str, step_name: str, status: str) -> None:
    """Registra un checkpoint de paso para resumibilidad (REGLA 4)."""
    try:
        session.execute(
            text(
                "INSERT INTO task_step_checkpoints "
                "(id, document_id, step_name, status, affected_rows) "
                "VALUES (gen_random_uuid(), NULL, :step, :status, CAST('{}' AS jsonb))"
            ),
            {"step": step_name, "status": status},
        )
        session.commit()
    except Exception:
        pass  # non-critical


def _transition_docs_to_sintetizado(session, proyecto_id: str) -> int:
    """Transiciona todos los docs 'listo' del proyecto a 'sintetizado'."""
    from agents.transitions import _maybe_trigger_selective_coding

    result = session.execute(
        text(
            "UPDATE documentos SET estado = 'sintetizado' "
            "WHERE proyecto_id = :pid AND estado = 'listo'"
        ),
        {"pid": proyecto_id},
    )
    session.commit()
    count = result.rowcount
    if count > 0:
        logger.info(
            "Transitioned %d docs to 'sintetizado' for project %s", count, proyecto_id
        )
        _maybe_trigger_selective_coding(session, proyecto_id)
    return count


def _prepare_playground_for_project(proyecto_id: str) -> None:
    """
    Prepara el ecosistema del Theoretical Playground cuando el proyecto
    llega a playground_ready: seed de códigos teóricos, layout inicial,
    ghost blobs desde memos huérfanos.
    """
    try:
        import sys as _s

        _s.path.insert(0, "/app")
        from app.services.ghost_connector import GhostConnector
        from app.services.theory_seeder import seed_theoretical_codes
        from database import SessionLocal as _SessionLocal

        s2 = _SessionLocal()
        try:
            # 1. Seed theoretical codes
            inserted = seed_theoretical_codes(s2)
            logger.info("Playground prep: seeded %d theoretical codes", inserted)

            # 2. Crear ecosystem layout inicial
            existing = s2.execute(
                text("SELECT id FROM ecosystem_layouts WHERE project_id = :pid"),
                {"pid": proyecto_id},
            ).fetchone()
            if not existing:
                s2.execute(
                    text(
                        "INSERT INTO ecosystem_layouts "
                        "(id, project_id, version, blob_positions, ghost_positions, "
                        "fog_zones, physics_params) "
                        "VALUES (gen_random_uuid(), :pid, 1, '{}', '{}', '{}', "
                        "CAST(:phys AS jsonb))"
                    ),
                    {
                        "pid": proyecto_id,
                        "phys": '{"attraction_strength":0.01,"repulsion":0.05,'
                        '"damping":0.95,"core_gravity":0.005,'
                        '"min_distance":80,"max_velocity":3.0}',
                    },
                )
                s2.commit()
                logger.info("Playground prep: created ecosystem layout")

            # 3. Generar ghost blobs desde memos huérfanos
            connector = GhostConnector(s2, llm)
            ghosts = connector.generate_ghost_blobs(proyecto_id)
            logger.info("Playground prep: generated %d ghost blobs", len(ghosts))

            # ── F6b: Tag all memos with theoretical coding families ──
            try:
                from theoretical import tag_memo_theoretically as _tmt

                memos = s2.execute(
                    text("SELECT id FROM memos WHERE proyecto_id = :pid"),
                    {"pid": proyecto_id},
                ).fetchall()
                for memo_row in memos:
                    try:
                        _tmt(memo_row[0], proyecto_id)
                    except Exception:
                        pass  # per-memo failure is non-blocking
                logger.info(
                    "F6b: tagged %d memos for project=%s",
                    len(memos),
                    proyecto_id[:8],
                )
            except Exception as e:
                logger.warning("F6b memo tagging failed (non-blocking): %s", e)

            # ── F6b: Detect ecosystem gaps ──
            try:
                from llm_client import LLMClient as _llm

                _lc = _llm()
                gaps = s2.execute(
                    text(
                        "SELECT DISTINCT category_id FROM ghost_blobs "
                        "WHERE proyecto_id = :pid AND suggested_category_id IS NULL"
                    ),
                    {"pid": proyecto_id},
                ).fetchall()
                unlinked_ghosts = len(gaps) if gaps else 0
                if unlinked_ghosts > 0:
                    logger.info(
                        "F6b: %d unlinked ghost blobs in project=%s",
                        unlinked_ghosts,
                        proyecto_id[:8],
                    )
                    # Dispatch gap_alerter (PRO) if significant gaps
                    if unlinked_ghosts >= 3:
                        try:
                            _lc.run_agent(
                                "f6b_gap_alerter",
                                variables={
                                    "core_concern": "(see hitl_decisions)",
                                    "object_of_study": "concern",
                                    "gaps_summary": f"{unlinked_ghosts} unlinked ghost blobs",
                                },
                            )
                        except Exception:
                            pass
            except Exception as e:
                logger.debug("F6b gap detection skipped: %s", e)

        finally:
            s2.close()
    except Exception as e:
        logger.warning("Playground prep failed (non-blocking): %s", e)


def __rebuild_cache(proyecto_id: str) -> int:
    """B18: Sincrono. Top-3 segmentos por codigo -> centroide -> Redis."""
    import json as _j

    s = SessionLocal()
    try:
        rows = s.execute(
            text("""
            SELECT cs.categoria_id, cs.segmento_id
            FROM codigos_segmento cs
            JOIN categorias c ON cs.categoria_id = c.id
            WHERE c.proyecto_id = :pid AND cs.confianza > 0.7
            ORDER BY cs.categoria_id, cs.confianza DESC
        """),
            {"pid": proyecto_id},
        ).fetchall()
        if not rows:
            return 0
        code_segs: dict = {}
        for row in rows:
            cid = str(row[0])
            if cid not in code_segs:
                code_segs[cid] = []
            if len(code_segs[cid]) < 3:
                code_segs[cid].append(str(row[1]))
        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))
        cached = 0
        for cid, sids in code_segs.items():
            er = s.execute(
                text(
                    "SELECT embedding FROM segmentos WHERE id = ANY(:ids) AND embedding IS NOT NULL"
                ),
                {"ids": sids},
            ).fetchall()
            embs = [e[0] for e in er]
            if not embs:
                continue
            dim = len(embs[0])
            cent = [sum(e[i] for e in embs) / len(embs) for i in range(dim)]
            r.setex(
                f"proto:{cid}",
                7200,
                _j.dumps(
                    {
                        "embedding": cent,
                        "segment_ids": sids,
                        "updated_at": __import__("datetime")
                        .datetime.utcnow()
                        .isoformat(),
                    }
                ),
            )
            cached += 1
        logger.info("B18: %d prototypes cached", cached)
        return cached
    finally:
        s.close()


@app.task(name="a06_theoretical_sample")
def task_a06_theoretical_sample(proyecto_id: str, targets: list[dict] = None) -> dict:
    """A6: TheoSampler SQL (ur mom.json). CTE con ANTI-JOIN + RANDOM estratificado."""
    s = SessionLocal()
    try:
        if targets is None:
            # Derivar targets desde memos de muestreo (B1)
            memos = s.execute(
                text(
                    "SELECT contenido FROM memos WHERE proyecto_id=:pid AND tipo='MUESTREO'"
                ),
                {"pid": proyecto_id},
            ).fetchall()
            targets = []
            for (m,) in memos:
                # Extraer dimensiones del memo como targets simples
                for line in m.split("\n"):
                    if ":" in line and any(
                        kw in line.lower()
                        for kw in ["contraste", "extremo", "consistente"]
                    ):
                        pass  # Simplificado: en produccion usaria LLM para derivar targets

        results_list = []
        for target in targets or []:
            rows = s.execute(
                text("""
                WITH target_values AS (
                    SELECT unnest(string_to_array(:vals, ',')) AS val
                ),
                available_docs AS (
                    SELECT d.id, d.original_filename, d.metadatos
                    FROM documentos d
                    JOIN target_values tv ON d.metadatos->>:key = tv.val
                    WHERE d.proyecto_id = :pid
                      AND d.id NOT IN (
                          SELECT unnest(c.saturation_docs)
                          FROM categorias c
                          WHERE c.proyecto_id = :pid
                            AND c.saturation_docs IS NOT NULL
                            AND jsonb_array_length(c.saturation_docs) > 0
                      )
                ),
                ranked_docs AS (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY metadatos->>:key
                            ORDER BY RANDOM()
                        ) AS rn
                    FROM available_docs
                )
                SELECT id, original_filename
                FROM ranked_docs
                WHERE rn = 1
            """),
                {
                    "vals": ",".join(target.get("vals", [])),
                    "key": target.get("key", ""),
                    "pid": proyecto_id,
                },
            ).fetchall()

            for row in rows:
                results_list.append(
                    {
                        "doc_id": str(row[0]),
                        "doc_name": row[1],
                        "target_key": target.get("key"),
                        "sample_type": target.get("sample_type", "contrast"),
                    }
                )

        return {"targets": len(targets or []), "docs_selected": len(results_list)}
    finally:
        s.close()


@app.task(name="a01_integrate_paradigm")
def task_a01_integrate_paradigm(code_id: str, proyecto_id: str) -> dict:
    """A1: Integrador Paradigmatico. Evalua si nuevos incidentes expanden el paradigma."""
    import json as _json

    s = SessionLocal()
    try:
        current = s.execute(
            text(
                "SELECT paradigm_snapshot, iteration FROM paradigm_states "
                "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 1"
            ),
            {"cid": code_id},
        ).fetchone()
        current_state = (
            current[0]
            if current
            else {
                "dimensions": [],
                "conditions": [],
                "consequences": [],
                "strategies": [],
            }
        )
        current_iter = (current[1] + 1) if current else 1

        new_incidents = s.execute(
            text(
                "SELECT s.texto, cs.confianza FROM codigos_segmento cs "
                "JOIN segmentos s ON cs.segmento_id = s.id "
                "WHERE cs.categoria_id = :cid ORDER BY cs.updated_at DESC LIMIT 10"
            ),
            {"cid": code_id},
        ).fetchall()

        if not new_incidents:
            return {"skipped": True, "reason": "sin nuevos incidentes"}

        code_def = s.execute(
            text("SELECT nombre, definicion FROM categorias WHERE id = :cid"),
            {"cid": code_id},
        ).fetchone()

        # Fetch object_of_study for paradigm context
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # Fetch operational_question for paradigm context (G26)
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")

        response = llm.run_agent(
            "fe_paradigm_integrator",
            variables={
                "current_paradigm": _json.dumps(current_state, ensure_ascii=False),
                "new_incidents": "\n---\n".join(r[0] for r in new_incidents[:5]),
                "code_name": code_def[0],
                "code_definition": code_def[1] or "",
                "object_of_study": object_of_study,
                "operational_question": operational_question or "",
            },
        )

        s.execute(
            text(
                "INSERT INTO paradigm_states (id, code_id, proyecto_id, iteration, "
                "did_state_expand, expansion_type, paradigm_snapshot, integration_memo) "
                "VALUES (gen_random_uuid(), :cid, :pid, :iter, :exp, :etype, :snap, :memo)"
            ),
            {
                "cid": code_id,
                "pid": proyecto_id,
                "iter": current_iter,
                "exp": response.get("did_state_expand", False),
                "etype": response.get("expansion_type", "NONE"),
                "snap": _json.dumps(response.get("new_paradigm", current_state)),
                "memo": response.get("integration_memo", ""),
            },
        )
        s.commit()

        return {
            "iteration": current_iter,
            "did_state_expand": response.get("did_state_expand", False),
            "expansion_type": response.get("expansion_type", "NONE"),
        }
    finally:
        s.close()


@app.task(name="a07_build_evidence_map")
def task_a07_build_evidence_map(proyecto_id: str) -> dict:
    """A7: Evidence Map. Cruza categorias x documentos programaticamente."""
    import random as _random

    s = SessionLocal()
    try:
        # Paso 1: evidence_map = {cat_name: {doc_name: {summary, segment_count}}}
        categories = s.execute(
            text("SELECT id, nombre FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()

        evidence_map = {}
        for cat_id, cat_name in categories:
            evidence = {}
            docs = s.execute(
                text("""
                SELECT DISTINCT d.id, d.original_filename
                FROM documentos d
                JOIN segmentos seg ON seg.documento_id = d.id
                JOIN codigos_segmento cs ON cs.segmento_id = seg.id
                WHERE cs.categoria_id = :cid AND d.proyecto_id = :pid
            """),
                {"cid": str(cat_id), "pid": proyecto_id},
            ).fetchall()

            for doc_id, doc_name in docs:
                segs = s.execute(
                    text(
                        "SELECT s.texto FROM codigos_segmento cs "
                        "JOIN segmentos s ON cs.segmento_id = s.id "
                        "WHERE cs.categoria_id = :cid AND s.documento_id = :did LIMIT 5"
                    ),
                    {"cid": str(cat_id), "did": str(doc_id)},
                ).fetchall()
                summary = (
                    " | ".join(r[0][:150] for r in segs) if segs else "(sin evidencia)"
                )
                evidence[doc_name] = {"summary": summary, "segment_count": len(segs)}

            evidence_map[cat_name] = evidence

        # Paso 2: Explosion vars x docs (si hay variables)
        cross_sections = []
        try:
            vars_rows = s.execute(
                text("SELECT * FROM variables WHERE proyecto_id = :pid"),
                {"pid": proyecto_id},
            ).fetchall()
        except Exception:
            vars_rows = []

        if vars_rows:
            for cat_name, cat_evidence in evidence_map.items():
                for var in vars_rows:
                    sampling = {}
                    var_cats = getattr(var, "categories", None)
                    if isinstance(var_cats, str):
                        import json

                        var_cats = json.loads(var_cats)
                    if not var_cats:
                        continue
                    for vc in var_cats:
                        label = vc.get("label", vc.get("value_code", ""))
                        matched = [
                            dn
                            for dn in cat_evidence
                            if dn.lower().find(label.lower()[:20]) >= 0
                        ]
                        if len(matched) > 5:
                            matched = _random.sample(matched, 5)
                        sampling[label] = matched
                    cross_sections.append(
                        {
                            "category": cat_name,
                            "variable_sections": sampling,
                        }
                    )

        return {
            "evidence_map": evidence_map,
            "cross_sections": cross_sections,
            "categories_processed": len(categories),
        }
    finally:
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# B23: Agentes huérfanos — A14 Main Concern, A15 Core Emergence, A16 Interchangeability
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="a14_find_main_concern")
def task_a14_main_concern(proyecto_id: str) -> dict:
    """A14: Core pattern detection. Usa main_concern_proposer.md."""
    s = SessionLocal()
    try:
        # F0.3.5: Leer object_of_study para parametrizar el tipo de patron
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # Fetch operational question and research question from Nemotron output
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")
        research_question = rq_data.get("question", "")  # the full question Q1+Q2

        codes = s.execute(
            text("SELECT nombre, definicion FROM categorias WHERE proyecto_id=:pid"),
            {"pid": proyecto_id},
        ).fetchall()
        memos = s.execute(
            text(
                "SELECT contenido FROM memos WHERE proyecto_id=:pid AND tipo IN ('HIPOTESIS','PROPIEDAD','RELACION')"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        all_codes = "\n".join(f"- {c[0]}: {c[1]}" for c in codes)
        all_memos = "\n---\n".join(m[0] for m in memos) if memos else "(sin memos)"

        # C06: Cargar core_patterns por documento
        prime_rows = s.execute(
            text(
                "SELECT dp.prime_mover, dp.prime_mover_confidence, "
                "d.original_filename "
                "FROM document_processes dp "
                "JOIN documentos d ON dp.documento_id = d.id "
                "WHERE dp.proyecto_id = :pid AND dp.prime_mover IS NOT NULL"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        core_patterns_text = (
            "\n".join(f"- {r[2]}: {r[0]} (confidence: {r[1]})" for r in prime_rows)
            if prime_rows
            else "(sin core patterns extraídos)"
        )

        response = llm.run_agent(
            "fc_main_concern_proposer",
            variables={
                "all_codes": all_codes,
                "all_memos": all_memos,
                "prime_movers_per_document": core_patterns_text,
                "researcher_feedback": "",
                "object_of_study": object_of_study,
                "research_question": research_question or "",
                "operational_question": operational_question or "(not yet generated)",
                "coding_style_instruction": _get_coding_style_instruction(
                    s, proyecto_id
                ),
                "processing_verb": processing_verb,
                "processing_gerund": processing_gerund,
            },
        )
        return {
            "candidates": response.get("candidates", []),
            "rationale": response.get("rationale", ""),
            "no_clear_concern": response.get("no_clear_concern", False),
        }
    finally:
        s.close()


@app.task(name="a15_core_emergence")
def task_a15_core_emergence(proyecto_id: str) -> dict:
    """A15: Identifica core category candidates desde el grafo de hipótesis.

    El sistema (SQL) selecciona el top 3 de categorías con más conexiones
    en el grafo de hipótesis. El PRO evalúa esos 3 candidatos cualitativamente.
    """
    s = SessionLocal()
    try:
        # ── SQL: Top 3 candidates by hypothesis connection count ──
        top_candidates = s.execute(
            text("""
            SELECT c.nombre, c.definicion,
                   COUNT(h.id) as hypothesis_connections
            FROM categorias c
            LEFT JOIN hypotheses h ON h.project_id = c.proyecto_id
                 AND (h.concern_labels @> to_jsonb(ARRAY[c.id::text])
                      OR h.text ILIKE '%' || c.nombre || '%')
            WHERE c.proyecto_id = :pid
            GROUP BY c.id, c.nombre, c.definicion
            HAVING COUNT(h.id) >= 1
            ORDER BY hypothesis_connections DESC
            LIMIT 3
        """),
            {"pid": proyecto_id},
        ).fetchall()

        if not top_candidates:
            return {
                "status": "insufficient",
                "reason": "No categories with ≥2 hypothesis connections",
            }

        top_candidates_str = "\n".join(
            f"- {r[0]}: {r[1]} ({r[2]} hypothesis connections)" for r in top_candidates
        )

        # ── Fetch context for the PRO ──
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")

        # Fetch confirmed concern from HITL decisions
        mc_row = s.execute(
            text(
                "SELECT proposal->>'core_concern' FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        confirmed_concern = mc_row[0] if mc_row and mc_row[0] else "(not yet confirmed)"

        # All categories summary
        all_cats = s.execute(
            text(
                "SELECT nombre, definicion, concern_label FROM categorias WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        categories_summary = "\n".join(
            f"- {c[0]}: {c[1]} [concern: {c[2] or 'none'}]" for c in all_cats
        )

        # Hypotheses summary
        hyps = s.execute(
            text("SELECT id, text, level FROM hypotheses WHERE project_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        hypotheses_summary = (
            "\n".join(f"[H{i + 1}] {h[1]} (level: {h[2]})" for i, h in enumerate(hyps))
            if hyps
            else "(no hypotheses yet)"
        )

        response = llm.run_agent(
            "fc_core_category_proposer",
            variables={
                "confirmed_concern": confirmed_concern,
                "top_candidates": top_candidates_str,
                "categories_summary": categories_summary,
                "hypotheses_summary": hypotheses_summary,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "",
            },
        )
        return {
            "core_candidates": response.get("core_category_candidates", []),
            "recommendation": response.get("recommendation", ""),
            "no_suitable_core": response.get("no_suitable_core", False),
            "top_candidates_sql": [r[0] for r in top_candidates],
        }
    finally:
        s.close()


@app.task(name="propose_core_categories")
def task_propose_core_categories(proyecto_id: str) -> dict:
    """Core Category Proposer: evalúa todas las categorías existentes contra
    los criterios CGT de categoría central.

    Se ejecuta después de que todas las pausas every-3-doc están resueltas
    y el usuario ha seleccionado exactamente UNA concern y UNA población.

    Guardrails (enforced in code):
        1. Exactly ONE confirmed concern must exist.
        2. All categories must have a concern_label assigned.

    Returns:
        dict con core_category_candidates (rankeados), recommendation,
        confirmed_concern, no_suitable_core, no_suitable_rationale.
    """
    return _propose_core_categories(proyecto_id)


@app.task(name="a16_test_interchangeability")
def task_a16_interchangeability(code_id: str, proyecto_id: str) -> dict:
    """A16: Prueba de intercambiabilidad de 3 incidentes del mismo código."""
    s = SessionLocal()
    try:
        code = s.execute(
            text("SELECT nombre, definicion FROM categorias WHERE id=:cid"),
            {"cid": code_id},
        ).fetchone()
        if not code:
            return {"error": "codigo no encontrado"}

        incidents = s.execute(
            text("""
            SELECT s.texto FROM codigos_segmento cs
            JOIN segmentos s ON cs.segmento_id = s.id
            WHERE cs.categoria_id = :cid
            ORDER BY cs.confianza DESC LIMIT 3
        """),
            {"cid": code_id},
        ).fetchall()

        inc_texts = [r[0] for r in incidents]
        while len(inc_texts) < 3:
            inc_texts.append("")

        response = llm.run_agent(
            "ff_interchangeability_tester",
            variables={
                "code_label": code[0],
                "code_definition": code[1] or "",
                "incident_1": inc_texts[0],
                "incident_2": inc_texts[1],
                "incident_3": inc_texts[2],
            },
        )
        return {
            "verdict": response.get("verdict", "INSUFICIENTES_INCIDENTES"),
            "rationale": response.get("rationale", ""),
            "suggested_action": response.get("suggested_action", ""),
        }
    finally:
        s.close()


@app.task(name="a04_group_constructs")
def task_a04_group_constructs(proyecto_id: str) -> dict:
    """A04: Agrupador. Toma codigos y los agrupa por interchangeability of indicators."""
    s = SessionLocal()
    try:
        # Fetch operational question and object of study
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        codes = s.execute(
            text(
                "SELECT id, nombre, definicion FROM categorias WHERE proyecto_id=:pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        constructs = []
        for i, (cid, name, defn) in enumerate(codes):
            indicators = s.execute(
                text(
                    "SELECT s.texto FROM codigos_segmento cs "
                    "JOIN segmentos s ON cs.segmento_id = s.id "
                    "WHERE cs.categoria_id = :cid ORDER BY cs.confianza DESC LIMIT 3"
                ),
                {"cid": str(cid)},
            ).fetchall()
            ind_text = (
                "\n -".join(r[0][:200] for r in indicators)
                if indicators
                else "(sin indicadores)"
            )
            constructs.append(
                f"{i + 1}. {name}: {defn}\nEmpirical indicators:\n -{ind_text}"
            )

        constructs_text = "\n\n".join(constructs)

        response = llm.run_agent(
            "ff_agrupador",
            variables={
                "constructs": constructs_text,
                "population_assumption": _get_population_assumption(s, proyecto_id),
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
                "coding_style_instruction": _get_coding_style_instruction(
                    s, proyecto_id
                ),
            },
        )

        groups_created = 0
        for group in response.get("summarized_constructs", []):
            content = (
                f"Constructo: {group.get('label', '')}\n"
                f"Definicion: {group.get('definition', '')}\n"
                f"Codigos agrupados: {group.get('summarized_ids', [])}\n"
                f"Inclusion: {group.get('theoretical_sampling_criteria', {}).get('inclusion', [])}\n"
                f"Exclusion: {group.get('theoretical_sampling_criteria', {}).get('exclusion', [])}"
            )
            s.execute(
                text(
                    "INSERT INTO memos (id, proyecto_id, autor_id, tipo, estado, contenido, es_confidencial) "
                    "VALUES (gen_random_uuid(), :pid, "
                    "(SELECT creador_id FROM proyectos WHERE id = :pid2 LIMIT 1), "
                    "'AGRUPACION', 'ABIERTO', :content, false)"
                ),
                {"pid": proyecto_id, "pid2": proyecto_id, "content": content},
            )
            groups_created += 1

        s.commit()
        return {"groups_created": groups_created}
    finally:
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# Selective Elaboration — dispatches per-code elaboration
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="trigger_selective_elaboration")
def trigger_selective_elaboration(proyecto_id: str) -> dict:
    """
    ⚠️ DEPRECATED — Usar selective_coding_coordinator en su lugar.

    Esta función viola R0.1 (sin HITL), R0.2 (ejecución paralela),
    y R0.3 (mezcla open/selective coding). Se mantiene por
    compatibilidad pero no debe usarse en nuevos flujos.
    """
    import warnings

    warnings.warn(
        "trigger_selective_elaboration is deprecated. "
        "Use selective_coding_coordinator instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    s = SessionLocal()
    try:
        # Obtener todas las categorias del proyecto
        codes = s.execute(
            text(
                "SELECT id, nombre, definicion FROM categorias WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if not codes:
            return {"status": "no_codes", "project_id": proyecto_id}

        elaborated = 0
        errors = 0
        for code_row in codes:
            code_id = str(code_row[0])
            try:
                # Para cada categoria, ejecutamos la integracion paradigmatica
                # que evalua si hay divergencia/expansion
                result = task_a01_integrate_paradigm(code_id, proyecto_id)
                if result and "error" not in result:
                    elaborated += 1
            except Exception as e:
                logger.warning("Elaboration failed for code %s: %s", code_id, e)
                errors += 1

        s.commit()
        return {
            "status": "completed",
            "project_id": proyecto_id,
            "codes_total": len(codes),
            "elaborated": elaborated,
            "errors": errors,
        }
    finally:
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# B21: LangGraph StateGraph — invocacion desde Celery
# ═══════════════════════════════════════════════════════════════════════


@app.task(
    name="invoke_graph",
    base=AbortableTask,
    bind=True,
)
def invoke_graph(self, proyecto_id: str, documento_id: str = None) -> dict:
    """
    B21: Invoca el StateGraph para un documento (o el proyecto completo).

    El grafo (workflow.py) orquesta los agentes como nodos.
    PostgresSaver checkpointea entre nodos para pausar/reanudar.
    Los agentes se llaman como funciones sincronas (no via Celery).

    Si documento_id es None, invoca la fase de sintesis (B).
    """
    try:
        import os as _os

        from app.core.workflow import AnalysisState, build_glaser_graph_reduced
        from config import DATABASE_URL as db_url
        from langgraph.checkpoint.postgres import PostgresSaver

        saver = PostgresSaver.from_conn_string(db_url)
        saver.setup()

        graph = build_glaser_graph_reduced()
        graph = graph.with_config(checkpointer=saver)

        config = {"configurable": {"thread_id": proyecto_id}}

        if documento_id:
            # Fase A: procesar un documento
            s = SessionLocal()
            try:
                doc = s.execute(
                    text("SELECT metadatos FROM documentos WHERE id = :did"),
                    {"did": documento_id},
                ).fetchone()
                meta = doc[0] or {} if doc else {}
                texto = meta.get("texto_preprocesado") or meta.get("texto_extraido", "")
            finally:
                s.close()

            state = AnalysisState(
                project_id=proyecto_id,
                document_id=documento_id,
                document_text=texto,
                study_status="collecting",
                current_wave=1,
            )
        else:
            # Fase B: sintesis cross-documento
            state = AnalysisState(
                project_id=proyecto_id,
                study_status="collecting",
                current_step="reduce_synthesize",
            )

        result = graph.invoke(state, config)

        return {
            "status": "completed",
            "current_step": result.get("current_step", ""),
            "core_concern": result.get("core_concern", ""),
            "hypotheses_count": len(result.get("candidate_hypotheses", [])),
        }
    except ImportError as e:
        logger.warning("LangGraph no disponible: %s", e)
        return {"status": "unavailable", "reason": str(e)}
    except Exception as e:
        logger.error("Graph invocation failed: %s", e)
        return {"status": "error", "reason": str(e)}


@app.task(name="seed_theoretical_codes")
def task_seed_theoretical_codes() -> dict:
    """T28: Seed de 12 codigos teoricos built-in. Idempotente."""
    import sys as _s

    _s.path.insert(0, "/app")
    from app.services.theory_seeder import seed_theoretical_codes
    from database import SessionLocal

    s = SessionLocal()
    try:
        inserted = seed_theoretical_codes(s)
        logger.info("T28: seeded %d theoretical codes", inserted)
        return {"status": "ok", "inserted": inserted}
    finally:
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# E2 — Selective Coding Coordinator + Pipeline Tasks
# ═══════════════════════════════════════════════════════════════════════


@app.task(
    name="selective_coding_coordinator",
    base=AbortableTask,
    bind=True,
)
def selective_coding_coordinator(self, proyecto_id: str) -> dict:
    """
    Coordinator del pipeline selectivo: Fase A → B → C → D → E.

    Despacha cada fase serialmente con gates HITL entre ellas.
    Cada fase espera confirmación del investigador antes de avanzar.

    Este coordinator reemplaza al antiguo trigger_selective_elaboration
    que ejecutaba tareas en paralelo sin HITL (violando R0.1, R0.2, R0.3).
    """
    if self._aborted:
        raise TaskCancelledError()

    s = SessionLocal()
    _set_language_from_project(s, proyecto_id)
    try:
        from agents.transitions import PROJECT_STATES, transition_project

        # ── Determinar punto de entrada ──
        current = s.execute(
            text("SELECT estado FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        if not current:
            return {"status": "error", "reason": "Project not found"}
        current_state = current[0]

        # ── Fase A: Core Category Detection ──
        if current_state == "coding":
            transition_project(s, proyecto_id, "coding", "finding_cc")
            current_state = "finding_cc"

        if current_state == "finding_cc":
            result_a = task_main_concern_pipeline(proyecto_id)
            if result_a.get("status") != "completed":
                return {"status": "paused", "phase": "A", "gate": "pattern_of_interest"}

            result_cc = task_core_emergence_pipeline(proyecto_id)
            if result_cc.get("status") == "paused":
                return {"status": "paused", "phase": "A", "gate": "core_category"}
            # insufficient / completed → continue

            transition_project(s, proyecto_id, "finding_cc", "reducing")
            current_state = "reducing"

        # ── Fase B: Selective Reduction ──
        if current_state == "reducing":
            result_b = task_selective_reduction_pipeline(proyecto_id)
            if result_b.get("status") != "completed":
                return {"status": "paused", "phase": "B", "gate": "selective_reduction"}

            transition_project(s, proyecto_id, "reducing", "saturating")
            current_state = "saturating"

        # ── Fase C: Core Saturation ──
        if current_state == "saturating":
            result_c = task_core_saturation_loop(proyecto_id)
            logger.info(
                "Fase C (saturation): %d categories processed, %d expansions",
                result_c.get("categories_processed", 0),
                result_c.get("total_expansions", 0),
            )
            if result_c.get("status") == "completed":
                transition_project(s, proyecto_id, "saturating", "building_db")
                current_state = "building_db"

        # ── Fase D: Database A/B ──
        if current_state == "building_db":
            result_da = task_database_a_pipeline(proyecto_id)
            if result_da.get("status") != "completed":
                return {"status": "paused", "phase": "D", "gate": "database_a"}

            result_db = task_database_b_pipeline(proyecto_id)
            if result_db.get("status") != "completed":
                return {"status": "paused", "phase": "D", "gate": "database_b"}

            # ── Fase E: Global Saturation Check ──
            result_e = task_global_saturation_check(proyecto_id)
            if result_e.get("status") != "completed":
                return {"status": "paused", "phase": "E", "gate": "global_saturation"}

            transition_project(s, proyecto_id, "building_db", "playground_ready")

            # ── Auto-trigger: preparar el Playground ──
            _prepare_playground_for_project(proyecto_id)

        return {
            "status": "completed",
            "project_id": proyecto_id,
            "final_state": "playground_ready",
        }

    except TaskCancelledError:
        return {"status": "cancelled", "proyecto_id": proyecto_id}
    except Exception:
        logger.exception("selective_coding_coordinator failed for %s", proyecto_id)
        raise
    finally:
        s.close()


@app.task(name="verify_core_pattern", base=AbortableTask, bind=True)
def task_verify_core_pattern(self, proyecto_id: str) -> dict:
    """F2.5: Verifica convergencia de patrones cada 3 docs (PRO)."""
    from pattern_verifier import verify_core_pattern as _impl

    return _impl(proyecto_id)


@app.task(name="f6b_memo_theoretical_tagger", base=AbortableTask, bind=True)
def task_memo_theoretical_tagger(self, memo_id: str, proyecto_id: str) -> dict:
    """F6b: Clasifica memo en 12 familias canónicas (FLASH)."""
    from theoretical import tag_memo_theoretically as _impl

    return _impl(memo_id, proyecto_id)


@app.task(name="final_report", base=AbortableTask, bind=True)
def task_final_report(self, proyecto_id: str) -> dict:
    """F6e: Genera reporte teórico final (PRO, nodo terminal)."""
    from reporter import generate_final_report as _impl

    return _impl(proyecto_id)


@app.task(
    name="main_concern_pipeline",
    base=AbortableTask,
)
def task_main_concern_pipeline(proyecto_id: str) -> dict:
    """
    Fase A, Pasos A1+A2: Main Concern Detection.
    Proposer (PRO) → Critic (PRO) → HITL gate.
    Llamado desde selective_coding_coordinator (directo) o via Celery.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "pattern_of_interest"}
        if existing and existing[0] == "pending":
            return {
                "status": "paused",
                "gate": "pattern_of_interest",
                "awaiting": "researcher",
            }

        # Si hay una decisión modified, obtener el feedback para re-ejecutar
        researcher_feedback = ""
        if existing and existing[0] == "modified":
            fb_row = s.execute(
                text(
                    "SELECT researcher_feedback FROM hitl_decisions "
                    "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                    "AND status = 'modified' ORDER BY creado_en DESC LIMIT 1"
                ),
                {"pid": proyecto_id},
            ).fetchone()
            researcher_feedback = (fb_row[0] or "") if fb_row else ""
            logger.info(
                "Re-executing core_concern with feedback: %s", researcher_feedback[:100]
            )

        # ── Proposer ──
        # F0.3.5: Leer object_of_study para parametrizar el tipo de patron
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # Fetch operational question and research question from Nemotron output
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")
        research_question = rq_data.get("question", "")
        processing_verb = (
            pa_data.get("processing_verb", "resolve")
            if isinstance(pa_data, dict)
            else "resolve"
        )
        processing_gerund = (
            pa_data.get("processing_gerund", "resolving")
            if isinstance(pa_data, dict)
            else "resolving"
        )

        codes = s.execute(
            text("SELECT nombre, definicion FROM categorias WHERE proyecto_id=:pid"),
            {"pid": proyecto_id},
        ).fetchall()
        memos = s.execute(
            text(
                "SELECT contenido FROM memos WHERE proyecto_id=:pid "
                "AND tipo IN ('HIPOTESIS','PROPIEDAD','RELACION')"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        prime_rows = s.execute(
            text(
                "SELECT dp.prime_mover, dp.prime_mover_confidence, d.original_filename "
                "FROM document_processes dp "
                "JOIN documentos d ON dp.documento_id = d.id "
                "WHERE dp.proyecto_id = :pid AND dp.prime_mover IS NOT NULL"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        all_codes = "\n".join(f"- {c[0]}: {c[1]}" for c in codes)
        all_memos = "\n---\n".join(m[0] for m in memos) if memos else "(sin memos)"
        prime_movers_text = (
            "\n".join(f"- {r[2]}: {r[0]} (confidence: {r[1]})" for r in prime_rows)
            if prime_rows
            else "(sin prime movers)"
        )

        proposal = llm.run_agent(
            "fc_main_concern_proposer",
            variables={
                "all_codes": all_codes,
                "all_memos": all_memos,
                "prime_movers_per_document": prime_movers_text,
                "researcher_feedback": researcher_feedback,
                "object_of_study": object_of_study,
                "research_question": research_question or "",
                "operational_question": operational_question or "(not yet generated)",
                "coding_style_instruction": _get_coding_style_instruction(
                    s, proyecto_id
                ),
                "processing_verb": processing_verb,
                "processing_gerund": processing_gerund,
            },
        )

        # ── Critic (feedback only, no verdicts) ──
        # Build structured context from proposer output for better LLM evaluation
        candidates_raw = proposal.get("candidates", [])
        candidates_context_parts = []
        for i, c in enumerate(candidates_raw):
            parts = [
                f"[CANDIDATE {i}]",
                f"statement: {c.get('statement', '')}",
                f"supporting_codes: {', '.join(c.get('supporting_codes', []))}",
                f"orphan_codes: {', '.join(c.get('orphan_codes', []))}",
                f"is_latent: {c.get('is_latent', False)}",
                f"rationale: {c.get('rationale', '')}",
            ]
            candidates_context_parts.append("\n".join(parts))
        candidates_context = "\n\n".join(candidates_context_parts)

        # Extract coding_style_key for label tokens in prompt
        coding_styles = pa_data.get("coding_styles", [])
        coding_style_key = (
            coding_styles[0]
            if isinstance(coding_styles, list) and coding_styles
            else "gerundio"
        )

        critic = llm.run_agent(
            "fc_main_concern_critic",
            variables={
                "candidates_context": candidates_context,
                "all_codes": all_codes,
                "all_memos": all_memos,
                "object_of_study": object_of_study,
                "research_question": research_question or "",
                "operational_question": operational_question or "",
                "researcher_feedback": researcher_feedback or "",
                "prime_movers_per_document": prime_movers_text,
                "processing_verb": processing_verb,
                "coding_style_key": coding_style_key,
            },
        )

        # ── HITL gate ──
        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "pattern_of_interest", proposal, critic)

        return {
            "status": "paused",
            "gate": "pattern_of_interest",
            "awaiting": "researcher",
        }

    except Exception:
        logger.exception("main_concern_pipeline failed for %s", proyecto_id)
        raise
    finally:
        s.close()


@app.task(
    name="core_emergence_pipeline",
    base=AbortableTask,
)
def task_core_emergence_pipeline(proyecto_id: str) -> dict:
    """
    Fase A, Pasos A3+A4: Core Category Emergence.

    SQL top-3 → Proposer (PRO) → Critic (FLASH) → HITL gate.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'core_category' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "core_category"}
        if existing and existing[0] == "pending":
            return {
                "status": "paused",
                "gate": "core_category",
                "awaiting": "researcher",
            }

        # ── SQL: Top 3 candidates by hypothesis connection count ──
        top_cats = s.execute(
            text("""
            SELECT c.id, c.nombre, c.definicion,
                   COUNT(h.id) as hypothesis_connections
            FROM categorias c
            LEFT JOIN hypotheses h ON h.project_id = c.proyecto_id
                 AND (h.concern_labels @> to_jsonb(ARRAY[c.id::text])
                      OR h.text ILIKE '%' || c.nombre || '%')
            WHERE c.proyecto_id = :pid
            GROUP BY c.id, c.nombre, c.definicion
            HAVING COUNT(h.id) >= 1
            ORDER BY hypothesis_connections DESC
            LIMIT 3
        """),
            {"pid": proyecto_id},
        ).fetchall()

        if not top_cats:
            return {
                "status": "insufficient",
                "reason": "No categories with ≥2 hypothesis connections",
            }

        top_candidates_str = "\n".join(
            f"- {r[1]}: {r[2]} ({r[3]} hypothesis connections)" for r in top_cats
        )

        # ── Fetch context ──
        oos_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = "concern"
        if oos_row and oos_row[0]:
            config = oos_row[0] if isinstance(oos_row[0], dict) else {}
            object_of_study = config.get("object_of_study", "concern")

        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")
        processing_verb = (
            pa_data.get("processing_verb", "resolve")
            if isinstance(pa_data, dict)
            else "resolve"
        )

        mc_row = s.execute(
            text(
                "SELECT proposal->>'core_concern' FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        confirmed_concern = mc_row[0] if mc_row and mc_row[0] else "(not yet confirmed)"

        all_cats = s.execute(
            text(
                "SELECT nombre, definicion, concern_label FROM categorias WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        categories_summary = "\n".join(
            f"- {c[0]}: {c[1]} [concern: {c[2] or 'none'}]" for c in all_cats
        )

        hyps = s.execute(
            text("SELECT id, text, level FROM hypotheses WHERE project_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        hypotheses_summary = (
            "\n".join(f"[H{i + 1}] {h[1]} (level: {h[2]})" for i, h in enumerate(hyps))
            if hyps
            else "(no hypotheses yet)"
        )

        # ── A3: Proposer (PRO) ──
        proposal = llm.run_agent(
            "fc_core_category_proposer",
            variables={
                "confirmed_concern": confirmed_concern,
                "top_candidates": top_candidates_str,
                "categories_summary": categories_summary,
                "hypotheses_summary": hypotheses_summary,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "",
            },
        )

        # ── A4: Critic (FLASH — interchangeability) ──
        candidates = proposal.get("core_category_candidates", [])

        # Build structured proposer context + fetch incidents from DIFFERENT docs
        proposer_context_parts = []
        incidents_context_parts = []
        used_docs = set()

        for cand_idx, cand in enumerate(candidates):
            cat_name = cand.get("category_label", "")

            # Proposer evaluation context
            proposer_parts = [
                f"[CANDIDATE {cand_idx}: {cat_name}]",
                f"is_central: {cand.get('is_central', False)}",
                f"has_explanatory_power: {cand.get('has_explanatory_power', False)}",
                f"has_theoretical_grab: {cand.get('has_theoretical_grab', False)}",
                f"connected_categories: {cand.get('connected_categories', [])}",
                f"key_hypothesis_refs: {cand.get('key_hypothesis_refs', [])}",
                f"proposer_rationale: {cand.get('centrality_rationale', '')}",
            ]
            proposer_context_parts.append("\n".join(proposer_parts))

            # Find category by name
            cat_row = s.execute(
                text(
                    "SELECT id FROM categorias WHERE nombre = :name AND proyecto_id = :pid"
                ),
                {"name": cat_name, "pid": proyecto_id},
            ).fetchone()
            if not cat_row:
                continue

            # Fetch 2-3 incidents from DIFFERENT documents for interchangeability testing
            incidents = s.execute(
                text(
                    "SELECT DISTINCT ON (s.documento_id) s.texto, d.original_filename "
                    "FROM codigos_segmento cs "
                    "JOIN segmentos s ON cs.segmento_id = s.id "
                    "JOIN documentos d ON s.documento_id = d.id "
                    "WHERE cs.categoria_id = :cid LIMIT 3"
                ),
                {"cid": str(cat_row[0])},
            ).fetchall()

            if incidents:
                inc_parts = [f"[INCIDENTS for {cat_name}]"]
                for inc in incidents:
                    doc_name = inc[1]
                    inc_parts.append(f"  DOC {doc_name}: {inc[0][:400]}")
                inc_parts.append(
                    "  → Are these incidents INTERCHANGEABLE? (valid | refine | split)"
                )
                incidents_context_parts.append("\n".join(inc_parts))

        proposer_context = "\n\n".join(proposer_context_parts)
        incidents_context = "\n\n".join(incidents_context_parts)

        # Real code statistics from codigos_segmento
        code_stats_rows = s.execute(
            text(
                "SELECT c.nombre, COUNT(DISTINCT cs.segmento_id) as seg_count, "
                "COUNT(DISTINCT s.documento_id) as doc_count "
                "FROM categorias c "
                "LEFT JOIN codigos_segmento cs ON c.id = cs.categoria_id "
                "LEFT JOIN segmentos s ON cs.segmento_id = s.id "
                "WHERE c.proyecto_id = :pid GROUP BY c.id, c.nombre ORDER BY seg_count DESC"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        code_statistics = "\n".join(
            f"- {r[0]}: {r[1]} segments in {r[2]} docs" for r in code_stats_rows
        )

        critic = llm.run_agent(
            "fc_core_emergence_critic",
            variables={
                "proposer_context": proposer_context,
                "incidents_context": incidents_context,
                "core_concern": confirmed_concern,
                "object_of_study": object_of_study,
                "all_codes": categories_summary,
                "code_statistics": code_statistics,
                "processing_verb": processing_verb,
            },
        )

        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "core_category", proposal, critic)

        return {"status": "paused", "gate": "core_category", "awaiting": "researcher"}

    except Exception:
        logger.exception("core_emergence_pipeline failed for %s", proyecto_id)
        raise
    finally:
        s.close()


@app.task(
    name="selective_reduction_pipeline",
    base=AbortableTask,
)
def task_selective_reduction_pipeline(proyecto_id: str) -> dict:
    """
    Fase B, Pasos B1+B2: Selective Reduction.
    Proposer (PRO) → Critic (PRO) → HITL gate.
    Llamado desde selective_coding_coordinator (directo) o via Celery.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'selective_reduction' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "selective_reduction"}
        if existing and existing[0] == "pending":
            return {
                "status": "paused",
                "gate": "selective_reduction",
                "awaiting": "researcher",
            }

        codes = s.execute(
            text(
                "SELECT id, nombre, definicion FROM categorias WHERE proyecto_id=:pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        all_codes = "\n".join(f"- {c[0]}: {c[1]}: {c[2]}" for c in codes)

        # Fetch object_of_study from project config
        oos_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = "concern"
        processing_verb = "resolve"
        if oos_row and oos_row[0]:
            config = oos_row[0] if isinstance(oos_row[0], dict) else {}
            object_of_study = config.get("object_of_study", "concern")
            processing_verb = config.get("processing_verb", "resolve")

        # Fetch confirmed core_concern from HITL decisions
        mc_row = s.execute(
            text(
                "SELECT proposal->>'core_concern' FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        core_concern = mc_row[0] if mc_row and mc_row[0] else "(not yet confirmed)"

        # Fetch accepted core_category from HITL decisions
        cc_row = s.execute(
            text(
                "SELECT proposal->>'core_category' FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'core_category' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        core_category = cc_row[0] if cc_row and cc_row[0] else "(not yet confirmed)"

        # Fetch existing categories
        existing_cats = s.execute(
            text(
                "SELECT id, nombre, definicion FROM categorias WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        existing_categories = (
            "\n".join(f"- {cat[1]}: {cat[2]}" for cat in existing_cats)
            if existing_cats
            else "(no existing categories yet)"
        )

        proposal = llm.run_agent(
            "fd_selective_reduction_proposer",
            variables={
                "core_concern": core_concern,
                "object_of_study": object_of_study,
                "core_category": core_category,
                "all_open_codes": all_codes,
                "existing_categories": existing_categories,
                "processing_verb": processing_verb,
            },
        )

        # ── Build structured context for critic ──
        reduced_codes = proposal.get("reduced_codes", [])
        discarded_codes = proposal.get("discarded_codes", [])

        # Normalize discarded codes for frontend (add code_name alias)
        for d in discarded_codes:
            if "code_name" not in d and "code_label" in d:
                d["code_name"] = d["code_label"]

        # Build structured text contexts instead of JSON blobs
        reduced_context = "CODES THAT SURVIVED REDUCTION:\n"
        for code in reduced_codes:
            source_ids = code.get("source_code_ids", [])
            is_fusion = len(source_ids) > 1
            prefix = "[FUSION]" if is_fusion else "[KEPT]"
            reduced_context += (
                f"  {prefix} {code.get('code_label', code.get('code_name', ''))}\n"
                f"    entity_type: {code.get('entity_type', '')}\n"
                f"    relation_to_core: {code.get('relation_to_core', '')}\n"
                f"    definition: {code.get('definition', '')[:200]}\n"
            )
            if is_fusion:
                reduced_context += f"    source_codes: {source_ids}\n"

        discarded_context = "CODES PROPOSED FOR DISCARD:\n"
        for code in discarded_codes:
            discarded_context += (
                f"  - {code.get('code_label', code.get('code_name', ''))}: "
                f"reason={code.get('discard_reason', '')}, "
                f"category={code.get('discard_category', '')}\n"
            )

        # Extract fusions from reduced_codes
        fusions = [c for c in reduced_codes if len(c.get("source_code_ids", [])) > 1]
        fusions_context = "PROPOSED FUSIONS:\n"
        for f in fusions:
            fusions_context += (
                f"  - {f.get('code_label', '')}: "
                f"sources={f.get('source_code_ids', [])}, "
                f"definition={f.get('definition', '')[:150]}\n"
            )

        critic = llm.run_agent(
            "fd_selective_reduction_critic",
            variables={
                "reduced_context": reduced_context,
                "discarded_context": discarded_context,
                "fusions_context": fusions_context,
                "all_open_codes": all_codes,
                "object_of_study": object_of_study,
                "core_concern": core_concern,
                "core_category": core_category,
                "existing_categories": existing_categories,
                "processing_verb": processing_verb,
            },
        )

        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "selective_reduction", proposal, critic)

        return {
            "status": "paused",
            "gate": "selective_reduction",
            "awaiting": "researcher",
        }

    except Exception:
        logger.exception("selective_reduction_pipeline failed for %s", proyecto_id)
        raise
    finally:
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# F4.2 — 4-Signal Saturation Panel helpers
# ═══════════════════════════════════════════════════════════════════════

# Default minimum properties target (used when not configured per-project)
_MIN_PROPS_TARGET = 15


def _compute_saturation_panel(session, code_id: str, proyecto_id: str) -> dict:
    """
    Computa las 4 señales de saturación para una categoría.

    Señal 1 — Matemática: rolling_std desde saturation_metrics.
    Señal 2 — Cualitativa: ventana deslizante de 5 paradigm_states.
    Señal 3 — Cobertura: propiedades documentadas en paradigm_snapshot.
    Señal 4 — Integración: conceptual_relationships vinculados.

    Devuelve el dict listo para saturation_panel_json.
    """
    from datetime import datetime, timezone

    panel = {
        "matematica": {"rolling_std": None, "status": "unknown"},
        "cualitativa": {"paradigm_window": [], "stable_since": 0, "status": "unknown"},
        "cobertura": {
            "propiedades_cubiertas": 0,
            "total_propiedades": _MIN_PROPS_TARGET,
            "pct": 0.0,
        },
        "integracion": {"relaciones_documentadas": 0, "suficiente": False},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── Señal 1: Matemática (rolling_std) ──
    math_row = session.execute(
        text(
            "SELECT rolling_std, saturation_status FROM saturation_metrics "
            "WHERE code_id = :cid"
        ),
        {"cid": code_id},
    ).fetchone()

    if math_row:
        rolling_std = float(math_row[0]) if math_row[0] is not None else None
        panel["matematica"]["rolling_std"] = (
            round(rolling_std, 4) if rolling_std is not None else None
        )
        # stable = rolling_std <= 0.3 (baja variabilidad)
        if rolling_std is not None and rolling_std <= 0.3:
            panel["matematica"]["status"] = "stable"
        elif rolling_std is not None:
            panel["matematica"]["status"] = "unstable"
        else:
            panel["matematica"]["status"] = "no_data"
    else:
        panel["matematica"]["status"] = "no_data"

    # ── Señal 2: Cualitativa (paradigm window) ──
    ps_rows = session.execute(
        text(
            "SELECT did_state_expand FROM paradigm_states "
            "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 5"
        ),
        {"cid": code_id},
    ).fetchall()

    paradigm_window = [bool(r[0]) for r in ps_rows]
    panel["cualitativa"]["paradigm_window"] = paradigm_window

    # Count consecutive False from the most recent
    stable_since = 0
    for expanded in paradigm_window:
        if not expanded:
            stable_since += 1
        else:
            break
    panel["cualitativa"]["stable_since"] = stable_since

    # stable = all last 5 are False (no expansion)
    if len(paradigm_window) >= 5 and all(not x for x in paradigm_window):
        panel["cualitativa"]["status"] = "stable"
    elif stable_since >= 3:
        panel["cualitativa"]["status"] = "approaching"
    else:
        panel["cualitativa"]["status"] = "unstable"

    # ── Señal 3: Cobertura (paradigm_snapshot properties) ──
    snap_row = session.execute(
        text(
            "SELECT paradigm_snapshot FROM paradigm_states "
            "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 1"
        ),
        {"cid": code_id},
    ).fetchone()

    props_covered = 0
    if snap_row and snap_row[0]:
        snap = snap_row[0] if isinstance(snap_row[0], dict) else {}
        for key in ("dimensions", "conditions", "consequences", "strategies"):
            arr = snap.get(key, [])
            if isinstance(arr, list):
                props_covered += len(arr)

    panel["cobertura"]["propiedades_cubiertas"] = props_covered
    # Use project config if available, else default
    config_row = session.execute(
        text("SELECT config_segmentacion FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    total_target = _MIN_PROPS_TARGET
    if config_row and config_row[0] and isinstance(config_row[0], dict):
        total_target = config_row[0].get("min_paradigm_properties", _MIN_PROPS_TARGET)
    panel["cobertura"]["total_propiedades"] = total_target
    panel["cobertura"]["pct"] = round(min(1.0, props_covered / max(1, total_target)), 3)

    # ── Señal 4: Integración (conceptual_relationships) ──
    rel_row = session.execute(
        text(
            "SELECT COUNT(*) FROM conceptual_relationships "
            "WHERE project_id = :pid "
            "AND category_ids @> to_jsonb(ARRAY[:cid])"
        ),
        {"pid": proyecto_id, "cid": code_id},
    ).fetchone()

    rel_count = int(rel_row[0]) if rel_row else 0
    panel["integracion"]["relaciones_documentadas"] = rel_count
    panel["integracion"]["suficiente"] = rel_count >= 1

    return panel


def _update_saturation_panel(session, code_id: str, panel: dict) -> None:
    """Actualiza categorias.saturation_panel_json con el panel calculado."""
    import json as _json

    session.execute(
        text("UPDATE categorias SET saturation_panel_json = :panel WHERE id = :cid"),
        {
            "panel": _json.dumps(panel, ensure_ascii=False),
            "cid": code_id,
        },
    )
    session.commit()


def _check_all_signals_stable(panel: dict) -> bool:
    """Devuelve True si las 4 señales sugieren saturación/estabilidad."""
    return (
        panel["matematica"]["status"] == "stable"
        and panel["cualitativa"]["status"] == "stable"
        and panel["cobertura"]["pct"] >= 0.8
        and panel["integracion"]["suficiente"] is True
    )


# ═══════════════════════════════════════════════════════════════════════


@app.task(
    name="core_saturation_loop",
    base=AbortableTask,
    bind=True,
)
def task_core_saturation_loop(self, proyecto_id: str) -> dict:
    """
    Fase C: Core Saturation Loop con Panel de 4 Señales (F4.2).

    Antes de cada llamada LLM (Proposer→Critic) se evalúan 4 señales
    de saturación para decidir si la categoría ya está saturada:

    1. Matemática (rolling_std) — SQL gratis
    2. Cualitativa (paradigm window 5) — SQL barato
    3. Cobertura (propiedades del paradigma) — JSONB parse
    4. Integración (conceptual_relationships) — SQL COUNT

    LLM solo se invoca cuando las 4 señales sugieren estabilidad.
    TheoSampler (F4.2.3) se activa si did_state_expand=False por 3
    iteraciones consecutivas Y cobertura < 80%.
    """
    if self._aborted:
        raise TaskCancelledError()

    s = SessionLocal()
    try:
        # ── Obtener categorías con score ≥ 4 ──
        cats = s.execute(
            text(
                "SELECT id, nombre, definicion, version, puntaje_relevancia "
                "FROM categorias "
                "WHERE proyecto_id = :pid AND COALESCE(puntaje_relevancia, 0) > 2 "
                "ORDER BY puntaje_relevancia DESC"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if not cats:
            logger.info("No categories with score ≥ 4 for project %s", proyecto_id)
            return {"status": "completed", "categories_processed": 0}

        # ── Obtener documentos ──
        docs = s.execute(
            text(
                "SELECT id, original_filename FROM documentos WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        # ── Obtener object_of_study del proyecto ──
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # ── Obtener operational_question (G24-G25) ──
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")

        processing_verb = (
            pa_data.get("processing_verb", "resolve")
            if isinstance(pa_data, dict)
            else "resolve"
        )
        processing_gerund = (
            pa_data.get("processing_gerund", "resolving")
            if isinstance(pa_data, dict)
            else "resolving"
        )

        results = {"project_id": proyecto_id, "categories": {}}
        total_expansions = 0
        theosampler_activations = 0
        theosampler_called_this_run = False  # rate-limit per loop run

        for cat_row in cats:
            cat_id = str(cat_row[0])
            cat_name = cat_row[1]
            cat_def = cat_row[2] or ""
            cat_version = cat_row[3] or 1
            cat_entity_type = "PROCESS"

            # ── F4.2: Compute 4-signal saturation panel ──
            panel = _compute_saturation_panel(s, cat_id, proyecto_id)
            _update_saturation_panel(s, cat_id, panel)

            logger.info(
                "Category %s panel: math=%s qual=%s cov=%.2f int=%s",
                cat_name,
                panel["matematica"]["status"],
                panel["cualitativa"]["status"],
                panel["cobertura"]["pct"],
                panel["integracion"]["suficiente"],
            )

            # ── F4.2: Decision gate ──
            # LLM (Proposer→Critic) solo se invoca cuando las 4 senales
            # sugieren estabilidad. Si alguna senal dice "inestable",
            # saltamos el LLM: la senal barata ya nos dice el estado.
            all_stable = _check_all_signals_stable(panel)
            consecutive_no_expand = panel["cualitativa"]["stable_since"]
            coverage_pct = panel["cobertura"]["pct"]

            # ── F4.2.3: TheoSampler activation ──
            # Trigger if: did_state_expand=False for 3+ consecutive AND coverage < 80%
            if (
                consecutive_no_expand >= 3
                and coverage_pct < 0.8
                and not theosampler_called_this_run
            ):
                logger.info(
                    "F4.2.3 TheoSampler: %s (stable=%d, coverage=%.2f)",
                    cat_name,
                    consecutive_no_expand,
                    coverage_pct,
                )
                try:
                    task_a06_theoretical_sample(proyecto_id)
                    theosampler_activations += 1
                    theosampler_called_this_run = True
                except Exception as e:
                    logger.warning("TheoSampler failed for %s: %s", cat_name, e)

            if not all_stable:
                # Signals say NOT saturated → skip expensive LLM
                logger.info(
                    "Category %s NOT saturated (math=%s qual=%s cov=%.2f int=%s) — skipping LLM",
                    cat_name,
                    panel["matematica"]["status"],
                    panel["cualitativa"]["status"],
                    coverage_pct,
                    panel["integracion"]["suficiente"],
                )
                results["categories"][cat_name] = {
                    "status": "processing",
                    "panel": panel,
                    "llm_skipped": True,
                }
                continue

            # All 4 signals suggest stability → invoke LLM for definitive confirmation
            logger.info(
                "Category %s: all 4 signals stable — invoking LLM confirmation",
                cat_name,
            )

            cat_results = {
                "iterations": 0,
                "expansions": 0,
                "status": "processing",
                "panel": panel,
            }
            no_expand_streak = consecutive_no_expand
            panel_iterations = 1

            for doc_row in docs:
                if self._aborted:
                    raise TaskCancelledError()

                doc_id = str(doc_row[0])
                doc_name = doc_row[1]

                # ── F4.2: Recompute panel before each doc iteration ──
                if panel_iterations > 1:
                    panel = _compute_saturation_panel(s, cat_id, proyecto_id)
                    _update_saturation_panel(s, cat_id, panel)

                panel_iterations += 1

                # If signals no longer stable → category destabilized, stop LLM calls
                if not _check_all_signals_stable(panel):
                    cat_results["panel"] = panel
                    cat_results["note"] = "signals_destabilized"
                    logger.info(
                        "Category %s: signals no longer stable, pausing LLM calls",
                        cat_name,
                    )
                    break

                # F4.2.3: TheoSampler re-check
                if (
                    panel["cualitativa"]["stable_since"] >= 3
                    and panel["cobertura"]["pct"] < 0.8
                    and not theosampler_called_this_run
                ):
                    try:
                        task_a06_theoretical_sample(proyecto_id)
                        theosampler_activations += 1
                        theosampler_called_this_run = True
                    except Exception as e:
                        logger.warning(
                            "TheoSampler re-activation failed for %s: %s", cat_name, e
                        )

                # Obtener un segmento/incidente para esta categoría+documento
                incident = s.execute(
                    text(
                        "SELECT s.texto FROM codigos_segmento cs "
                        "JOIN segmentos s ON cs.segmento_id = s.id "
                        "WHERE cs.categoria_id = :cid AND s.documento_id = :did "
                        "ORDER BY cs.confianza DESC LIMIT 1"
                    ),
                    {"cid": cat_id, "did": doc_id},
                ).fetchone()

                if not incident:
                    continue

                incident_text = incident[0][:5000]

                # ── C1: Proposer (PRO) ──
                proposal = llm.run_agent(
                    "fe_core_saturation_proposer",
                    variables={
                        "category_label": cat_name,
                        "category_definition": cat_def,
                        "category_id": cat_id,
                        "entity_type": cat_entity_type,
                        "current_paradigm_state": _get_paradigm_snapshot(s, cat_id),
                        "new_incidents": incident_text,
                        "document_name": doc_name,
                        "document_id": doc_id,
                        "object_of_study": object_of_study,
                        "operational_question": operational_question or "",
                        "processing_gerund": processing_gerund,
                    },
                )

                # ── C2: Critic (FLASH) ──
                critic = llm.run_agent(
                    "fe_core_saturation_critic",
                    variables={
                        "proposed_expansions": json.dumps(proposal),
                        "current_paradigm_state": _get_paradigm_snapshot(s, cat_id),
                        "new_incidents": incident_text,
                        "object_of_study": object_of_study,
                        "category_label": cat_name,
                        "category_definition": cat_def,
                        "operational_question": operational_question or "",
                        "processing_verb": processing_verb,
                    },
                    tier="FAST",
                )

                did_expand = proposal.get("did_state_expand", False)
                cat_results["iterations"] += 1

                if did_expand:
                    cat_results["expansions"] += 1
                    total_expansions += 1
                    no_expand_streak = 0

                    # Registrar en paradigm_states
                    _record_paradigm_state(
                        s,
                        cat_id,
                        proyecto_id,
                        did_expand=True,
                        etype=proposal.get("elaboration_type", "expanded"),
                        snapshot=proposal,
                        memo=proposal.get("elaboration_note", ""),
                    )

                    # Actualizar definición si se expandió
                    expanded_def = proposal.get("expanded_definition", "")
                    if expanded_def:
                        s.execute(
                            text(
                                "UPDATE categorias SET definicion = :def, "
                                "version = version + 1 WHERE id = :cid"
                            ),
                            {"def": expanded_def, "cid": cat_id},
                        )
                        s.commit()
                        cat_def = expanded_def
                        cat_version += 1
                else:
                    no_expand_streak += 1
                    _record_paradigm_state(
                        s,
                        cat_id,
                        proyecto_id,
                        did_expand=False,
                        etype="converges",
                        snapshot=proposal,
                        memo="",
                    )

                # Traditional saturation criterion (fallback)
                if no_expand_streak >= 3:
                    cat_results["status"] = "saturated"
                    cat_results["iterations_without_expansion"] = no_expand_streak
                    logger.info(
                        "Category %s saturated after %d iterations without expansion",
                        cat_name,
                        no_expand_streak,
                    )
                    break

            # Final panel update for this category
            panel = _compute_saturation_panel(s, cat_id, proyecto_id)
            _update_saturation_panel(s, cat_id, panel)
            if cat_results.get("status") == "saturated":
                cat_results["panel"] = panel
            results["categories"][cat_name] = cat_results

        # ── HITL gate si hay categorías saturadas ──
        saturated_count = sum(
            1 for c in results["categories"].values() if c.get("status") == "saturated"
        )
        if saturated_count > 0:
            from agents.transitions import hitl_gate

            hitl_gate(
                s,
                proyecto_id,
                "core_saturation",
                {"saturated_categories": saturated_count, "results": results},
                {
                    "verdict": "SAT",
                    "rationale": f"{saturated_count} categories saturated",
                },
            )

        return {
            "status": "completed",
            "categories_processed": len(cats),
            "total_expansions": total_expansions,
            "theosampler_activations": theosampler_activations,
            "results": results,
        }

    except TaskCancelledError:
        return {"status": "cancelled", "proyecto_id": proyecto_id}
    except Exception:
        logger.exception("core_saturation_loop failed for %s", proyecto_id)
        raise
    finally:
        s.close()


def _get_paradigm_snapshot(session, code_id: str) -> str:
    """Obtiene el paradigm_state actual de una categoría como string JSON."""
    import json as _json

    row = session.execute(
        text(
            "SELECT paradigm_snapshot FROM paradigm_states "
            "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 1"
        ),
        {"cid": code_id},
    ).fetchone()
    if row and row[0]:
        return (
            _json.dumps(row[0], ensure_ascii=False)
            if isinstance(row[0], dict)
            else str(row[0])
        )
    return "(sin propiedades documentadas)"


def _record_paradigm_state(
    session,
    code_id: str,
    proyecto_id: str,
    did_expand: bool,
    etype: str,
    snapshot: dict,
    memo: str,
) -> None:
    """Registra una iteración en paradigm_states."""
    import json as _json

    current_iter = session.execute(
        text(
            "SELECT COALESCE(MAX(iteration), 0) FROM paradigm_states WHERE code_id = :cid"
        ),
        {"cid": code_id},
    ).fetchone()[0]

    session.execute(
        text(
            "INSERT INTO paradigm_states "
            "(id, code_id, proyecto_id, iteration, did_state_expand, "
            "expansion_type, paradigm_snapshot, integration_memo) "
            "VALUES (gen_random_uuid(), :cid, :pid, :iter, :exp, :etype, :snap, :memo)"
        ),
        {
            "cid": code_id,
            "pid": proyecto_id,
            "iter": current_iter + 1,
            "exp": did_expand,
            "etype": etype,
            "snap": _json.dumps(snapshot, ensure_ascii=False),
            "memo": memo,
        },
    )
    session.commit()


@app.task(name="database_a_pipeline")
def task_database_a_pipeline(proyecto_id: str) -> dict:
    """
    Fase D1+D2: Database A — Nodes planos con entity_type.
    Proposer (PRO) → Critic (PRO) → HITL gate.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'database_a' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "database_a"}
        if existing and existing[0] == "pending":
            return {"status": "paused", "gate": "database_a", "awaiting": "researcher"}

        # Obtener categorías saturadas
        cats = s.execute(
            text(
                "SELECT id, nombre, definicion, puntaje_relevancia "
                "FROM categorias WHERE proyecto_id = :pid "
                "AND COALESCE(puntaje_relevancia, 0) > 2 "
                "ORDER BY puntaje_relevancia DESC"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        saturated_cats = "\n".join(f"- [{c[3]}] {c[1]}: {c[2]}" for c in cats)

        # Fetch object_of_study from proyectos
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # Fetch research_question from population_assumption JSONB
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        research_question = rq_data.get("question", "")
        processing_verb = (
            pa_data.get("processing_verb", "resolve")
            if isinstance(pa_data, dict)
            else "resolve"
        )
        processing_gerund = (
            pa_data.get("processing_gerund", "resolving")
            if isinstance(pa_data, dict)
            else "resolving"
        )

        # Fetch core_category from accepted core_emergence HITL decision
        cc_row = s.execute(
            text(
                "SELECT proposal FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'core_category' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        cc_data = cc_row[0] if cc_row else {}
        core_candidates = (
            cc_data.get("core_category_candidates", [])
            if isinstance(cc_data, dict)
            else []
        )
        core_category = (
            core_candidates[0].get("name", "")
            if core_candidates
            else "(pending core_emergence HITL)"
        )

        proposal = llm.run_agent(
            "ff_database_a_proposer",
            variables={
                "saturated_categories": saturated_cats,
                "core_category": core_category,
                "object_of_study": object_of_study,
                "research_question": research_question or "",
                "processing_verb": processing_verb,
                "processing_gerund": processing_gerund,
            },
        )

        critic = llm.run_agent(
            "ff_database_a_critic",
            variables={
                "nodes": proposal.get("nodes", []),
                "saturated_categories": saturated_cats,
                "object_of_study": object_of_study,
                "core_category": core_category,
                "research_question": research_question or "",
                "processing_verb": processing_verb,
                "processing_gerund": processing_gerund,
            },
        )

        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "database_a", proposal, critic)

        # ── F5.1: Siempre persistir (HITL decide), no solo si SAT ──
        nodes = proposal.get("nodes", [])
        for node in nodes:
            s.execute(
                text(
                    "INSERT INTO database_nodes "
                    "(id, project_id, category_id, label, entity_type, definition, is_core) "
                    "VALUES (gen_random_uuid(), :pid, :cid, :label, :etype, :def, :core) "
                    "ON CONFLICT DO NOTHING"
                ),
                {
                    "pid": proyecto_id,
                    "cid": node.get("category_id"),
                    "label": node.get("label", ""),
                    "etype": node.get("entity_type", "PROCESS"),
                    "def": node.get("definition", ""),
                    "core": node.get("is_core", False),
                },
            )
        s.commit()
        logger.info(
            "Persisted %d database nodes for project %s (critic: %s)",
            len(nodes),
            proyecto_id,
            critic.get("verdict", "?"),
        )

        return {"status": "paused", "gate": "database_a", "awaiting": "researcher"}

    except Exception:
        logger.exception("database_a_pipeline failed for %s", proyecto_id)
        raise
    finally:
        s.close()


@app.task(name="database_b_pipeline")
def task_database_b_pipeline(proyecto_id: str) -> dict:
    """
    Fase D3+D4: Database B — Edges con relationship_type.
    Proposer (PRO) → Critic (PRO) → HITL gate.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'database_b' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "database_b"}
        if existing and existing[0] == "pending":
            return {"status": "paused", "gate": "database_b", "awaiting": "researcher"}

        # Obtener nodos (de database_a aceptada)
        nodes_row = s.execute(
            text(
                "SELECT proposal FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'database_a' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        nodes = nodes_row[0] if nodes_row else {}
        nodes_text = str(nodes)

        # Relaciones conceptuales
        rels = s.execute(
            text(
                "SELECT cr.category_ids, cr.elaboration_status, "
                "cr.converging_doc_count, tc.name "
                "FROM conceptual_relationships cr "
                "JOIN theoretical_codes tc ON cr.theoretical_code_id = tc.id "
                "WHERE cr.project_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        rels_text = "\n".join(
            f"- {r[3]}: {r[0]} (status={r[1]}, docs={r[2]})" for r in rels
        )

        # Hipótesis confirmadas
        hyps = s.execute(
            text(
                "SELECT text, level FROM hypotheses "
                "WHERE project_id = :pid AND status = 'accepted'"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        hyps_text = (
            "\n".join(f"- [{r[1]}] {r[0]}" for r in hyps)
            if hyps
            else "(sin hipótesis confirmadas)"
        )

        # Fetch object_of_study from proyectos
        oos_row = s.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

        # Fetch research_question from population_assumption JSONB
        pa_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        research_question = rq_data.get("question", "")
        processing_verb = (
            pa_data.get("processing_verb", "resolve")
            if isinstance(pa_data, dict)
            else "resolve"
        )

        # Fetch core_concern from accepted HITL decision
        mc_row = s.execute(
            text(
                "SELECT proposal->>'core_concern' FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'pattern_of_interest' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        core_concern = mc_row[0] if mc_row and mc_row[0] else "(not yet confirmed)"

        proposal = llm.run_agent(
            "ff_database_b_proposer",
            variables={
                "nodes": nodes_text,
                "conceptual_relationships": rels_text,
                "hypotheses": hyps_text,
                "object_of_study": object_of_study,
                "research_question": research_question or "",
                "core_concern": core_concern,
                "processing_verb": processing_verb,
            },
        )

        # ── Build structured edges context ──
        edges_raw = proposal.get("edges", [])
        edges_context_parts = []
        for i, edge in enumerate(edges_raw):
            evidence = edge.get("evidence", {})
            if isinstance(evidence, dict):
                ev_str = (
                    f"source={evidence.get('source_id', '')} "
                    f"({evidence.get('source_type', '')}): "
                    f"{evidence.get('summary', '')} "
                    f"[quality: {evidence.get('quality', '')}]"
                )
            else:
                ev_str = str(evidence)
            edge_parts = [
                f"[EDGE {i}]",
                f"source: {edge.get('source', '')}",
                f"target: {edge.get('target', '')}",
                f"description: {edge.get('description', '')}",
                f"rationale: {edge.get('rationale', '')}",
                f"evidence: {ev_str}",
                f"evidence_quality: {edge.get('evidence_quality', '')}",
            ]
            edges_context_parts.append("\n".join(edge_parts))
        edges_context = "\n\n".join(edges_context_parts)

        critic = llm.run_agent(
            "ff_database_b_critic",
            variables={
                "edges_context": edges_context,
                "nodes": nodes_text,
                "hypotheses": hyps_text,
                "object_of_study": object_of_study,
                "core_concern": core_concern,
                "research_question": research_question or "",
                "conceptual_relationships": rels_text,
                "processing_verb": processing_verb,
            },
        )

        from agents.transitions import hitl_gate

        # ── Deterministic quality gate: edge coverage ──
        edges = proposal.get("edges", [])
        connected_nodes = set()
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if src:
                connected_nodes.add(src)
            if tgt:
                connected_nodes.add(tgt)
        node_count_row = s.execute(
            text("SELECT COUNT(*) FROM database_nodes WHERE project_id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        total_nodes = node_count_row[0] if node_count_row else 0
        coverage_pct = (
            (len(connected_nodes) / total_nodes * 100) if total_nodes > 0 else 100
        )
        proposal["_coverage"] = {
            "connected_nodes": len(connected_nodes),
            "total_nodes": total_nodes,
            "coverage_pct": round(coverage_pct, 1),
            "sufficient": coverage_pct >= 50,
        }
        if coverage_pct < 50:
            logger.warning(
                "Database B: low coverage %d/%d (%.1f%%)",
                len(connected_nodes),
                total_nodes,
                coverage_pct,
            )
            if isinstance(critic, dict):
                ov = critic.get("overall_verdict", {})
                if isinstance(ov, dict) and ov.get("is_sound") is True:
                    ov["is_sound"] = False
                    ov["coverage_issue"] = (
                        f"Only {len(connected_nodes)}/{total_nodes} nodes ({coverage_pct:.0f}%) connected. Min 50% required."
                    )
                    critic["overall_verdict"] = ov
        else:
            logger.info(
                "Database B: coverage OK %d/%d (%.1f%%)",
                len(connected_nodes),
                total_nodes,
                coverage_pct,
            )

        hitl_gate(s, proyecto_id, "database_b", proposal, critic)

        # ── F5.1: Siempre persistir (HITL decide), no solo si SAT ──
        edges = proposal.get("edges", [])
        # Mapa label→id para resolver source/target
        node_map = {}
        node_rows = s.execute(
            text("SELECT id, label FROM database_nodes WHERE project_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        for nr in node_rows:
            node_map[str(nr[1])] = str(nr[0])

        persisted = 0
        for edge in edges:
            src_id = node_map.get(edge.get("source", ""))
            tgt_id = node_map.get(edge.get("target", ""))
            if src_id and tgt_id:
                evidence_obj = edge.get("evidence", {})
                evidence_json = (
                    json.dumps(evidence_obj, ensure_ascii=False)
                    if isinstance(evidence_obj, dict)
                    else str(evidence_obj)
                )
                s.execute(
                    text(
                        "INSERT INTO database_edges "
                        "(id, project_id, source_node_id, target_node_id, "
                        "relationship_type, evidence) "
                        "VALUES (gen_random_uuid(), :pid, :src, :tgt, :rtype, :ev) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "pid": proyecto_id,
                        "src": src_id,
                        "tgt": tgt_id,
                        "rtype": edge.get("relationship_type", "CO_OCCURS_WITH"),
                        "ev": evidence_json,
                    },
                )
                persisted += 1
        s.commit()
        logger.info(
            "Persisted %d/%d database edges for project %s (critic: %s)",
            persisted,
            len(edges),
            proyecto_id,
            str(critic.get("overall_verdict", {}).get("is_sound", "?"))
            if isinstance(critic, dict)
            else "?",
        )

        return {"status": "paused", "gate": "database_b", "awaiting": "researcher"}

    except Exception:
        logger.exception("database_b_pipeline failed for %s", proyecto_id)
        raise
    finally:
        s.close()


@app.task(name="global_saturation_check")
def task_global_saturation_check(proyecto_id: str) -> dict:
    """
    Fase E: Global Saturation Check.

    Verifica 3 condiciones:
    1. Todas las categorías con score ≥ 4 están saturadas
    2. Relaciones inter-categoriales saturadas
    3. Buffer de residuos revisado
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'global_saturation' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "global_saturation"}

        # Condición 1: categorías saturadas
        cats = s.execute(
            text(
                "SELECT id, nombre FROM categorias "
                "WHERE proyecto_id = :pid AND COALESCE(puntaje_relevancia, 0) >= 4"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        saturated = 0
        unsaturated = []
        for cat in cats:
            no_expand = s.execute(
                text(
                    "SELECT COUNT(*) FROM ("
                    "SELECT did_state_expand FROM paradigm_states "
                    "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 3"
                    ") sub WHERE did_state_expand = false"
                ),
                {"cid": str(cat[0])},
            ).fetchone()[0]
            if no_expand >= 3:
                saturated += 1
            else:
                unsaturated.append(cat[1])

        # Condición 2: relaciones inter-categoriales
        rel_count = s.execute(
            text(
                "SELECT COUNT(*) FROM conceptual_relationships WHERE project_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        # Condición 3: buffer de residuos (memos sin procesar)
        orphan_memos = s.execute(
            text(
                "SELECT COUNT(*) FROM memos "
                "WHERE proyecto_id = :pid AND tipo = 'HIPOTESIS' "
                "AND id NOT IN (SELECT COALESCE(memo_id, '00000000-0000-0000-0000-000000000000') FROM elaboration_memos WHERE project_id = :pid2)"
            ),
            {"pid": proyecto_id, "pid2": proyecto_id},
        ).fetchone()[0]

        proposal = {
            "condition_1_saturated_categories": f"{saturated}/{len(cats)}",
            "condition_1_unsaturated": unsaturated,
            "condition_2_relationships": rel_count,
            "condition_3_orphan_memos": orphan_memos,
            "all_conditions_met": saturated == len(cats)
            and rel_count > 0
            and orphan_memos == 0,
        }

        from agents.transitions import hitl_gate

        hitl_gate(
            s,
            proyecto_id,
            "global_saturation",
            proposal,
            {
                "verdict": "SAT" if proposal["all_conditions_met"] else "MOD",
                "rationale": (
                    "All saturation conditions met"
                    if proposal["all_conditions_met"]
                    else f"{len(unsaturated)} categories still unsaturated, "
                    f"{orphan_memos} orphan memos remaining"
                ),
            },
        )

        return {
            "status": "completed" if proposal["all_conditions_met"] else "paused",
            "gate": "global_saturation",
            "checks": proposal,
        }

    except Exception:
        logger.exception("global_saturation_check failed for %s", proyecto_id)
        raise
    finally:
        s.close()
