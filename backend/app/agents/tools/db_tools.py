"""Database tools — solo consultas SQL, sin dependencia de LLM.

Estas son las tools más básicas y seguras. No requieren conexión a
Together.ai ni a TEI. Solo leen de PostgreSQL a través de SQLAlchemy.

Usan sesiones sincrónicas para ser compatibles con workers Celery.
"""

from __future__ import annotations

import logging

from app.agents.tool_registry import tool

logger = logging.getLogger(__name__)


def _sync_session():
    """Obtiene una sesión sync para uso en workers Celery.

    El path /app se agrega a sys.path porque los workers ejecutan
    desde /app, no desde backend/.
    """
    import sys

    sys.path.insert(0, "/app")
    from database import SessionLocal  # type: ignore[import-not-found]

    return SessionLocal()


# ═══════════════════════════════════════════════════════════════════
# Tools
# ═══════════════════════════════════════════════════════════════════


@tool(
    name="get_all_codes",
    description="Lista todos los códigos (categorías) del proyecto con sus "
    "definiciones. Útil para conocer qué códigos existen antes de "
    "generar nuevos o buscar relaciones.",
    parameters={
        "proyecto_id": "UUID del proyecto (obligatorio)",
    },
)
def get_all_codes(proyecto_id: str) -> dict:
    """Tool: listar todos los códigos de un proyecto."""
    from sqlalchemy import text

    s = _sync_session()
    try:
        codes = s.execute(
            text(
                "SELECT id, nombre, definicion "
                "FROM categorias WHERE proyecto_id = :pid "
                "ORDER BY puntaje_relevancia DESC, nombre"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        return {
            "total": len(codes),
            "codes": [
                {
                    "id": str(c[0]),
                    "nombre": c[1],
                    "definicion": (c[2] or "")[:200],
                }
                for c in codes
            ],
        }
    except Exception as e:
        logger.error("get_all_codes failed: %s", e)
        return {"error": str(e)}
    finally:
        s.close()


@tool(
    name="get_code_details",
    description="Obtiene la definición completa y los incidentes (segmentos "
    "codificados) de un código específico por su ID. Útil para "
    "entender en profundidad qué significa un código y qué "
    "evidencia lo respalda.",
    parameters={
        "code_id": "UUID del código a consultar",
    },
)
def get_code_details(code_id: str) -> dict:
    """Tool: obtener definición + incidentes de un código."""
    from sqlalchemy import text

    s = _sync_session()
    try:
        cat = s.execute(
            text(
                "SELECT nombre, definicion, version, es_central, "
                "estado_saturacion, puntaje_relevancia "
                "FROM categorias WHERE id = :cid"
            ),
            {"cid": code_id},
        ).fetchone()

        if not cat:
            return {"error": f"Código {code_id} no encontrado"}

        incidents = s.execute(
            text(
                "SELECT s.texto, d.original_filename "
                "FROM codigos_segmento cs "
                "JOIN segmentos s ON cs.segmento_id = s.id "
                "JOIN documentos d ON s.documento_id = d.id "
                "WHERE cs.categoria_id = :cid "
                "ORDER BY s.posicion "
                "LIMIT 10"
            ),
            {"cid": code_id},
        ).fetchall()

        return {
            "id": code_id,
            "nombre": cat[0],
            "definicion": cat[1] or "",
            "version": cat[2] or 1,
            "es_central": bool(cat[3]),
            "estado_saturacion": cat[4] or "ABIERTO",
            "puntaje_relevancia": cat[5] or 0,
            "incidentes": [
                {
                    "texto": (r[0] or "")[:300],
                    "documento": r[1] or "",
                }
                for r in incidents
            ],
            "total_incidentes": len(incidents),
        }
    except Exception as e:
        logger.error("get_code_details failed: %s", e)
        return {"error": str(e)}
    finally:
        s.close()


@tool(
    name="get_existing_hypotheses",
    description="Lista las hipótesis existentes del proyecto que no fueron "
    "rechazadas. Útil para evitar duplicar hipótesis y para "
    "construir sobre hallazgos previos.",
    parameters={
        "proyecto_id": "UUID del proyecto (obligatorio)",
    },
)
def get_existing_hypotheses(proyecto_id: str) -> dict:
    """Tool: listar hipótesis no rechazadas de un proyecto."""
    from sqlalchemy import text

    s = _sync_session()
    try:
        hyps = s.execute(
            text(
                "SELECT id, text, level, confidence, status "
                "FROM hypotheses "
                "WHERE project_id = :pid AND status != 'rejected' "
                "ORDER BY confidence DESC, creado_en DESC"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        return {
            "total": len(hyps),
            "hypotheses": [
                {
                    "id": str(h[0]),
                    "text": h[1],
                    "level": h[2],
                    "confidence": float(h[3]) if h[3] else 0.0,
                    "status": h[4],
                }
                for h in hyps
            ],
        }
    except Exception as e:
        logger.error("get_existing_hypotheses failed: %s", e)
        return {"error": str(e)}
    finally:
        s.close()
