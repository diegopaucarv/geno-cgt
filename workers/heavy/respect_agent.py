"""F5.6 — ReSpecAgent: Sistema de Re-especificacion Jerarquica.

Monitorea senales de que algo necesita revision (incidentes ambiguos,
etiquetas rechazadas, relaciones divergentes sin resolver, memos huerfanos,
ejes vacios) y sugiere bajar de nivel para re-examinar.

Refs: kb.md 10, 1-Refaccion open coding.md 20, AGENTES.md Transversales.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()

# ── Thresholds for re-specification signals ──
AMBIGUOUS_INCIDENT_THRESHOLD = 10  # >10 incidentes con confidence < 0.5
REJECTED_LABEL_THRESHOLD = 3  # >3 etiquetas rechazadas en critic
UNRESOLVED_DIVERGENCE_THRESHOLD = 2  # >2 relaciones divergentes sin resolver
ORPHAN_MEMO_THRESHOLD = 5  # >5 memos sin categoria vinculada


def evaluate_respec_signals(proyecto_id: str) -> dict:
    """Evalua todas las senales de re-especificacion para un proyecto.

    Returns:
        dict con {suggestions: [{level, direction, detail, severity}],
                  total_signals: int, needs_review: bool}
    """
    session = SessionLocal()
    suggestions = []

    try:
        # ── Senal 1: Incidentes ambiguos ──
        ambiguous = session.execute(
            text(
                "SELECT COUNT(*) FROM extracted_incidents "
                "WHERE proyecto_id = :pid "
                "AND preguntas_glaser_json->>'confidence' IS NOT NULL "
                "AND (preguntas_glaser_json->>'confidence')::float < 0.5"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if ambiguous > AMBIGUOUS_INCIDENT_THRESHOLD:
            suggestions.append(
                {
                    "level": "incident",
                    "direction": "down",
                    "detail": (
                        f"{ambiguous} incidentes con baja confianza. "
                        "Revisar la extraccion de incidentes — posible sesgo "
                        "en las preguntas de Glaser o cambio en el tipo de dato."
                    ),
                    "severity": "warning",
                }
            )

        # ── Senal 2: Etiquetas rechazadas ──
        rejected = session.execute(
            text(
                "SELECT COUNT(*) FROM incident_groups "
                "WHERE proyecto_id = :pid AND status = 'rejected'"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if rejected > REJECTED_LABEL_THRESHOLD:
            suggestions.append(
                {
                    "level": "category",
                    "direction": "down",
                    "detail": (
                        f"{rejected} grupos de incidentes con etiquetas rechazadas. "
                        "El pattern_labeler o label_critic pueden necesitar ajuste. "
                        "Revisar si los grupos estan bien formados."
                    ),
                    "severity": "critical" if rejected > 10 else "warning",
                }
            )

        # ── Senal 3: Relaciones divergentes sin resolver ──
        unresolved = session.execute(
            text(
                "SELECT COUNT(*) FROM conceptual_relationships "
                "WHERE project_id = :pid AND elaboration_status = 'tense' "
                "AND divergence_resolution IS NULL"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if unresolved > UNRESOLVED_DIVERGENCE_THRESHOLD:
            suggestions.append(
                {
                    "level": "relationship",
                    "direction": "down",
                    "detail": (
                        f"{unresolved} relaciones tensas sin resolver. "
                        "El elaboration_engine encontro evidencia divergente "
                        "que no ha sido integrada. Expandir relaciones afectadas."
                    ),
                    "severity": "warning",
                }
            )

        # ── Senal 4: Memos huerfanos ──
        orphans = session.execute(
            text(
                "SELECT COUNT(*) FROM memos "
                "WHERE proyecto_id = :pid "
                "AND id NOT IN (SELECT memo_id FROM elaboration_memos WHERE memo_id IS NOT NULL)"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if orphans > ORPHAN_MEMO_THRESHOLD:
            suggestions.append(
                {
                    "level": "memo",
                    "direction": "up",
                    "detail": (
                        f"{orphans} memos sin vincular a ninguna categoria o relacion. "
                        "Ejecutar ghost_blob_mapper para absorber memos huerfanos."
                    ),
                    "severity": "info",
                }
            )

        # ── Senal 5: Ejes vacios (paradigm dimensions sin contenido) ──
        empty_axes = session.execute(
            text(
                "SELECT COUNT(*) FROM paradigm_states ps "
                "WHERE ps.proyecto_id = :pid "
                "AND ps.did_state_expand = false "
                "AND ps.paradigm_snapshot IS NOT NULL "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM paradigm_states ps2 "
                "  WHERE ps2.code_id = ps.code_id AND ps2.did_state_expand = true"
                ")"
            ),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if empty_axes > 0:
            suggestions.append(
                {
                    "level": "paradigm",
                    "direction": "down",
                    "detail": (
                        f"{empty_axes} categorias sin expansiones paradigmaticas. "
                        "Posible saturacion prematura — TheoSampler puede ayudar."
                    ),
                    "severity": "warning" if empty_axes > 3 else "info",
                }
            )

        needs_review = any(s["severity"] == "critical" for s in suggestions)

        return {
            "suggestions": suggestions,
            "total_signals": len(suggestions),
            "needs_review": needs_review,
            "thresholds": {
                "ambiguous_incidents": AMBIGUOUS_INCIDENT_THRESHOLD,
                "rejected_labels": REJECTED_LABEL_THRESHOLD,
                "unresolved_divergence": UNRESOLVED_DIVERGENCE_THRESHOLD,
                "orphan_memos": ORPHAN_MEMO_THRESHOLD,
            },
        }

    except Exception:
        logger.exception("ReSpecAgent failed for project %s", proyecto_id)
        return {"suggestions": [], "total_signals": 0, "needs_review": False}
    finally:
        session.close()


def query_lower_level(
    entity_type: str,
    entity_id: str,
    direction: str = "down",
) -> dict:
    """Tool: baja un nivel de abstraccion para re-examinar.

    Args:
        entity_type: 'category', 'relationship', 'hypothesis', 'incident'
        entity_id: UUID de la entidad
        direction: 'down' (mas concreto) o 'up' (mas abstracto)

    Returns:
        dict con los datos del nivel inferior vinculados a esta entidad.
    """
    session = SessionLocal()
    try:
        if entity_type == "category" and direction == "down":
            # Bajar a incidentes que respaldan esta categoria
            incidents = session.execute(
                text(
                    "SELECT ei.id, ei.jot_text, s.texto, d.original_filename "
                    "FROM extracted_incidents ei "
                    "JOIN segmentos s ON ei.segmento_id = s.id "
                    "JOIN documentos d ON ei.documento_id = d.id "
                    "JOIN codigos_segmento cs ON cs.segmento_id = s.id "
                    "WHERE cs.categoria_id = :eid LIMIT 30"
                ),
                {"eid": entity_id},
            ).fetchall()

            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "direction": direction,
                "lower_level": "incidents",
                "data": [
                    {
                        "incident_id": str(r[0]),
                        "jot": r[1],
                        "text": r[2][:300],
                        "document": r[3],
                    }
                    for r in incidents
                ],
            }

        if entity_type == "relationship" and direction == "down":
            # Bajar a categorias que forman esta relacion
            rel = session.execute(
                text(
                    "SELECT category_ids, converging_incident_ids, "
                    "diverging_incident_ids FROM conceptual_relationships "
                    "WHERE id = :eid"
                ),
                {"eid": entity_id},
            ).fetchone()

            if not rel:
                return {"error": "Relationship not found"}

            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "direction": direction,
                "lower_level": "categories",
                "category_ids": rel[0] if isinstance(rel[0], list) else [],
                "converging_incidents": rel[1] if isinstance(rel[1], list) else [],
                "diverging_incidents": rel[2] if isinstance(rel[2], list) else [],
            }

        if entity_type == "incident" and direction == "up":
            # Subir: que categorias/grupos contienen este incidente
            groups = session.execute(
                text(
                    "SELECT ig.id, ig.label, ig.status FROM incident_groups ig "
                    "WHERE ig.incident_ids_json @> to_jsonb(ARRAY[:eid::text])"
                ),
                {"eid": entity_id},
            ).fetchall()

            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "direction": direction,
                "higher_level": "incident_groups",
                "groups": [
                    {"group_id": str(r[0]), "label": r[1], "status": r[2]}
                    for r in groups
                ],
            }

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "direction": direction,
            "message": f"No query defined for {entity_type}/{direction}",
        }

    except Exception:
        logger.exception("ReSpecTool query_lower_level failed")
        return {"error": "Query failed", "entity_type": entity_type}
    finally:
        session.close()
