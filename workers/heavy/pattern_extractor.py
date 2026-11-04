"""
F2.3 — Document Pattern & Evidence Extractor (PRO, per-document).

Reads ALL baseline segments of a document and identifies:
  1. Tentative patterns (codes with gerunds)
  2. Incidents (evidence one-liners, NO gerunds) linked to patterns and segments
  3. Document-level signals (prime mover, main concern)

Replaces the old per-segment extract_incident loop (~13 FLASH calls per doc)
with ONE PRO call that does unified Open Coding.

Design based on n8n Open Coder approach: explication de texte in one pass.
Incidents are evidence, not codes. Patterns are codes (gerunds).
"""

from __future__ import annotations

import json
import logging
import os
import sys

sys.path.insert(0, "/app")

from database import SessionLocal, engine
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


class ExtractionFailed(RuntimeError):
    """La extracción F2.3 no pudo completarse; no debe reportarse como éxito."""


def _get_object_of_study(session, proyecto_id: str) -> str:
    row = session.execute(
        text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    return row[0] if row and row[0] else "concern"


def _get_operational_question(session, proyecto_id: str) -> str:
    pa_row = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if pa_row and pa_row[0] and isinstance(pa_row[0], dict):
        rq = pa_row[0].get("research_question", {})
        return rq.get("operational_question", "") if isinstance(rq, dict) else ""
    return ""


def extract_patterns_and_incidents(
    documento_id: str,
    proyecto_id: str,
    replace_existing: bool = True,
) -> dict:
    """Unified Open Coding: patterns + incidents + signals in ONE PRO call.

    Args:
        documento_id: UUID of the document.
        proyecto_id: UUID of the project.
        replace_existing: When True (default), remove this document's previous
            incidents (and the comparisons that reference them) after the LLM
            call succeeds and before inserting the new rows. Makes re-runs of
            the same document idempotent.

    Returns:
        dict with patterns, incidents, and document_signals from the AI.
    """
    session = SessionLocal()
    lock_conn = None
    try:
        # ── 0. Advisory lock por documento ────────────────────────
        # Dos ejecuciones concurrentes del mismo doc harían DELETE + INSERT
        # en paralelo y duplicarían incidentes. El lock es de sesión Postgres,
        # así que se toma en una conexión dedicada que permanece abierta hasta
        # el finally (si se tomara en `session` el COMMIT la devolvería al pool
        # y el unlock podría caer en otra conexión).
        try:
            lock_conn = engine.connect()
            lock_conn.execute(
                text("SELECT pg_advisory_lock(hashtext(:key))"),
                {"key": f"extract_incidents:{documento_id}"},
            )
            lock_conn.commit()
        except Exception as exc:
            logger.error(
                "Pattern extraction: no se pudo tomar el advisory lock doc=%s — %s",
                documento_id[:8],
                exc,
            )
            raise ExtractionFailed(
                f"advisory lock no disponible para doc={documento_id}"
            ) from exc

        # ── 1. Fetch baseline segments ───────────────────────────
        seg_rows = session.execute(
            text(
                "SELECT id, texto, posicion FROM segmentos "
                "WHERE documento_id = :did "
                "AND (tipo_dato_glaser = 'baseline_data' OR tipo_dato_glaser IS NULL) "
                "ORDER BY posicion"
            ),
            {"did": documento_id},
        ).fetchall()

        if not seg_rows:
            logger.warning("No baseline segments for doc=%s", documento_id[:8])
            raise ExtractionFailed(f"sin segmentos baseline para doc={documento_id}")

        # ── 2. Build segments_text for the prompt ─────────────────
        parts = []
        for i, row in enumerate(seg_rows):
            seg_id = str(row[0])
            seg_text = (row[1] or "").strip()
            if seg_text:
                parts.append(
                    f"--- Segment {i + 1} (seg={i + 1}, id={seg_id[:8]}) ---\n{seg_text[:2000]}"
                )

        segments_text = "\n\n".join(parts)
        seg_count = len(parts)

        # Truncate if too long for context window (~20K chars safe)
        max_chars = 20000
        segments_omitted = 0
        if len(segments_text) > max_chars:
            # Cuántos segmentos completos entran antes del límite
            kept = 0
            used = 0
            for part in parts:
                needed = len(part) + (2 if kept else 0)
                if used + needed > max_chars:
                    break
                used += needed
                kept += 1
            segments_omitted = max(seg_count - kept, 1)
            segments_text = segments_text[:max_chars] + (
                "\n\n[... texto truncado por límite de contexto ...]"
            )
            logger.warning(
                "Pattern extraction: prompt truncado doc=%s — %d de %d "
                "segmentos omitidos (%d chars)",
                documento_id[:8],
                segments_omitted,
                seg_count,
                max_chars,
            )

        logger.info(
            "Pattern extraction: doc=%s, %d baseline segments, %d chars",
            documento_id[:8],
            seg_count,
            len(segments_text),
        )

        # ── 3. Get document name ──────────────────────────────────
        doc_name_row = session.execute(
            text("SELECT original_filename FROM documentos WHERE id = :did"),
            {"did": documento_id},
        ).fetchone()
        doc_name = doc_name_row[0] if doc_name_row else documento_id

        # ── 4. Get project config ─────────────────────────────────
        object_of_study = _get_object_of_study(session, proyecto_id)
        operational_question = _get_operational_question(session, proyecto_id)

        # ── 5. Call AI (PRO) ─────────────────────────────────────
        # Per-document content travels in the user message so the static
        # system prefix (instructions + schema) stays cacheable across the batch.
        user_content = (
            f"[DOCUMENT]\nName: {doc_name}\n\n"
            f"[ALL BASELINE SEGMENTS FROM THIS DOCUMENT]\n{segments_text}"
        )
        response = llm.run_agent(
            "fa_document_pattern_extractor",
            variables={
                "segments_text": segments_text,
                "document_name": doc_name,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
            },
            cache_key=str(proyecto_id),
            tail_variables=("segments_text", "document_name"),
            user_content=user_content,
        )

        # ── 5.5: Log raw response keys for debugging ────────────
        logger.info(
            "Pattern extraction raw response keys: %s",
            list(response.keys())
            if isinstance(response, dict)
            else type(response).__name__,
        )
        # Log first 500 chars of each key if empty results
        patterns_raw = response.get("patterns", [])
        incidents_raw = response.get("incidents", [])
        signals_raw = response.get("document_signals", {})
        if not patterns_raw and not incidents_raw:
            logger.warning(
                "Pattern extraction EMPTY result for doc=%s. RAW response (first 1000 chars): %s",
                documento_id[:8],
                str(response)[:1000],
            )

        # ── 6. Validate ──────────────────────────────────────────
        if response.get("mock_note") or response.get("error"):
            cause = response.get("mock_note", response.get("error", ""))
            logger.warning(
                "Pattern extraction: mock/error for doc=%s — %s",
                documento_id[:8],
                cause,
            )
            raise ExtractionFailed(
                f"respuesta mock/error del LLM para doc={documento_id}: {cause}"
            )

        patterns = response.get("patterns", [])
        incidents = response.get("incidents", [])
        doc_signals = response.get("document_signals", {})

        # ── 7. Persist incidents to DB ───────────────────────────
        # Build seg index → seg_id map
        seg_map = {i + 1: str(r[0]) for i, r in enumerate(seg_rows)}

        # ── 7a. Replace this document's previous extraction ───────
        # Both incident_comparisons FKs are NO ACTION (confdeltype='a'), not
        # CASCADE, so the dependent rows must be removed before their
        # incidents. Deferred until after the mock/error guard above so a
        # failed LLM call never wipes existing data.
        if replace_existing:
            deleted_comparisons = (
                session.execute(
                    text(
                        "DELETE FROM incident_comparisons "
                        "WHERE incident_a_id IN ("
                        "SELECT id FROM extracted_incidents "
                        "WHERE documento_id = :did AND proyecto_id = :pid) "
                        "OR incident_b_id IN ("
                        "SELECT id FROM extracted_incidents "
                        "WHERE documento_id = :did AND proyecto_id = :pid)"
                    ),
                    {"did": documento_id, "pid": proyecto_id},
                ).rowcount
                or 0
            )

            deleted_incidents = (
                session.execute(
                    text(
                        "DELETE FROM extracted_incidents "
                        "WHERE documento_id = :did AND proyecto_id = :pid"
                    ),
                    {"did": documento_id, "pid": proyecto_id},
                ).rowcount
                or 0
            )

            logger.info(
                "Pattern extraction: removed %d previous incidents for doc=%s",
                deleted_incidents,
                documento_id[:8],
            )
            if deleted_comparisons:
                logger.info(
                    "Pattern extraction: removed %d previous comparisons for doc=%s",
                    deleted_comparisons,
                    documento_id[:8],
                )

        persisted_incidents = 0
        failed_inserts = 0
        for inc in incidents:
            description = (inc.get("description") or "").strip()
            if not description:
                continue

            seg_refs = inc.get("segment_refs", [])
            pattern_ids = inc.get("patterns", [])
            exact_quote = inc.get("exact_quote", "")

            # Resolve segment refs to actual UUIDs
            segment_ids = []
            seg_refs_clean = []  # integers only, for JSONB storage
            for ref in seg_refs:
                if isinstance(ref, int) and ref in seg_map:
                    segment_ids.append(seg_map[ref])
                    seg_refs_clean.append(ref)
                elif isinstance(ref, str) and ref.isdigit():
                    rint = int(ref)
                    if rint in seg_map:
                        segment_ids.append(seg_map[rint])
                        seg_refs_clean.append(rint)

            # If no valid segment refs, link to first baseline segment as fallback
            unlinked = False
            if not segment_ids and seg_rows:
                logger.warning(
                    "Pattern extraction: incidente sin segment_refs resolubles "
                    "doc=%s — se enlaza al primer segmento baseline: %.80s",
                    documento_id[:8],
                    description,
                )
                segment_ids = [str(seg_rows[0][0])]
                seg_refs_clean = [1]
                unlinked = True

            # ONE row per incident, segmento_id = first referenced segment
            primary_seg = segment_ids[0] if segment_ids else None
            if not primary_seg:
                continue

            meta = {
                "patterns": pattern_ids,
                "segment_refs": seg_refs_clean,
                "exact_quote": exact_quote,
                "method": "unified_pattern_extractor",
            }
            if unlinked:
                meta["unlinked"] = True

            try:
                session.execute(
                    text(
                        "INSERT INTO extracted_incidents "
                        "(id, segmento_id, documento_id, proyecto_id, "
                        "jot_text, keep_moving, tipo_dato_glaser, "
                        "preguntas_glaser_json) "
                        "VALUES (gen_random_uuid(), :sid, :did, :pid, "
                        ":desc, true, 'baseline_data', CAST(:meta AS jsonb))"
                    ),
                    {
                        "sid": primary_seg,
                        "did": documento_id,
                        "pid": proyecto_id,
                        "desc": description,
                        "meta": json.dumps(meta),
                    },
                )
                persisted_incidents += 1
            except Exception as e:
                failed_inserts += 1
                logger.warning(
                    "Pattern extraction: fallo al persistir incidente doc=%s: %s",
                    documento_id[:8],
                    e,
                )

        if failed_inserts:
            # Una corrida parcialmente persistida no puede reportarse como éxito:
            # se revierte también el DELETE previo para no perder los datos viejos.
            session.rollback()
            raise ExtractionFailed(
                f"{failed_inserts} incidentes no se pudieron persistir "
                f"(doc={documento_id}, proyecto={proyecto_id})"
            )

        session.commit()

        # ── 8. Persist document-level signals ────────────────────
        prime_mover = doc_signals.get("core_pattern") or doc_signals.get(
            "prime_mover", ""
        )
        main_concern = doc_signals.get("main_concern_signal", "")
        confidence = doc_signals.get("confidence", "MEDIUM")

        if prime_mover:
            existing = session.execute(
                text(
                    "SELECT id FROM document_processes "
                    "WHERE documento_id = :did AND proyecto_id = :pid"
                ),
                {"did": documento_id, "pid": proyecto_id},
            ).fetchone()

            if existing:
                session.execute(
                    text(
                        "UPDATE document_processes "
                        "SET prime_mover = :pm, "
                        "prime_mover_confidence = :pmc "
                        "WHERE id = :dpid"
                    ),
                    {"pm": prime_mover, "pmc": confidence, "dpid": str(existing[0])},
                )
            else:
                session.execute(
                    text(
                        "INSERT INTO document_processes "
                        "(id, documento_id, proyecto_id, process_description, "
                        "prime_mover, prime_mover_confidence) "
                        "VALUES (gen_random_uuid(), :did, :pid, :pd, :pm, :pmc)"
                    ),
                    {
                        "did": documento_id,
                        "pid": proyecto_id,
                        "pd": prime_mover,
                        "pm": prime_mover,
                        "pmc": confidence,
                    },
                )

            session.commit()

        logger.info(
            "Pattern extraction complete: doc=%s, %d patterns, %d incidents, "
            "core_pattern='%s'",
            documento_id[:8],
            len(patterns),
            persisted_incidents,
            prime_mover[:60] if prime_mover else "(none)",
        )

        return {
            "documento_id": documento_id,
            "patterns": patterns,
            "incidents_count": persisted_incidents,
            "document_signals": doc_signals,
            "segments_omitted": segments_omitted,
            "mock": False,
        }

    except ExtractionFailed:
        raise
    except Exception as exc:
        logger.exception(
            "Pattern extraction failed for doc=%s proyecto=%s",
            documento_id,
            proyecto_id,
        )
        raise ExtractionFailed(
            f"extracción falló para doc={documento_id} proyecto={proyecto_id}: {exc}"
        ) from exc
    finally:
        if lock_conn is not None:
            try:
                lock_conn.execute(text("SELECT pg_advisory_unlock_all()"))
                lock_conn.commit()
            except Exception as exc:
                logger.warning(
                    "Pattern extraction: no se pudo liberar el advisory lock "
                    "doc=%s — %s",
                    documento_id[:8],
                    exc,
                )
            finally:
                try:
                    lock_conn.close()
                except Exception:
                    pass
        session.close()
