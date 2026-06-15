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

app = Celery("heavy_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
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
                "sd": response.get("surprising_details", ""),
                "lp": response.get("language_patterns", ""),
                "dpc": response.get("data_production_context", ""),
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
                "SELECT texto FROM segmentos WHERE documento_id = :did ORDER BY posicion LIMIT 10"
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
                "segments": segments_text[:6000],
                "task_section": task_section_with_hint,
            },
            temperature=0.3,
        )

        if response.get("mock_note"):
            return {"error": "mock fallback"}

        result = session.execute(
            text(
                "INSERT INTO document_processes (id, documento_id, proyecto_id, process_description, similarity_to_previous, difference_from_previous, previous_document_id) VALUES (gen_random_uuid(), :did, :pid, :pd, :stp, :dfp, :prevd) RETURNING id"
            ),
            {
                "did": documento_id,
                "pid": proyecto_id,
                "pd": response.get("process_description", ""),
                "stp": response.get("similarity_to_previous"),
                "dfp": response.get("difference_from_previous"),
                "prevd": str(previous[1]) if previous else None,
            },
        )
        session.commit()
        new_id = str(result.fetchone()[0])

        return {
            "document_process_id": new_id,
            "process_description": response.get("process_description", ""),
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
    """Segmenta el documento con spaCy si no tiene segmentos."""
    count = session.execute(
        text("SELECT COUNT(*) FROM segmentos WHERE documento_id = :did"),
        {"did": documento_id},
    ).fetchone()[0]
    if count > 0:
        return

    doc_row = session.execute(
        text("SELECT metadatos FROM documentos WHERE id = :did"),
        {"did": documento_id},
    ).fetchone()
    if not doc_row or not doc_row[0]:
        return

    metadatos = doc_row[0] if isinstance(doc_row[0], dict) else {}
    texto = metadatos.get("texto_extraido", "")
    if not texto:
        return

    session.execute(
        text("UPDATE documentos SET estado = 'segmentando' WHERE id = :did"),
        {"did": documento_id},
    )
    session.commit()

    # Segmentation happens in worker-nlp. Poll until segments appear.
    import time as _time

    for attempt in range(40):
        count = session.execute(
            text("SELECT COUNT(*) FROM segmentos WHERE documento_id = :did"),
            {"did": documento_id},
        ).fetchone()[0]
        if count > 0:
            logger.info("Segments ready: doc=%s, count=%d", documento_id, count)
            # A2: anchor reconstruction
            full_text = (
                metadatos.get("texto_extraido", "")
                if isinstance(metadatos, dict)
                else ""
            )
            if full_text:
                _anchor_segments(session, documento_id, full_text)
            return
        if attempt == 0:
            logger.info("Waiting for worker-nlp to segment doc=%s...", documento_id)
        _time.sleep(3)
    logger.warning("Timeout waiting for segments: doc=%s", documento_id)


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


def _mark_doc_ready(documento_id: str) -> None:
    s = SessionLocal()
    try:
        s.execute(
            text("UPDATE documentos SET estado = 'listo' WHERE id = :did"),
            {"did": documento_id},
        )
        s.commit()
    finally:
        s.close()


def _mark_doc_error(documento_id: str, error_msg: str) -> None:
    s = SessionLocal()
    try:
        s.execute(
            text("UPDATE documentos SET estado = 'error' WHERE id = :did"),
            {"did": documento_id},
        )
        s.execute(
            text(
                "UPDATE documentos SET metadatos = metadatos || jsonb_build_object('pipeline_error', :err) WHERE id = :did"
            ),
            {"did": documento_id, "err": error_msg[:500]},
        )
        s.commit()
    finally:
        s.close()


def _maybe_trigger_phase_b(proyecto_id: str) -> None:
    """B20: Incremental. Solo dispara si hay >= 3 docs NUEVOS desde la ultima Phase B."""
    s = SessionLocal()
    try:
        doc_count = s.execute(
            text("SELECT COUNT(*) FROM document_processes WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if doc_count < 3:
            return

        last = s.execute(
            text(
                "SELECT step FROM processing_states "
                "WHERE entity_type = 'project' AND entity_id = :pid "
                "AND step LIKE 'phase_b_dc_%' "
                "ORDER BY step DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        last_count = int(last[0].split("_")[-1]) if last else 0

        new_docs = doc_count - last_count
        if new_docs < 3:
            return

        logger.info("Phase B incremental: +%d docs (total=%d)", new_docs, doc_count)
        process_synthesis_agents_b(proyecto_id)

        s.execute(
            text(
                "INSERT INTO processing_states (entity_type, entity_id, step) "
                "VALUES ('project', :pid, :st) ON CONFLICT DO NOTHING"
            ),
            {"pid": proyecto_id, "st": f"phase_b_dc_{doc_count}"},
        )
        s.commit()
    finally:
        s.close()


# ═══════════════════════════════════════════════════════════════════════
# Pipeline A
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="process_document_agents_a")
def process_document_agents_a(documento_id: str, proyecto_id: str) -> dict:
    results: dict[str, Any] = {"documento_id": documento_id}
    session = SessionLocal()

    try:
        # 0. Asegurar segmentación (si el doc no tiene segmentos aún)
        _ensure_segmented(session, documento_id)

        # Actualizar estado → procesando
        session.execute(
            text("UPDATE documentos SET estado = 'procesando' WHERE id = :did"),
            {"did": documento_id},
        )
        session.commit()
    finally:
        session.close()

    logger.info("A1: Contexto poblacional doc %s", documento_id)
    results["population_context"] = a1_build_population_context(
        documento_id, proyecto_id
    )
    if "error" in results["population_context"]:
        _mark_doc_error(
            documento_id, str(results["population_context"].get("error", "a1_failed"))
        )
        return results

    logger.info("A2: Proceso doc %s", documento_id)
    results["document_process"] = a2_identify_process(documento_id, proyecto_id)
    if "error" in results["document_process"]:
        _mark_doc_error(
            documento_id, str(results["document_process"].get("error", "a2_failed"))
        )
        return results

    # C06: Extraer prime_mover del documento (usa solo baseline_data)
    logger.info("C06: Prime mover doc %s", documento_id)
    try:
        pm_result = _extract_prime_mover(session, documento_id, proyecto_id)
        results["prime_mover"] = pm_result
        # Persistir en document_processes
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

    logger.info("A3: Sentido emergente proyecto %s", proyecto_id)
    results["sense_making"] = a3_make_sense(proyecto_id)

    # Marcar documento como listo
    _mark_doc_ready(documento_id)

    # Si es el tercer documento (o múltiplo de 3), disparar síntesis B
    _maybe_trigger_phase_b(proyecto_id)

    return results


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


@app.task(name="process_synthesis_agents_b")
def process_synthesis_agents_b(proyecto_id: str) -> dict:
    results: dict[str, Any] = {"proyecto_id": proyecto_id}
    logger.info("B1: Muestreo %s", proyecto_id)
    results["sampling"] = b1_distill_sampling(proyecto_id)
    logger.info("B2: Open coding %s", proyecto_id)
    results["open_coding"] = b2_open_code(proyecto_id)
    logger.info("B2.5: Grounding %s", proyecto_id)
    results["grounding"] = b2_5_assign_codes_to_segments(proyecto_id)

    # B17: SaturationCalculator
    try:
        app.send_task("update_saturation", args=[proyecto_id], queue="nlp")
    except Exception:
        pass

    # B18: Prototype cache rebuild
    try:
        __rebuild_cache(proyecto_id)
    except Exception:
        pass

    logger.info("B3: Hipotesis %s", proyecto_id)
    results["hypotheses"] = b3_generate_hypotheses(proyecto_id)
    return results


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
    Dispara elaboracion selectiva para todas las categorias del proyecto.
    Itera sobre cada categoria y ejecuta incident_elaborator.
    """
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


@app.task(name="invoke_graph")
def invoke_graph(proyecto_id: str, documento_id: str = None) -> dict:
    """
    B21: Invoca el StateGraph para un documento (o el proyecto completo).

    El grafo (workflow.py) orquesta los agentes como nodos.
    PostgresSaver checkpointea entre nodos para pausar/reanudar.
    Los agentes se llaman como funciones sincronas (no via Celery).

    Si documento_id es None, invoca la fase de sintesis (B).
    """
    try:
        import os as _os

        from app.core.workflow import AnalysisState, build_glaser_graph
        from config import DATABASE_URL as db_url
        from langgraph.checkpoint.postgres import PostgresSaver

        saver = PostgresSaver.from_conn_string(db_url)
        saver.setup()

        graph = build_glaser_graph()
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
