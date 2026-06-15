"""
Calculadora Incremental de Saturación — Centroide Móvil + Rolling Std.

Plan §Fase 7: saturation_config con umbrales configurables.
Plan §2.2: métrica continua de novedad, no binaria.

Lógica:
  1. Tras cada batch de codificación (B2 assign codes), se dispara esta tarea.
  2. Para cada código activo, recalcula:
     - Centroide móvil: promedio de embeddings de segmentos asignados
     - Rolling std: desviación estándar de los últimos N segmentos vs centroide
     - documents_since_change: cuántos docs sin cambio significativo
  3. Decide estado: unsaturated → approaching → saturated
  4. Actualiza Categoria.embedding_centroide y SaturationMetrics.
"""

from __future__ import annotations

import logging
import math
import os
import sys
from typing import List
from uuid import UUID

from celery import Celery
from sqlalchemy import text

sys.path.insert(0, "/app")

from database import SessionLocal

logger = logging.getLogger(__name__)

app = Celery("nlp_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))

# ═══════════════════════════════════════════════════════════════
# Configuración por defecto (sobrescribible por saturation_config)
# ═══════════════════════════════════════════════════════════════

DEFAULT_WINDOW = 10  # últimos N segmentos para rolling std
DEFAULT_STD_THRESHOLD = 0.15  # por debajo → saturando
DEFAULT_DOCS_FOR_SATURATION = 3  # docs consecutivos sin cambio → saturado


def _cosine_distance(a: List[float], b: List[float]) -> float:
    """Distancia coseno entre dos vectores L2-normalizados."""
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    # Clamp para evitar errores de punto flotante
    dot = max(-1.0, min(1.0, dot))
    return 1.0 - dot


def _compute_centroid(embeddings: List[List[float]]) -> List[float]:
    """Centroide (promedio) de una lista de embeddings."""
    if not embeddings:
        return []
    dim = len(embeddings[0])
    return [sum(e[i] for e in embeddings) / len(embeddings) for i in range(dim)]


def _rolling_std(embeddings: List[List[float]], centroid: List[float]) -> float:
    """
    Desviación estándar de los embeddings respecto al centroide.

    Métrica de "novedad": si los nuevos segmentos se alejan mucho del
    centroide, la categoría no está saturada (siguen apareciendo variantes).
    """
    if not embeddings or not centroid:
        return 1.0

    distances = [_cosine_distance(emb, centroid) for emb in embeddings]
    mean_dist = sum(distances) / len(distances)
    variance = sum((d - mean_dist) ** 2 for d in distances) / len(distances)
    return math.sqrt(variance)


def _decide_status(
    rolling_std: float,
    docs_since_change: int,
    std_threshold: float = DEFAULT_STD_THRESHOLD,
    docs_for_sat: int = DEFAULT_DOCS_FOR_SATURATION,
) -> str:
    """
    Decide el estado de saturación basado en métricas continuas.

    unsaturated:  alta variabilidad (std alta) → siguen apareciendo novedades
    approaching:  variabilidad bajando (std media)
    saturated:    baja variabilidad (std baja) + docs consecutivos sin cambio
    """
    if rolling_std > std_threshold * 2:
        return "unsaturated"
    elif rolling_std > std_threshold:
        return "approaching"
    elif docs_since_change >= docs_for_sat:
        return "saturated"
    else:
        return "approaching"


# ═══════════════════════════════════════════════════════════════
# Tarea principal
# ═══════════════════════════════════════════════════════════════


@app.task(name="update_saturation")
def update_saturation(proyecto_id: str, code_id: str | None = None) -> dict:
    """
    Recalcula métricas de saturación para códigos de un proyecto.

    Si code_id es None, procesa todos los códigos del proyecto.
    Si code_id se especifica, solo ese código.

    Llamado tras cada batch de B2 (open coding + assign codes to segments).

    Returns:
        dict con {codes_processed, codes_saturated, codes_approaching, ...}
    """
    session = SessionLocal()
    try:
        # 1. Cargar configuración de saturación del proyecto
        config = session.execute(
            text("SELECT config_segmentacion FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()

        sat_config = {}
        if config and config[0]:
            sat_config = config[0] if isinstance(config[0], dict) else {}

        window = sat_config.get("sat_window", DEFAULT_WINDOW)
        std_threshold = sat_config.get("sat_std_threshold", DEFAULT_STD_THRESHOLD)
        docs_for_sat = sat_config.get(
            "sat_docs_for_saturation", DEFAULT_DOCS_FOR_SATURATION
        )

        # 2. Seleccionar códigos a procesar
        if code_id:
            codes = session.execute(
                text(
                    "SELECT id FROM categorias WHERE id = :cid AND proyecto_id = :pid"
                ),
                {"cid": code_id, "pid": proyecto_id},
            ).fetchall()
        else:
            codes = session.execute(
                text("SELECT id FROM categorias WHERE proyecto_id = :pid"),
                {"pid": proyecto_id},
            ).fetchall()

        if not codes:
            return {"codes_processed": 0, "reason": "sin códigos"}

        # 3. Para cada código, calcular métricas
        stats = {"unsaturated": 0, "approaching": 0, "saturated": 0}

        for (cid,) in codes:
            # 3a. Obtener últimos N segmentos asignados (ordenados por created_at)
            segments = session.execute(
                text("""
                    SELECT s.embedding
                    FROM codigos_segmento cs
                    JOIN segmentos s ON cs.segmento_id = s.id
                    WHERE cs.categoria_id = :cid AND s.embedding IS NOT NULL
                    ORDER BY cs.updated_at DESC
                    LIMIT :window
                """),
                {"cid": cid, "window": window},
            ).fetchall()

            embeddings = [r[0] for r in segments]

            if not embeddings:
                # Sin segmentos asignados → unsaturated
                session.execute(
                    text(
                        "UPDATE categorias SET estado_saturacion = 'unsaturated' "
                        "WHERE id = :cid"
                    ),
                    {"cid": cid},
                )
                stats["unsaturated"] += 1
                continue

            # 3b. Calcular centroide móvil
            centroid = _compute_centroid(embeddings)

            # 3c. Calcular rolling std
            std = _rolling_std(embeddings, centroid)

            # 3d. Determinar cuántos docs sin cambio significativo
            # (miramos la tabla saturation_metrics para el historial)
            prev = session.execute(
                text(
                    "SELECT documents_since_change, rolling_std FROM saturation_metrics "
                    "WHERE code_id = :cid"
                ),
                {"cid": cid},
            ).fetchone()

            prev_std = prev[1] if prev else None
            prev_docs = prev[0] if prev else 0

            # Si la std cambió significativamente (> 20% de cambio), reiniciamos contador
            if prev_std is not None and prev_std > 0:
                std_change = abs(std - prev_std) / prev_std
                if std_change > 0.20:
                    docs_since_change = 0
                else:
                    docs_since_change = prev_docs + 1
            else:
                docs_since_change = 0 if std > std_threshold else 1

            # 3e. Decidir estado
            status = _decide_status(std, docs_since_change, std_threshold, docs_for_sat)

            # 3f. Actualizar SaturationMetrics (upsert)
            session.execute(
                text("""
                    INSERT INTO saturation_metrics (code_id, centroid, rolling_std, saturation_status, documents_since_change)
                    VALUES (:cid, :cent, :std, :status, :docs)
                    ON CONFLICT (code_id)
                    DO UPDATE SET centroid = :cent2, rolling_std = :std2,
                                  saturation_status = :status2, documents_since_change = :docs2
                """),
                {
                    "cid": cid,
                    "cent": centroid,
                    "std": std,
                    "status": status,
                    "docs": docs_since_change,
                    "cent2": centroid,
                    "std2": std,
                    "status2": status,
                    "docs2": docs_since_change,
                },
            )

            # 3g. Actualizar embedding_centroide y estado en Categoria
            session.execute(
                text(
                    "UPDATE categorias SET embedding_centroide = :cent, "
                    "estado_saturacion = :status WHERE id = :cid"
                ),
                {"cent": centroid, "status": status, "cid": cid},
            )

            stats[status] = stats.get(status, 0) + 1

        session.commit()

        logger.info(
            "Saturation updated for project %s: %s",
            proyecto_id,
            stats,
        )

        return {
            "codes_processed": len(codes),
            "saturation_stats": stats,
            "config_used": {
                "window": window,
                "std_threshold": std_threshold,
                "docs_for_saturation": docs_for_sat,
            },
        }

    finally:
        session.close()


@app.task(name="get_saturation_report")
def get_saturation_report(proyecto_id: str) -> dict:
    """
    Genera un reporte de saturación legible para el frontend (Saturation Dashboard).

    Returns:
        dict con {codes: [{id, nombre, estado, std, docs_since_change}, ...]}
    """
    session = SessionLocal()
    try:
        rows = session.execute(
            text("""
                SELECT c.id, c.nombre, c.estado_saturacion,
                       sm.rolling_std, sm.documents_since_change,
                       c.puntaje_relevancia
                FROM categorias c
                LEFT JOIN saturation_metrics sm ON c.id = sm.code_id
                WHERE c.proyecto_id = :pid
                ORDER BY c.puntaje_relevancia DESC, sm.rolling_std ASC
            """),
            {"pid": proyecto_id},
        ).fetchall()

        codes = []
        for row in rows:
            codes.append(
                {
                    "id": str(row[0]),
                    "nombre": row[1],
                    "estado_saturacion": row[2] or "unsaturated",
                    "rolling_std": round(float(row[3]), 4)
                    if row[3] is not None
                    else None,
                    "docs_since_change": row[4] or 0,
                    "puntaje_relevancia": row[5] or 0,
                }
            )

        summary = {
            "total": len(codes),
            "saturated": sum(1 for c in codes if c["estado_saturacion"] == "saturated"),
            "approaching": sum(
                1 for c in codes if c["estado_saturacion"] == "approaching"
            ),
            "unsaturated": sum(
                1 for c in codes if c["estado_saturacion"] == "unsaturated"
            ),
        }

        return {"proyecto_id": proyecto_id, "summary": summary, "codes": codes}

    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# A1 — SQL Saturation Check (category saturator.json, Execute SQL query l.10)
# ═══════════════════════════════════════════════════════════════════════

@app.task(name="check_saturation_sliding_window")
def check_saturation_sliding_window(code_id: str, window: int = 5) -> dict:
    """
    Ventana deslizante de N iteraciones. bool_and(did_state_expand = FALSE).
    Si hay < N iteraciones, no esta saturado.
    """
    session = SessionLocal()
    try:
        row = session.execute(
            text("""
                WITH LastN AS (
                    SELECT did_state_expand
                    FROM paradigm_states
                    WHERE code_id = :cid
                    ORDER BY iteration DESC
                    LIMIT :win
                )
                SELECT
                    COUNT(*) AS n,
                    COUNT(*) = :win AND bool_and(did_state_expand = FALSE) AS saturated
                FROM LastN
            """),
            {"cid": code_id, "win": window},
        ).fetchone()

        return {
            "code_id": code_id,
            "iterations_in_window": row[0],
            "is_saturated": row[1] if row else False,
            "window_size": window,
        }
    finally:
        session.close()
