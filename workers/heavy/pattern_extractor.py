"""
F2.4 — Core Pattern Extractor (PRO, per-documento).

Síntesis multi-párrafo del patrón central que emerge de TODOS los
incidentes extraídos de un documento. Solo ve incidentes del doc actual.
No ve otros documentos ni categorías existentes.

PRO tier — deep reasoning, low volume (1 call per document).

Output:
  - core_pattern: gerundio que nombra el patrón central
  - description: síntesis multi-párrafo
  - evidence_quotes: citas exactas de los incidentes que sustentan el patrón
  - confidence: HIGH | MEDIUM | LOW

Alimenta document_processes y vincula incidentes vía patron_documento_id.
"""

from __future__ import annotations

import json
import logging
import sys

sys.path.insert(0, "/app")

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def _get_object_of_study(session, proyecto_id: str) -> str:
    """Obtiene el object_of_study del proyecto. Default: 'concern'."""
    row = session.execute(
        text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if row and row[0]:
        return row[0]
    return "concern"


def _build_incidents_text(session, documento_id: str) -> str:
    """Construye el texto consolidado de todos los incidentes del documento."""
    rows = session.execute(
        text(
            "SELECT id, jot_text, preguntas_glaser_json "
            "FROM extracted_incidents "
            "WHERE documento_id = :did "
            "ORDER BY creado_en"
        ),
        {"did": documento_id},
    ).fetchall()

    if not rows:
        return "(sin incidentes extraídos)"

    parts: list[str] = []
    for i, row in enumerate(rows):
        inc_id = str(row[0])
        jot = row[1] or "(sin jot)"
        preguntas = row[2] if isinstance(row[2], dict) else {}

        block = f"--- Incidente {i + 1} (id={inc_id[:8]}) ---\nJot: {jot}\n"
        for key, label in [
            ("what_is_this_about", "¿De qué trata?"),
            ("what_category", "¿Qué categoría indica?"),
            ("what_is_happening", "¿Qué está sucediendo?"),
            ("participants_pattern", "Patrón del participante"),
        ]:
            val = preguntas.get(key, "")
            if val:
                block += f"{label}: {val}\n"
        parts.append(block)

    return "\n".join(parts)


def extract_core_pattern(documento_id: str, proyecto_id: str) -> dict:
    """Sintetiza el patrón central de un documento a partir de sus incidentes.

    PRO, 1-pass. Solo ve incidentes del documento actual.
    Inserta/actualiza en document_processes y vincula incidentes.

    Args:
        documento_id: UUID del documento.
        proyecto_id: UUID del proyecto.

    Returns:
        dict con el resultado: {document_process_id, core_pattern, confidence, ...}
    """
    session = SessionLocal()
    try:
        # ── 1. Leer incidentes del documento ───────────────────────────
        inc_count = session.execute(
            text("SELECT COUNT(*) FROM extracted_incidents WHERE documento_id = :did"),
            {"did": documento_id},
        ).fetchone()[0]

        if inc_count == 0:
            logger.warning(
                "extract_core_pattern: doc=%s sin incidentes — no se puede sintetizar",
                documento_id,
            )
            return {
                "error": "sin_incidentes",
                "documento_id": documento_id,
                "incident_count": 0,
            }

        incidents_text = _build_incidents_text(session, documento_id)
        logger.info(
            "extract_core_pattern: doc=%s incidentes=%d chars=%d",
            documento_id[:8],
            inc_count,
            len(incidents_text),
        )

        # ── 2. Obtener object_of_study ────────────────────────────────
        object_of_study = _get_object_of_study(session, proyecto_id)

        # ── 2.5. Obtener operational_question y document_name ─────
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")

        doc_name_row = session.execute(
            text("SELECT original_filename FROM documentos WHERE id = :did"),
            {"did": documento_id},
        ).fetchone()
        doc_name = doc_name_row[0] if doc_name_row else documento_id

        # ── 3. Truncar si excede el contexto PRO (~6K chars para el texto de incidentes) ──
        max_incident_chars = 6000
        if len(incidents_text) > max_incident_chars:
            logger.warning(
                "extract_core_pattern: truncando incidentes de %d a %d chars",
                len(incidents_text),
                max_incident_chars,
            )
            incidents_text = incidents_text[:max_incident_chars] + (
                "\n\n[... texto truncado por límite de contexto ...]"
            )

        # ── 4. Llamar core_pattern_extractor agent (PRO) ──────────
        response = llm.run_agent(
            "core_pattern_extractor",
            variables={
                "document_name": doc_name,
                "incidents_text": incidents_text,
                "object_of_study": object_of_study,
                "operational_question": operational_question or "(not yet generated)",
            },
        )

        # ── 5. Validar respuesta ──────────────────────────────────────
        if response.get("mock_note") or response.get("error"):
            logger.warning(
                "extract_core_pattern: LLM fallback/mock para doc=%s — %s",
                documento_id[:8],
                response.get("mock_note", response.get("error", "")),
            )
            core_pattern = response.get("core_pattern", "[MOCK] Patrón sintetizado")
            description = response.get("description", "[MOCK] Síntesis no disponible.")
            evidence_quotes = response.get("evidence_quotes", [])
            confidence = response.get("confidence", "LOW")
            mock = True
        else:
            core_pattern = (response.get("core_pattern") or "").strip()
            description = (response.get("description") or "").strip()
            evidence_quotes = response.get("evidence_quotes") or []
            confidence = response.get("confidence", "LOW")
            mock = False

        if not core_pattern:
            logger.warning(
                "extract_core_pattern: core_pattern vacío para doc=%s",
                documento_id[:8],
            )
            core_pattern = "(patrón no identificado)"
            confidence = "LOW"

        # ── 6. UPSERT en document_processes ───────────────────────────
        evidence_json = json.dumps(evidence_quotes)
        key_incident_ids = response.get("key_incident_ids", [])

        existing = session.execute(
            text(
                "SELECT id FROM document_processes "
                "WHERE documento_id = :did AND proyecto_id = :pid"
            ),
            {"did": documento_id, "pid": proyecto_id},
        ).fetchone()

        if existing:
            # UPDATE
            dp_id = str(existing[0])
            session.execute(
                text(
                    "UPDATE document_processes "
                    "SET process_description = :pd, "
                    "prime_mover = :pm, "
                    "prime_mover_confidence = :pmc "
                    "WHERE id = :dpid"
                ),
                {
                    "pd": f"{core_pattern}\n\n{description}",
                    "pm": evidence_json,
                    "pmc": confidence,
                    "dpid": dp_id,
                },
            )
            logger.info(
                "extract_core_pattern: actualizado document_processes %s",
                dp_id[:8],
            )
        else:
            # INSERT
            result = session.execute(
                text(
                    "INSERT INTO document_processes "
                    "(id, documento_id, proyecto_id, process_description, "
                    "prime_mover, prime_mover_confidence) "
                    "VALUES (gen_random_uuid(), :did, :pid, :pd, :pm, :pmc) "
                    "RETURNING id"
                ),
                {
                    "did": documento_id,
                    "pid": proyecto_id,
                    "pd": f"{core_pattern}\n\n{description}",
                    "pm": evidence_json,
                    "pmc": confidence,
                },
            )
            dp_id = str(result.fetchone()[0])
            logger.info(
                "extract_core_pattern: insertado document_processes %s",
                dp_id[:8],
            )

        session.commit()

        # ── 7. Vincular incidentes al document_process ─────────────────
        linked = 0
        if key_incident_ids:
            for iid in key_incident_ids:
                try:
                    session.execute(
                        text(
                            "UPDATE extracted_incidents "
                            "SET patrón_documento_id = :dpid "
                            "WHERE id = :iid AND documento_id = :did"
                        ),
                        {"dpid": dp_id, "iid": iid, "did": documento_id},
                    )
                    linked += 1
                except Exception:
                    pass
        else:
            # Vincular todos los incidentes del documento
            result = session.execute(
                text(
                    "UPDATE extracted_incidents "
                    "SET patrón_documento_id = :dpid "
                    "WHERE documento_id = :did"
                ),
                {"dpid": dp_id, "did": documento_id},
            )
            linked = result.rowcount or 0

        session.commit()
        logger.info(
            "extract_core_pattern: %d incidentes vinculados a dp=%s",
            linked,
            dp_id[:8],
        )

        return {
            "document_process_id": dp_id,
            "documento_id": documento_id,
            "core_pattern": core_pattern,
            "description": description,
            "evidence_quotes": evidence_quotes,
            "confidence": confidence,
            "incident_count": inc_count,
            "linked_incidents": linked,
            "mock": mock,
        }

    except Exception:
        logger.exception(
            "extract_core_pattern: error en doc=%s proyecto=%s",
            documento_id,
            proyecto_id,
        )
        return {"error": "exception", "documento_id": documento_id}
    finally:
        session.close()
