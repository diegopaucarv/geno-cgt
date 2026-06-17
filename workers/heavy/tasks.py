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
            agent_id="a1",
            variables={
                "population_assumption": pop_assumption,
                "existing_context": existing_context or "(sin contexto previo)",
                "segments": "\n---\n".join(r[0] for r in segments)[:8000],
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

        agent_id = "a2"
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
            agent_id="a3",
            variables={
                "population_assumption": pop_assumption,
                "population_context": pop_ctx[0] if pop_ctx else "",
                "processes": processes_text,
                "existing_hypotheses": hyp_text,
                "task_section": task_section,
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
    obj = "concern"  # default
    if config and config[0]:
        obj = (
            config[0].get("object_of_study", "concern")
            if isinstance(config[0], dict)
            else "concern"
        )

    # Instrucciones segun objeto de estudio
    instructions = {
        "concern": "Busca el patron de COMPORTAMIENTO recurrente. Que intenta resolver este entrevistado una y otra vez?",
        "emotion": "Busca el patron EMOCIONAL recurrente. Que siente este entrevistado una y otra vez? Expresalo como gerundio (ej. 'Sintiendo culpa', 'Arrpentintiendose').",
        "behavior": "Busca la CONDUCTA observable recurrente. Que hace este entrevistado una y otra vez?",
        "discourse": "Busca el patron DISCURSIVO recurrente. Como construye su narrativa este entrevistado?",
        "identity": "Busca el TRABAJO IDENTITARIO recurrente. Como negocia su identidad este entrevistado?",
    }

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
        "prime_mover_extractor",
        variables={
            "document_name": doc_name[0] if doc_name else "",
            "baseline_segments": segments_text[:6000],
            "object_of_study": obj,
            "object_of_study_instructions": instructions.get(
                obj, instructions["concern"]
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
            checkpoint(session, documento_id, STEP, "completed")

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
# Agentes B — wrappers Celery (implementación en agents_b.py)
# ═══════════════════════════════════════════════════════════════════════

from agents_b import (
    b1_distill_sampling,
    b2_5_assign_codes_to_segments,
    b2_open_code,
    b3_generate_hypotheses,
)


@app.task(name="b1_distill_sampling")
def task_b1_distill_sampling(proyecto_id: str) -> dict:
    return b1_distill_sampling(proyecto_id)


@app.task(name="b2_open_code")
def task_b2_open_code(proyecto_id: str) -> dict:
    return b2_open_code(proyecto_id)


@app.task(name="b3_generate_hypotheses")
def task_b3_generate_hypotheses(proyecto_id: str) -> dict:
    return b3_generate_hypotheses(proyecto_id)


@app.task(
    name="process_synthesis_agents_b",
    base=AbortableTask,
    bind=True,
)
def process_synthesis_agents_b(self, proyecto_id: str) -> dict:
    results: dict[str, Any] = {"proyecto_id": proyecto_id}

    # ── Check abort ──
    if self._aborted:
        raise TaskCancelledError()

    s = SessionLocal()
    try:
        _pipeline_log_to(proyecto_id)
        logger.info("🔗 Phase B iniciado — proyecto=%s", proyecto_id)

        # ── B1: Sampling distiller ──
        _checkpoint_step(s, proyecto_id, "b1_distill_sampling", "in_progress")
        logger.info("B1: Muestreo %s", proyecto_id)
        results["sampling"] = b1_distill_sampling(proyecto_id)
        _checkpoint_step(s, proyecto_id, "b1_distill_sampling", "completed")

        # ── B2: Open coding ──
        if self._aborted:
            raise TaskCancelledError()
        _checkpoint_step(s, proyecto_id, "b2_open_code", "in_progress")
        logger.info("B2: Open coding %s", proyecto_id)
        results["open_coding"] = b2_open_code(proyecto_id)
        _checkpoint_step(s, proyecto_id, "b2_open_code", "completed")

        # ── B2.5: Grounding ──
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

        # ── B3: Hypotheses ──
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

        response = llm.run_agent(
            "paradigm_integrator",
            variables={
                "current_paradigm": _json.dumps(current_state, ensure_ascii=False),
                "new_incidents": "\n---\n".join(r[0] for r in new_incidents[:5]),
                "code_name": code_def[0],
                "code_definition": code_def[1] or "",
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
    """A14: 3 preguntas GT -> main_concern. Usa main_concern_proposer.md."""
    s = SessionLocal()
    try:
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
            "main_concern_proposer",
            variables={
                "all_codes": all_codes,
                "all_memos": all_memos,
                "prime_movers_per_document": prime_movers_text,
            },
        )
        return {
            "main_concern": response.get("main_concern", ""),
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
            "core_emergence_proposer",
            variables={
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
            "a16",
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
            "agrupador",
            variables={
                "constructs": constructs_text,
                "population_assumption": _get_population_assumption(s, proyecto_id),
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
            "main_concern": result.get("main_concern", ""),
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
                return {"status": "paused", "phase": "A", "gate": "main_concern"}

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


@app.task(name="main_concern_pipeline")
def task_main_concern_pipeline(proyecto_id: str) -> dict:
    """
    Fase A, Pasos A1+A2: Main Concern Detection.
    Proposer (PRO) → Critic (PRO) → HITL gate.
    """
    s = SessionLocal()
    try:
        existing = s.execute(
            text(
                "SELECT status FROM hitl_decisions "
                "WHERE project_id = :pid AND gate_name = 'main_concern' "
                "ORDER BY creado_en DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if existing and existing[0] == "accepted":
            return {"status": "completed", "gate": "main_concern"}
        if existing and existing[0] == "pending":
            return {
                "status": "paused",
                "gate": "main_concern",
                "awaiting": "researcher",
            }

        # Si hay una decisión modified, obtener el feedback para re-ejecutar
        researcher_feedback = ""
        if existing and existing[0] == "modified":
            fb_row = s.execute(
                text(
                    "SELECT researcher_feedback FROM hitl_decisions "
                    "WHERE project_id = :pid AND gate_name = 'main_concern' "
                    "AND status = 'modified' ORDER BY creado_en DESC LIMIT 1"
                ),
                {"pid": proyecto_id},
            ).fetchone()
            researcher_feedback = (fb_row[0] or "") if fb_row else ""
            logger.info(
                "Re-executing main_concern with feedback: %s", researcher_feedback[:100]
            )

        # ── Proposer ──
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
            "main_concern_proposer",
            variables={
                "all_codes": all_codes,
                "all_memos": all_memos,
                "prime_movers_per_document": prime_movers_text,
                "researcher_feedback": researcher_feedback,
            },
        )

        # ── Critic ──
        critic = llm.run_agent(
            "main_concern_critic",
            variables={
                "main_concern": proposal.get("main_concern", ""),
                "all_codes": all_codes,
                "prime_movers_per_document": prime_movers_text,
            },
        )

        # ── HITL gate ──
        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "main_concern", proposal, critic)

        return {"status": "paused", "gate": "main_concern", "awaiting": "researcher"}

    except Exception:
        logger.exception("main_concern_pipeline failed for %s", proyecto_id)
        raise
    finally:
        s.close()


@app.task(name="core_emergence_pipeline")
def task_core_emergence_pipeline(proyecto_id: str) -> dict:
    """
    Fase A, Pasos A3+A4: Core Category Emergence.
    Proposer (PRO) → Critic (FLASH) → HITL gate.
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

        proposal = llm.run_agent(
            "core_emergence_proposer",
            variables={"all_codes": all_codes, "code_statistics": stats_text},
        )

        critic = llm.run_agent(
            "core_emergence_critic",
            variables={
                "core_category_candidates": proposal.get(
                    "core_category_candidates", []
                ),
                "code_incidents": "(ver codigos_segmento)",
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


@app.task(name="selective_reduction_pipeline")
def task_selective_reduction_pipeline(proyecto_id: str) -> dict:
    """
    Fase B, Pasos B1+B2: Selective Reduction.
    Proposer (PRO) → Critic (PRO) → HITL gate.
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

        cooc_rows = s.execute(
            text(
                "SELECT c1.nombre, c2.nombre, COUNT(*) "
                "FROM codigos_segmento cs1 "
                "JOIN codigos_segmento cs2 ON cs1.segmento_id = cs2.segmento_id "
                "JOIN categorias c1 ON cs1.categoria_id = c1.id "
                "JOIN categorias c2 ON cs2.categoria_id = c2.id "
                "WHERE c1.proyecto_id = :pid AND c2.proyecto_id = :pid2 "
                "AND c1.id < c2.id GROUP BY c1.nombre, c2.nombre LIMIT 100"
            ),
            {"pid": proyecto_id, "pid2": proyecto_id},
        ).fetchall()
        cooc_text = "\n".join(
            f"- {r[0]} ↔ {r[1]}: {r[2]} co-occurrences" for r in cooc_rows
        )

        proposal = llm.run_agent(
            "selective_reduction_proposer",
            variables={
                "core_category": "(ver hitl_decisions para core_category aceptada)",
                "all_codes": all_codes,
                "code_relationships": cooc_text,
            },
        )

        critic = llm.run_agent(
            "selective_reduction_critic",
            variables={
                "reduction_proposal": proposal,
                "core_category": "(ver hitl_decisions)",
                "all_codes": all_codes,
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


@app.task(
    name="core_saturation_loop",
    base=AbortableTask,
    bind=True,
)
def task_core_saturation_loop(self, proyecto_id: str) -> dict:
    """
    Fase C: Core Saturation Loop.

    Itera sobre categorías con score ≥ 4 × documentos del proyecto.
    Para cada par (cat, doc), ejecuta Proposer→Critic y evalúa si
    el estado de la categoría se expande.

    Criterio de saturación: did_state_expand=false por 3 iteraciones
    consecutivas para una misma categoría → HITL gate.
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

        results = {"project_id": proyecto_id, "categories": {}}
        total_expansions = 0

        for cat_row in cats:
            cat_id = str(cat_row[0])
            cat_name = cat_row[1]
            cat_def = cat_row[2] or ""
            cat_version = cat_row[3] or 1

            # Verificar si ya está saturada (3 iteraciones sin expansión)
            no_expand_count = s.execute(
                text(
                    "SELECT COUNT(*) FROM paradigm_states "
                    "WHERE code_id = :cid AND did_state_expand = false "
                    "ORDER BY iteration DESC LIMIT 3"
                ),
                {"cid": cat_id},
            ).fetchone()[0]

            if no_expand_count >= 3:
                logger.info("Category %s already saturated, skipping", cat_name)
                results["categories"][cat_name] = {
                    "status": "saturated",
                    "iterations_without_expansion": no_expand_count,
                }
                continue

            cat_results = {"iterations": 0, "expansions": 0, "status": "processing"}

            for doc_row in docs:
                if self._aborted:
                    raise TaskCancelledError()

                doc_id = str(doc_row[0])
                doc_name = doc_row[1]

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
                    "core_saturation_proposer",
                    variables={
                        "category_label": cat_name,
                        "category_definition": cat_def,
                        "version": str(cat_version),
                        "current_properties": _get_paradigm_snapshot(s, cat_id),
                        "document_name": doc_name,
                        "incident_text": incident_text,
                    },
                )

                # ── C2: Critic (FLASH) ──
                critic = llm.run_agent(
                    "core_saturation_critic",
                    variables={
                        "elaboration_result": proposal,
                        "category_definition": cat_def,
                        "paradigm_state": _get_paradigm_snapshot(s, cat_id),
                        "incident_text": incident_text,
                    },
                    tier="FAST",
                )

                did_expand = proposal.get("did_state_expand", False)
                cat_results["iterations"] += 1

                if did_expand:
                    cat_results["expansions"] += 1
                    total_expansions += 1
                    no_expand_count = 0

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
                    no_expand_count += 1
                    _record_paradigm_state(
                        s,
                        cat_id,
                        proyecto_id,
                        did_expand=False,
                        etype="converges",
                        snapshot=proposal,
                        memo="",
                    )

                # Check saturation criterion
                if no_expand_count >= 3:
                    cat_results["status"] = "saturated"
                    cat_results["iterations_without_expansion"] = no_expand_count
                    logger.info(
                        "Category %s saturated after %d iterations without expansion",
                        cat_name,
                        no_expand_count,
                    )
                    break

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

        proposal = llm.run_agent(
            "database_a_proposer",
            variables={
                "saturated_categories": saturated_cats,
                "core_category": "(ver hitl_decisions)",
            },
        )

        critic = llm.run_agent(
            "database_a_critic",
            variables={
                "nodes": proposal.get("nodes", []),
                "saturated_categories": saturated_cats,
            },
        )

        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "database_a", proposal, critic)

        # ── Si el critic dio SAT, persistir nodos inmediatamente ──
        if critic.get("verdict") == "SAT":
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
                "Persisted %d database nodes for project %s", len(nodes), proyecto_id
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

        proposal = llm.run_agent(
            "database_b_proposer",
            variables={
                "nodes": nodes_text,
                "conceptual_relationships": rels_text,
                "hypotheses": hyps_text,
            },
        )

        critic = llm.run_agent(
            "database_b_critic",
            variables={
                "edges": proposal.get("edges", []),
                "nodes": nodes_text,
                "hypotheses": hyps_text,
            },
        )

        from agents.transitions import hitl_gate

        hitl_gate(s, proyecto_id, "database_b", proposal, critic)

        # ── Si el critic dio SAT, persistir edges ──
        if critic.get("verdict") == "SAT":
            edges = proposal.get("edges", [])
            # Mapa label→id para resolver source/target
            node_map = {}
            node_rows = s.execute(
                text("SELECT id, label FROM database_nodes WHERE project_id = :pid"),
                {"pid": proyecto_id},
            ).fetchall()
            for nr in node_rows:
                node_map[str(nr[1])] = str(nr[0])

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
            s.commit()
            logger.info(
                "Persisted %d database edges for project %s", len(edges), proyecto_id
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
