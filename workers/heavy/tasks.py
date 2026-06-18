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

from algorithmic_checks import check_output_references, preclassify_glaser
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

        # Validate: don't save empty outputs
        sd = (response.get("surprising_details") or "").strip()
        lp = (response.get("language_patterns") or "").strip()
        dpc = (response.get("data_production_context") or "").strip()
        all_empty = not sd and not lp and not dpc
        all_no_evidence = all("Sin evidencia" in v for v in [sd, lp, dpc] if v)
        if all_empty or all_no_evidence:
            logger.warning(
                "A1: empty/invalid response for doc=%s — marking as error", documento_id
            )
            return {"error": "empty_llm_response", "documento_id": documento_id}

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
            "Identifica el proceso central que este entrevistado intenta resolver\n"
            "continuamente. Nómbralo con un gerundio y explica en 2-3 oraciones\n"
            "qué acciones concretas en los segmentos revelan este proceso.\n"
            "No busques lo que el entrevistado dice explícitamente que le preocupa.\n"
            "Busca el patrón de comportamiento que subyace a sus acciones.\n"
            "Para similarity_to_previous y difference_from_previous, responde 'N/A'."
            if is_first
            else "[TAREA]\n"
            "1. Identifica el proceso central de ESTE entrevistado (gerundio + 2-3 oraciones).\n"
            "2. ¿En qué se PARECE al proceso del entrevistado anterior?\n"
            "   ¿Es el mismo proceso con distinta manifestación?\n"
            "3. ¿En qué se DIFERENCIA ESENCIALMENTE?\n"
            "   No detalles superficiales sino diferencias en el patrón de comportamiento."
        )

        # Pattern 4: pre-clasificar tipo de dato Glaser
        glaser_hint = preclassify_glaser(segments_text)
        task_section_with_hint = task_section + (
            "\n\n[PISTA — el sistema detectó estas señales textuales]\n"
            f"Señales encontradas: {glaser_hint['signals_found']}\n"
            f"Clasificación sugerida: {glaser_hint['suggested_type']} (confianza: {glaser_hint['confidence']:.0%})\n"
            "Puedes confirmar esta clasificación o corregirla si tu análisis difiere."
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
            logger.warning("A2: empty process_description for doc=%s", documento_id)
            return {"error": "empty_llm_response", "documento_id": documento_id}

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


def _classify_glaser_types_for_doc(
    session, documento_id: str, use_llm_fallback: bool = False
) -> int:
    """F2.1: Clasifica todos los segmentos de un documento con preclassify_glaser.

    Layer 1 (algorithmic) siempre corre. Layer 2 (FLASH) solo si
    use_llm_fallback=True y la confianza algorítmica es < 0.7.

    Persiste el resultado en segmentos.tipo_dato_glaser.

    Returns:
        Número de segmentos clasificados.
    """
    segments = session.execute(
        text(
            "SELECT id, texto FROM segmentos "
            "WHERE documento_id = :did ORDER BY posicion"
        ),
        {"did": documento_id},
    ).fetchall()

    if not segments:
        return 0

    classified = 0
    for seg_id, seg_text in segments:
        result = preclassify_glaser(
            seg_text,
            use_llm_fallback=use_llm_fallback,
            llm_client=llm if use_llm_fallback else None,
        )
        glaser_type = result.get("glaser_data_type")
        if glaser_type:
            session.execute(
                text("UPDATE segmentos SET tipo_dato_glaser = :tipo WHERE id = :sid"),
                {"tipo": glaser_type, "sid": str(seg_id)},
            )
            classified += 1

    session.commit()
    logger.info(
        "Glaser pre-classification: %d/%d segments classified (doc=%s)",
        classified,
        len(segments),
        documento_id,
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

        # ── Step 0.5: F2.2 — Extract incidents per baseline segment (FLASH) ──
        STEP = "extract_incidents"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("F2.2: Extrayendo incidentes doc %s", documento_id)
            try:
                from incident_extractor import extract_incident as _extract_inc

                baseline_segs = session.execute(
                    text(
                        "SELECT id FROM segmentos WHERE documento_id = :did "
                        "AND (tipo_dato_glaser = 'baseline_data' OR tipo_dato_glaser IS NULL)"
                    ),
                    {"did": documento_id},
                ).fetchall()
                n = 0
                for (sid,) in baseline_segs:
                    if self._aborted:
                        raise TaskCancelledError()
                    try:
                        _extract_inc(str(sid), proyecto_id)
                        n += 1
                    except Exception as e:
                        logger.warning(
                            "Incident extraction failed for seg %s: %s", sid, e
                        )
                results["incidents_extracted"] = n
                logger.info("F2.2: %d incidentes extraidos doc %s", n, documento_id)
            except Exception as e:
                logger.warning("Incident extraction batch failed: %s", e)
                results["incidents_extracted"] = 0
            checkpoint(session, documento_id, STEP, "completed")

        # ── Step 0.6: F2.4 — Extract core pattern per document (PRO) ──
        STEP = "extract_core_pattern"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed and results.get("incidents_extracted", 0) > 0:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("F2.4: Extrayendo patron central doc %s", documento_id)
            try:
                from pattern_extractor import extract_core_pattern as _extract_cp

                cp_result = _extract_cp(documento_id, proyecto_id)
                results["core_pattern"] = cp_result
                logger.info("F2.4: Patron central extraido doc %s", documento_id)
            except Exception as e:
                logger.warning("Core pattern extraction failed: %s", e)
                results["core_pattern"] = None
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
            if "error" in results["population_context"]:
                transit(
                    session,
                    documento_id,
                    proyecto_id,
                    "procesando",
                    "process_document_agents_a",
                    False,
                )
                return results

        # ── Step 2: A2 — Process Identification ──
        STEP = "a2_identify_process"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("A2: Proceso doc %s", documento_id)
            results["document_process"] = a2_identify_process(documento_id, proyecto_id)
            checkpoint(session, documento_id, STEP, "completed")
            if "error" in results["document_process"]:
                transit(
                    session,
                    documento_id,
                    proyecto_id,
                    "procesando",
                    "process_document_agents_a",
                    False,
                )
                return results

        # ── Step 3: C06 — Prime Mover ──
        STEP = "extract_prime_mover"
        if self._aborted:
            raise TaskCancelledError()
        if STEP not in completed:
            checkpoint(session, documento_id, STEP, "in_progress")
            logger.info("C06: Prime mover doc %s", documento_id)
            try:
                pm_result = _extract_prime_mover(session, documento_id, proyecto_id)
                results["prime_mover"] = pm_result
                if pm_result and pm_result.get("prime_mover"):
                    session.execute(
                        text(
                            "UPDATE document_processes SET prime_mover = :pm, "
                            "prime_mover_confidence = :pmc "
                            "WHERE documento_id = :did AND proyecto_id = :pid"
                        ),
                        {
                            "pm": pm_result["prime_mover"],
                            "pmc": pm_result.get("confidence", "LOW"),
                            "did": documento_id,
                            "pid": proyecto_id,
                        },
                    )
                    session.commit()
            except Exception as e:
                logger.warning("Prime mover extraction fallo: %s", e)
                results["prime_mover"] = None
            checkpoint(session, documento_id, STEP, "completed")

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
)

# ── New F2.3 agent imports ──
from comparator import b1_compare_incidents
from label_critic import b3_critique_labels
from labeler import b2_label_groups

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
    return b1_compare_incidents(proyecto_id, incremental)


@app.task(name="b2_label_groups")
def task_b2_label_groups(proyecto_id: str) -> dict:
    return b2_label_groups(proyecto_id)


@app.task(name="b3_critique_labels")
def task_b3_critique_labels(groups_json: str, labels_json: str) -> dict:
    return b3_critique_labels(groups_json, labels_json)


# ═══════════════════════════════════════════════════════════════════════
# F2.2 / F2.4 — Incident Extractor + Core Pattern Extractor
# ═══════════════════════════════════════════════════════════════════════

from incident_extractor import extract_incident as _extract_incident_impl
from pattern_extractor import extract_core_pattern as _extract_core_pattern_impl


@app.task(name="extract_incident")
def task_extract_incident(segment_id: str, proyecto_id: str) -> dict:
    """F2.2: Extrae un incidente por segmento con las 4 preguntas de Glaser (FLASH)."""
    return _extract_incident_impl(segment_id, proyecto_id)


@app.task(name="extract_core_pattern")
def task_extract_core_pattern(documento_id: str, proyecto_id: str) -> dict:
    """F2.4: Sintetiza el patrón central de un documento a partir de sus incidentes (PRO)."""
    return _extract_core_pattern_impl(documento_id, proyecto_id)


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
def task_literature_critic(comparison_table: dict) -> dict:
    """F5.4: Evalúa si el diálogo con literatura fuerza coincidencias o trata la literatura como autoridad (PRO)."""
    return _critique_literature_impl(comparison_table)


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
def task_applicability_critic(directrices: dict) -> dict:
    """F5.5: Evalúa si las directrices de aplicabilidad son genuinas, accesibles y modificables (PRO)."""
    return _critique_applicability_impl(directrices)


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
      7. Transition all docs: listo → sintetizado
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

        # ── F2.3 B1: Incident Comparator (PRO, 1-pass) ──
        if self._aborted:
            raise TaskCancelledError()
        _checkpoint_step(s, proyecto_id, "b1_compare_incidents", "in_progress")
        logger.info("B1: Comparando incidentes %s", proyecto_id)
        results["comparator"] = b1_compare_incidents(proyecto_id)
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
                "VALUES (gen_random_uuid(), NULL, :step, :status, '{}'::jsonb)"
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

        response = llm.run_agent(
            "fe_paradigm_integrator",
            variables={
                "current_paradigm": _json.dumps(current_state, ensure_ascii=False),
                "new_incidents": "\n---\n".join(r[0] for r in new_incidents[:5]),
                "code_name": code_def[0],
                "code_definition": code_def[1] or "",
                "object_of_study": object_of_study,
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

        # C06: Cargar prime_movers por documento
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
        prime_movers_text = (
            "\n".join(f"- {r[2]}: {r[0]} (confidence: {r[1]})" for r in prime_rows)
            if prime_rows
            else "(sin prime movers extraídos)"
        )

        response = llm.run_agent(
            "fc_main_concern_proposer",
            variables={
                "all_codes": all_codes,
                "all_memos": all_memos,
                "prime_movers_per_document": prime_movers_text,
                "researcher_feedback": "",
                "object_of_study": object_of_study,
                "research_question": research_question or "",
                "operational_question": operational_question or "(not yet generated)",
            },
        )
        return {
            "core_concern": response.get("core_concern", ""),
            "confidence": response.get("confidence", "LOW"),
            "recurring_problems": response.get("recurring_problems", []),
            "relevant_population_dimensions": response.get(
                "relevant_population_dimensions", []
            ),
        }
    finally:
        s.close()


@app.task(name="a15_core_emergence")
def task_a15_core_emergence(proyecto_id: str) -> dict:
    """A15: Identifica core category candidates desde el main concern."""
    s = SessionLocal()
    try:
        codes = s.execute(
            text(
                "SELECT id, nombre, definicion, puntaje_relevancia FROM categorias WHERE proyecto_id=:pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        all_codes = "\n".join(f"- [{c[3]}] {c[1]}: {c[2]}" for c in codes)

        # Estadísticas de co-ocurrencia básicas
        stats_rows = s.execute(
            text("""
            SELECT c.nombre, COUNT(DISTINCT cs.segmento_id) as seg_count,
                   COUNT(DISTINCT s.documento_id) as doc_count
            FROM categorias c
            LEFT JOIN codigos_segmento cs ON c.id = cs.categoria_id
            LEFT JOIN segmentos s ON cs.segmento_id = s.id
            WHERE c.proyecto_id = :pid
            GROUP BY c.id, c.nombre
            ORDER BY seg_count DESC
        """),
            {"pid": proyecto_id},
        ).fetchall()
        stats_text = "\n".join(
            f"- {r[0]}: {r[1]} segmentos en {r[2]} documentos" for r in stats_rows
        )

        response = llm.run_agent(
            "fc_core_emergence_proposer",
            variables={
                "core_concern": "(see task_a14 for confirmed core concern)",
                "object_of_study": "concern",
                "all_codes": all_codes,
                "code_statistics": stats_text,
            },
        )
        return {
            "core_candidates": response.get("core_category_candidates", []),
            "no_core_detected": response.get("no_core_detected", False),
        }
    finally:
        s.close()


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


# ═══════════════════════════════════════════════════════════════════════
# F0.6: Nemotrón — Research Question Builder (PRO, executeOnce)
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="fc_research_question_builder")
def task_research_question_builder(proyecto_id: str) -> dict:
    """F0.6: Generates formal CGT research question from population assumption.

    Reads population_description, object_of_study, generalized_population,
    spatial_frame, temporal_frame, and coding_styles from the DB. Calls the
    PRO model with the research_question_builder prompt. Stores the result in
    proyectos.population_assumption under key 'research_question'.

    Runs ONCE or on-demand (not automatic).
    """
    s = SessionLocal()
    try:
        # Read population_assumption JSONB
        row = s.execute(
            text(
                "SELECT population_assumption, object_of_study "
                "FROM proyectos WHERE id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if not row:
            return {"error": "Proyecto no encontrado", "proyecto_id": proyecto_id}

        pa = row[0] or {}
        object_of_study = row[1] or pa.get("object_of_study", "concern")

        population_description = pa.get("population_description", "")
        generalized_population = pa.get("generalized_population", "")
        spatial_frame = pa.get("spatial_frame", "")
        temporal_frame = pa.get("temporal_frame", "")
        coding_styles_list = pa.get("coding_styles", ["gerundio", "in_vivo"])
        coding_styles = (
            ", ".join(coding_styles_list)
            if isinstance(coding_styles_list, list)
            else str(coding_styles_list)
        )

        logger.info(
            "research_question_builder: proyecto=%s oos=%s pop=%s",
            proyecto_id[:8],
            object_of_study,
            population_description[:60] if population_description else "(sin desc)",
        )

        response = llm.run_agent(
            "fc_research_question_builder",
            variables={
                "object_of_study": object_of_study,
                "population_description": population_description or "(not specified)",
                "generalized_population": generalized_population or "(not specified)",
                "spatial_frame": spatial_frame or "(not specified)",
                "temporal_frame": temporal_frame or "(not specified)",
                "coding_styles": coding_styles,
                "processing_verb": pa.get("processing_verb", "resolve"),
                "processing_gerund": pa.get("processing_gerund", "resolving"),
                "processing_verb_conjugated": pa.get(
                    "processing_verb_conjugated", "resolve"
                ),
            },
        )

        # ── Store result in population_assumption JSONB ──
        result_data = {
            "research_question": response.get("research_question", ""),
            "operational_question": response.get("operational_question", ""),
            "rationale": response.get("rationale", ""),
            "key_dimensions": response.get("key_dimensions", []),
            "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

        # ── Critic: evaluate the generated research question ──
        try:
            critic = llm.run_agent(
                "fc_research_question_critic",
                variables={
                    "research_question": result_data["research_question"],
                    "operational_question": result_data["operational_question"],
                    "object_of_study": object_of_study,
                    "population_description": population_description
                    or "(not specified)",
                    "processing_verb": pa.get("processing_verb", "resolve"),
                    "key_dimensions": json.dumps(result_data.get("key_dimensions", [])),
                },
            )
            result_data["critic_verdict"] = critic.get("verdict", "SAT")
            result_data["critic_rationale"] = critic.get("rationale", "")
            result_data["critic_suggestions"] = critic.get("suggestions", [])
            logger.info("RQ critic verdict: %s", result_data["critic_verdict"])
        except Exception as e:
            logger.warning("RQ critic failed (non-blocking): %s", e)
            result_data["critic_verdict"] = "ERROR"

        # Merge into existing population_assumption
        updated_pa = dict(pa)
        updated_pa["research_question"] = result_data

        s.execute(
            text(
                "UPDATE proyectos SET population_assumption = :pa::jsonb "
                "WHERE id = :pid"
            ),
            {"pa": json.dumps(updated_pa), "pid": proyecto_id},
        )
        s.commit()

        logger.info(
            "research_question_builder: stored for proyecto=%s rq=%s",
            proyecto_id[:8],
            result_data["research_question"][:80]
            if result_data["research_question"]
            else "(empty)",
        )

        return result_data

    except Exception:
        s.rollback()
        logger.exception("research_question_builder failed for %s", proyecto_id[:8])
        raise
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
                texto = (doc[0] or {}).get("texto_extraido", "") if doc else ""
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
            if result_cc.get("status") != "completed":
                return {"status": "paused", "phase": "A", "gate": "core_emergence"}

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
                "Re-executing main_concern with feedback: %s", researcher_feedback[:100]
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
            },
        )

        # ── Critic ──
        critic = llm.run_agent(
            "fc_main_concern_critic",
            variables={
                "core_concern": proposal.get("core_concern", ""),
                "all_codes": all_codes,
                "prime_movers_per_document": prime_movers_text,
                "object_of_study": object_of_study,
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
    Proposer (PRO) → Critic (FLASH) → HITL gate.
    Llamado desde selective_coding_coordinator (directo) o via Celery.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'core_emergence' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "core_emergence"}
        if existing and existing[0] == "pending":
            return {
                "status": "paused",
                "gate": "core_emergence",
                "awaiting": "researcher",
            }

        codes = s.execute(
            text(
                "SELECT id, nombre, definicion, puntaje_relevancia "
                "FROM categorias WHERE proyecto_id=:pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        all_codes = "\n".join(f"- [{c[3]}] {c[1]}: {c[2]}" for c in codes)

        stats_rows = s.execute(
            text(
                "SELECT c.nombre, COUNT(DISTINCT cs.segmento_id), "
                "COUNT(DISTINCT s.documento_id) "
                "FROM categorias c "
                "LEFT JOIN codigos_segmento cs ON c.id = cs.categoria_id "
                "LEFT JOIN segmentos s ON cs.segmento_id = s.id "
                "WHERE c.proyecto_id = :pid GROUP BY c.id, c.nombre "
                "ORDER BY 2 DESC"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        stats_text = "\n".join(
            f"- {r[0]}: {r[1]} segmentos en {r[2]} documentos" for r in stats_rows
        )

        # Fetch object_of_study from project config
        oos_row = s.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = "concern"
        if oos_row and oos_row[0]:
            config = oos_row[0] if isinstance(oos_row[0], dict) else {}
            object_of_study = config.get("object_of_study", "concern")

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

        proposal = llm.run_agent(
            "fc_core_emergence_proposer",
            variables={
                "core_concern": core_concern,
                "object_of_study": object_of_study,
                "all_codes": all_codes,
                "code_statistics": stats_text,
            },
        )

        # Build incidents for each core category candidate
        candidates = proposal.get("core_category_candidates", [])
        candidate_incidents = []
        for cand in candidates:
            code_id = cand.get("code_id", "")
            incidents = s.execute(
                text(
                    "SELECT s.texto, d.original_filename "
                    "FROM codigos_segmento cs "
                    "JOIN segmentos s ON cs.segmento_id = s.id "
                    "JOIN documentos d ON s.documento_id = d.id "
                    "WHERE cs.categoria_id = :cid LIMIT 3"
                ),
                {"cid": code_id},
            ).fetchall()
            cand_with_incidents = dict(cand)
            cand_with_incidents["incidents"] = [
                {"text": inc[0], "document": inc[1]} for inc in incidents
            ]
            candidate_incidents.append(cand_with_incidents)

        # Build document list
        docs = s.execute(
            text(
                "SELECT id, original_filename FROM documentos WHERE proyecto_id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        document_list = "\n".join(f"- {d[0]}: {d[1]}" for d in docs)

        critic = llm.run_agent(
            "fc_core_emergence_critic",
            variables={
                "core_category_candidates_with_incidents": json.dumps(
                    candidate_incidents
                ),
                "document_list": document_list,
            },
        )

        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "core_emergence", proposal, critic)

        return {"status": "paused", "gate": "core_emergence", "awaiting": "researcher"}

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
        if oos_row and oos_row[0]:
            config = oos_row[0] if isinstance(oos_row[0], dict) else {}
            object_of_study = config.get("object_of_study", "concern")

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
                "WHERE project_id = :pid AND gate_name = 'core_emergence' "
                "AND status = 'accepted' ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        core_category = cc_row[0] if cc_row and cc_row[0] else "(not yet confirmed)"

        # Fetch existing categories with entity_type
        existing_cats = s.execute(
            text(
                "SELECT id, nombre, entity_type, definicion "
                "FROM categorias WHERE proyecto_id = :pid AND entity_type IS NOT NULL"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        existing_categories = (
            "\n".join(f"- [{cat[2]}] {cat[1]}: {cat[3]}" for cat in existing_cats)
            if existing_cats
            else "(no existing categories with entity_type yet)"
        )

        proposal = llm.run_agent(
            "fd_selective_reduction_proposer",
            variables={
                "core_concern": core_concern,
                "object_of_study": object_of_study,
                "core_category": core_category,
                "all_open_codes": all_codes,
                "existing_categories": existing_categories,
            },
        )

        # Extract reduced_codes and discarded_codes from proposal for the critic
        reduced_codes = proposal.get("reduced_codes", [])
        discarded_codes = proposal.get("discarded_codes", [])

        critic = llm.run_agent(
            "fd_selective_reduction_critic",
            variables={
                "reduced_codes": json.dumps(reduced_codes),
                "discarded_codes": json.dumps(discarded_codes),
                "all_open_codes": all_codes,
                "object_of_study": object_of_study,
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
            "AND category_ids @> to_jsonb(ARRAY[:cid::text])"
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
                "SELECT id, nombre, definicion, version, puntaje_relevancia, entity_type "
                "FROM categorias "
                "WHERE proyecto_id = :pid AND COALESCE(puntaje_relevancia, 0) >= 4 "
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

        results = {"project_id": proyecto_id, "categories": {}}
        total_expansions = 0
        theosampler_activations = 0
        theosampler_called_this_run = False  # rate-limit per loop run

        for cat_row in cats:
            cat_id = str(cat_row[0])
            cat_name = cat_row[1]
            cat_def = cat_row[2] or ""
            cat_version = cat_row[3] or 1
            cat_entity_type = cat_row[5] or "PROCESS"

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
                    },
                )

                # ── C2: Critic (FLASH) ──
                critic = llm.run_agent(
                    "fe_core_saturation_critic",
                    variables={
                        "proposed_expansions": json.dumps(proposal),
                        "current_paradigm_state": _get_paradigm_snapshot(s, cat_id),
                        "new_incidents": incident_text,
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
                "AND COALESCE(puntaje_relevancia, 0) >= 4 "
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

        # Fetch research_question from population_assessment JSONB
        pa_row = s.execute(
            text("SELECT population_assessment FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        research_question = rq_data.get("question", "")

        # Fetch core_category from accepted core_emergence HITL decision
        cc_row = s.execute(
            text(
                "SELECT proposal FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'core_emergence' "
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
            },
        )

        critic = llm.run_agent(
            "ff_database_a_critic",
            variables={
                "nodes": proposal.get("nodes", []),
                "saturated_categories": saturated_cats,
                "object_of_study": object_of_study,
                "core_category": core_category,
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
                "WHERE proyecto_id = :pid AND status = 'accepted'"
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

        # Fetch research_question from population_assessment JSONB
        pa_row = s.execute(
            text("SELECT population_assessment FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        research_question = rq_data.get("question", "")

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
            },
        )

        critic = llm.run_agent(
            "ff_database_b_critic",
            variables={
                "edges": proposal.get("edges", []),
                "nodes": nodes_text,
                "hypotheses": hyps_text,
                "object_of_study": object_of_study,
                "core_concern": core_concern,
            },
        )

        from agents.transitions import hitl_gate

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
            src_id = node_map.get(edge.get("source_node_label", ""))
            tgt_id = node_map.get(edge.get("target_node_label", ""))
            if src_id and tgt_id:
                s.execute(
                    text(
                        "INSERT INTO database_edges "
                        "(id, project_id, source_node_id, target_node_id, "
                        "relationship_type, evidence, direction, strength) "
                        "VALUES (gen_random_uuid(), :pid, :src, :tgt, :rtype, :ev, :dir, :str) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "pid": proyecto_id,
                        "src": src_id,
                        "tgt": tgt_id,
                        "rtype": edge.get("relationship_type", "CO_OCCURS_WITH"),
                        "ev": edge.get("evidence", ""),
                        "dir": edge.get("direction", "unidirectional"),
                        "str": edge.get("strength", "moderate"),
                    },
                )
                persisted += 1
        s.commit()
        logger.info(
            "Persisted %d/%d database edges for project %s (critic: %s)",
            persisted,
            len(edges),
            proyecto_id,
            critic.get("verdict", "?"),
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
                    "SELECT COUNT(*) FROM paradigm_states "
                    "WHERE code_id = :cid AND did_state_expand = false "
                    "ORDER BY iteration DESC LIMIT 3"
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
