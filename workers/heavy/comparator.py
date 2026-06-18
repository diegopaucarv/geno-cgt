"""
B1 — Incident Comparator (PRO, 1-pass con pre-filtro por embedding).

Compara incidentes extraidos (extracted_incidents) para evaluar
intercambiabilidad entre pares. NO ve categorias ni etiquetas existentes.

Pipeline de 3 pasos:
  1. Pre-filtro por embedding (algoritmico, sin LLM): solo pares con cosine > 0.75
  2. Batch comparison (PRO, con batching): solo los pares sobrevivientes
  3. Union-Find (algoritmico): agrupa pares intercambiables en incident_groups

Refs: 6-ContextWindowManager.md 3.1, AGENTES.md incident_comparator.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()

COSINE_THRESHOLD = 0.75
BATCH_SIZE = 25  # pares por llamada LLM


def _parse_embedding(emb) -> list[float] | None:
    """Parsea embedding de pgvector (viene como string '[0.1, 0.2, ...]' o ya como lista)."""
    if emb is None:
        return None
    if isinstance(emb, list):
        return emb
    if isinstance(emb, str):
        try:
            return [float(x.strip()) for x in emb.strip("[]").split(",")]
        except (ValueError, AttributeError):
            return None
    return None


def b1_compare_incidents(proyecto_id: str, incremental: bool = False) -> dict:
    """Compara incidentes para evaluar intercambiabilidad.

    Paso 1: Pre-filtro por embedding cosine similarity (algoritmico)
    Paso 2: Batch LLM comparison de pares candidatos
    Paso 3: Union-Find para construir grupos finales
    """
    session = SessionLocal()
    try:
        # ── Cargar incidentes con embeddings ──
        rows = session.execute(
            text(
                "SELECT ei.id, ei.jot_text, ei.preguntas_glaser_json, "
                "s.embedding, s.texto "
                "FROM extracted_incidents ei "
                "JOIN segmentos s ON ei.segmento_id = s.id "
                "WHERE ei.proyecto_id = :pid AND s.embedding IS NOT NULL "
                "ORDER BY ei.creado_en"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if len(rows) < 2:
            logger.info("B1: <2 incidents with embeddings — nothing to compare")
            return {"comparisons_created": 0, "groups_created": 0, "pairs_evaluated": 0}

        n = len(rows)
        total_pairs = n * (n - 1) // 2
        logger.info("B1: %d incidents → %d total pairs", n, total_pairs)

        # ── PASO 1: Pre-filtro por embedding (algoritmico) ──
        candidates = []
        embeddings_pairs = 0
        for i in range(n):
            emb_i = _parse_embedding(rows[i][3])
            if emb_i is None:
                continue
            for j in range(i + 1, n):
                emb_j = _parse_embedding(rows[j][3])
                if emb_j is None:
                    continue
                embeddings_pairs += 1
                sim = _cosine_similarity(emb_i, emb_j)
                if sim >= COSINE_THRESHOLD:
                    candidates.append(
                        {
                            "pair_id": f"{rows[i][0]}_{rows[j][0]}",
                            "incident_a_id": str(rows[i][0]),
                            "incident_b_id": str(rows[j][0]),
                            "a_jot": rows[i][1] or "",
                            "b_jot": rows[j][1] or "",
                            "a_text": rows[i][4][:400] if rows[i][4] else "",
                            "b_text": rows[j][4][:400] if rows[j][4] else "",
                            "similarity_score": round(sim, 4),
                        }
                    )

        pct = round(100 * len(candidates) / max(1, embeddings_pairs), 1)
        logger.info(
            "B1: Pre-filter: %d/%d pairs survive (%.1f%%), threshold=%.2f",
            len(candidates),
            embeddings_pairs,
            pct,
            COSINE_THRESHOLD,
        )

        if not candidates:
            logger.info("B1: No pairs survived pre-filter")
            return {"comparisons_created": 0, "groups_created": 0, "pairs_evaluated": 0}

        # ── PASO 2: Batch LLM comparison ──
        comparisons_created = 0
        batches = (len(candidates) + BATCH_SIZE - 1) // BATCH_SIZE
        logger.info(
            "B1: %d candidate pairs → %d LLM batches (batch_size=%d)",
            len(candidates),
            batches,
            BATCH_SIZE,
        )

        for batch_idx in range(batches):
            start = batch_idx * BATCH_SIZE
            end = min(start + BATCH_SIZE, len(candidates))
            batch = candidates[start:end]

            batch_json = json.dumps(batch, ensure_ascii=False)
            logger.info(
                "B1: Batch %d/%d — %d pairs", batch_idx + 1, batches, len(batch)
            )

            response = llm.run_agent(
                agent_id="fb_incident_comparator",
                variables={
                    "incidents_json": batch_json,
                    "strategy_note": (
                        f"Batch {batch_idx + 1}/{batches}. "
                        f"Evalua intercambiabilidad de estos {len(batch)} pares. "
                        "Responde SOLO con JSON."
                    ),
                },
            )

            # Persistir resultados del batch
            comps = response.get("comparisons", [])
            for comp in comps:
                try:
                    session.execute(
                        text(
                            "INSERT INTO incident_comparisons "
                            "(id, incident_a_id, incident_b_id, proyecto_id, "
                            " similarity_score, are_interchangeable, rationale) "
                            "VALUES (gen_random_uuid(), :a_id, :b_id, :pid, "
                            " :score, :interchangeable, :rationale)"
                        ),
                        {
                            "a_id": comp.get(
                                "incident_a_id", comp.get("incident_a", "")
                            ),
                            "b_id": comp.get(
                                "incident_b_id", comp.get("incident_b", "")
                            ),
                            "pid": proyecto_id,
                            "score": comp.get("similarity_score", 0.0),
                            "interchangeable": comp.get("are_interchangeable", False),
                            "rationale": comp.get("rationale", ""),
                        },
                    )
                    comparisons_created += 1
                except Exception as e:
                    logger.warning("B1: Failed to persist comparison: %s", e)

        session.commit()

        # ── PASO 3: Union-Find para construir grupos ──
        groups_created = _build_groups_from_comparisons(session, proyecto_id)

        logger.info(
            "B1 complete: %d comparisons, %d groups, %d pairs evaluated",
            comparisons_created,
            groups_created,
            len(candidates),
        )

        return {
            "comparisons_created": comparisons_created,
            "groups_created": groups_created,
            "pairs_evaluated": len(candidates),
            "total_pairs": total_pairs,
            "prefilter_pct": pct,
        }

    except Exception:
        session.rollback()
        logger.exception("B1 compare_incidents failed for project %s", proyecto_id)
        raise
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity entre dos vectores de embedding."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _build_groups_from_comparisons(session, proyecto_id: str) -> int:
    """Union-Find: agrupa incidentes marcados como intercambiables."""
    rows = session.execute(
        text(
            "SELECT incident_a_id, incident_b_id FROM incident_comparisons "
            "WHERE proyecto_id = :pid AND are_interchangeable = true"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # Union-Find
    parent = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x, y):
        parent[find(x)] = find(y)

    for a, b in rows:
        union(str(a), str(b))

    # Agrupar por raiz
    groups = defaultdict(list)
    for node in parent:
        groups[find(node)].append(node)

    # Persistir grupos (solo si tienen >= 2 incidentes)
    created = 0
    for root, members in groups.items():
        if len(members) < 2:
            continue
        session.execute(
            text(
                "INSERT INTO incident_groups "
                "(id, proyecto_id, label, definition, status, incident_ids_json) "
                "VALUES (gen_random_uuid(), :pid, NULL, '', 'open', :ids::jsonb) "
                "ON CONFLICT DO NOTHING"
            ),
            {"pid": proyecto_id, "ids": json.dumps(members)},
        )
        created += 1

    session.commit()
    logger.info(
        "B1 Union-Find: %d groups from %d interchangeable pairs", created, len(rows)
    )
    return created
