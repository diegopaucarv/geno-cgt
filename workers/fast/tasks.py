"""
Tareas rápidas: GraphRAG extraction, consultas atómicas, llamadas cortas a LLM.

Plan §2.3: Cola `fast_tasks` con 4 workers concurrentes.
Plan §6.2: GraphRAG — extraer entidades y relaciones vía Gemma 4 31B.

Las tareas aquí son atómicas y no requieren el grafo LangGraph.
El worker-fast ejecuta LLM calls de corta duración (< 5s).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import List
from uuid import UUID

from celery import Celery
from sqlalchemy import text

sys.path.insert(0, "/app")

# ── Usamos el mismo LLMClient y database que el worker-heavy ──
from database import SessionLocal
from llm_client import LLMClient

logger = logging.getLogger(__name__)

app = Celery("fast_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
llm = LLMClient()

# ═══════════════════════════════════════════════════════════════════════
# GraphRAG: Extracción de entidades y relaciones
# ═══════════════════════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = """[ROL]
Eres un extractor de entidades y relaciones para investigación cualitativa (Grounded Theory).

[TAREA]
Del siguiente segmento de entrevista, extrae:
1. ENTIDADES: personas, organizaciones, conceptos abstractos, eventos significativos.
   No extraigas entidades triviales (ej. "yo", "ellos" sin contexto).
2. RELACIONES entre entidades, clasificadas como:
   - CAUSA: A causa o provoca B
   - CONDICION: A es condición necesaria para B
   - CONSECUENCIA: A es consecuencia de B
   - OPOSICION: A se opone o contradice a B
   - COOCURRENCIA: A y B aparecen vinculados sin dirección causal clara

[REGLAS]
- Los nombres de entidades deben ser EXACTOS al texto original (no parafrasees).
- Si no hay entidades significativas, devuelve listas vacías.
- Si no hay relaciones claras, devuelve lista vacía.

[SEGMENTO]
{segment_text}

[OUTPUT FORMAT — responde SOLO en JSON]
{{"entities": [{{"name": "...", "type": "person|organization|concept|event"}}], "relations": [{{"source": "nombre exacto", "target": "nombre exacto", "type": "CAUSA|...", "rationale": "breve justificación en 1 oración"}}]}}"""


def _build_entity_prompt(segment_text: str) -> str:
    return ENTITY_EXTRACTION_PROMPT.format(segment_text=segment_text[:3000])


@app.task(name="extract_graph_entities")
def extract_graph_entities(segmento_id: str, proyecto_id: str) -> dict:
    """
    Extrae entidades y relaciones de un segmento usando Gemma 4 31B (EQUILIBRADO).

    Inserta/actualiza GraphEntity y GraphRelation en la DB.
    Llamado por el Coordinator tras la segmentación de cada documento.

    Returns:
        dict con {entities_found, relations_found, entity_ids}
    """
    session = SessionLocal()
    try:
        # 1. Obtener el texto del segmento
        row = session.execute(
            text("SELECT texto FROM segmentos WHERE id = :sid"),
            {"sid": segmento_id},
        ).fetchone()

        if not row:
            return {"error": "segmento no encontrado", "segmento_id": segmento_id}

        segment_text = row[0]
        if len(segment_text.strip()) < 50:
            return {
                "entities_found": 0,
                "relations_found": 0,
                "skipped": "texto muy corto",
            }

        # 2. Prompt al LLM
        prompt = _build_entity_prompt(segment_text)

        # Usamos tier POWERFUL para extracción precisa
        response = llm.run_agent(
            agent_id="graph_entity_extractor",
            variables={"segment_text": segment_text[:3000]},
            temperature=0.2,
        )

        # Si es mock, intentar parsear el prompt directo
        if response.get("mock_note"):
            return {
                "entities_found": 0,
                "relations_found": 0,
                "note": "mock — LLM no disponible",
            }

        entities = response.get("entities", [])
        relations = response.get("relations", [])

        # 3. Upsert entities
        entity_ids: dict[str, str] = {}
        for ent in entities:
            name = ent.get("name", "").strip()
            etype = ent.get("type", "concept")
            if not name or len(name) < 2:
                continue

            # Buscar existente por nombre + proyecto
            existing = session.execute(
                text(
                    "SELECT id, frequency FROM graph_entities "
                    "WHERE project_id = :pid AND name = :name"
                ),
                {"pid": proyecto_id, "name": name},
            ).fetchone()

            if existing:
                # Incrementar frecuencia
                session.execute(
                    text(
                        "UPDATE graph_entities SET frequency = frequency + 1 "
                        "WHERE id = :eid"
                    ),
                    {"eid": existing[0]},
                )
                entity_ids[name] = str(existing[0])
            else:
                # Insertar nueva entidad
                result = session.execute(
                    text(
                        "INSERT INTO graph_entities (id, project_id, name, type, frequency) "
                        "VALUES (gen_random_uuid(), :pid, :name, :type, 1) RETURNING id"
                    ),
                    {"pid": proyecto_id, "name": name, "type": etype},
                )
                new_id = str(result.fetchone()[0])
                entity_ids[name] = new_id

        # 4. Insert relations
        relations_found = 0
        for rel in relations:
            source_name = rel.get("source", "").strip()
            target_name = rel.get("target", "").strip()
            rel_type = rel.get("type", "COOCURRENCIA").strip().upper()

            if source_name not in entity_ids or target_name not in entity_ids:
                continue
            if source_name == target_name:
                continue

            # Validar tipo de relación
            valid_types = {
                "CAUSA",
                "CONDICION",
                "CONSECUENCIA",
                "OPOSICION",
                "COOCURRENCIA",
            }
            if rel_type not in valid_types:
                rel_type = "COOCURRENCIA"

            # Upsert relation (ON CONFLICT incrementa strength)
            session.execute(
                text(
                    "INSERT INTO graph_relations (source_id, target_id, relation_type, strength) "
                    "VALUES (:src, :tgt, :rtype, 1.0) "
                    "ON CONFLICT (source_id, target_id, relation_type) "
                    "DO UPDATE SET strength = graph_relations.strength + 0.5"
                ),
                {
                    "src": entity_ids[source_name],
                    "tgt": entity_ids[target_name],
                    "rtype": rel_type,
                },
            )
            relations_found += 1

        session.commit()

        return {
            "entities_found": len(entities),
            "entity_ids": list(entity_ids.values()),
            "relations_found": relations_found,
        }

    finally:
        session.close()


@app.task(name="batch_extract_graph")
def batch_extract_graph(documento_id: str, proyecto_id: str) -> dict:
    """
    Extrae entidades y relaciones de TODOS los segmentos de un documento.

    Llamado tras la segmentación (como paso post-segmentación en el pipeline).
    """
    session = SessionLocal()
    try:
        segments = session.execute(
            text(
                "SELECT id FROM segmentos WHERE documento_id = :did ORDER BY posicion"
            ),
            {"did": documento_id},
        ).fetchall()

        if not segments:
            return {"error": "documento sin segmentos"}

        total_entities = 0
        total_relations = 0

        for (seg_id,) in segments:
            result = extract_graph_entities(str(seg_id), proyecto_id)
            total_entities += result.get("entities_found", 0)
            total_relations += result.get("relations_found", 0)

        return {
            "documento_id": documento_id,
            "segmentos_procesados": len(segments),
            "total_entities": total_entities,
            "total_relations": total_relations,
        }

    finally:
        session.close()


@app.task(name="graphrag_search_local")
def graphrag_search_local(query: str, proyecto_id: str, top_k: int = 5) -> dict:
    """
    GraphRAG — búsqueda local (1-hop).

    1. Embed query → encontrar entidades cercanas (vía nombre textual)
    2. Recuperar segmentos donde aparecen esas entidades
    3. Incluir entidades relacionadas (1-hop via GraphRelation)

    Nota: Esta es una implementación naïve (búsqueda textual de entidades).
    La versión completa usará embedding de la query contra entity embeddings.
    """
    session = SessionLocal()
    try:
        # 1. Buscar entidades cuyos nombres contengan términos de la query
        query_terms = query.lower().split()
        entities = session.execute(
            text(
                "SELECT id, name, type, frequency FROM graph_entities "
                "WHERE project_id = :pid "
                "ORDER BY frequency DESC LIMIT 100"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        # Filtrar por relevancia textual simple
        matched = []
        for ent in entities:
            ent_name = ent[1].lower()
            score = sum(1 for t in query_terms if t in ent_name)
            if score > 0:
                matched.append((ent, score))

        matched.sort(key=lambda x: x[1], reverse=True)
        top_entities = matched[:top_k]

        # 2. Para cada entidad, buscar segmentos relacionados
        results = []
        for ent, score in top_entities:
            entity_id = str(ent[0])

            # Entidades relacionadas (1-hop)
            related = session.execute(
                text(
                    "SELECT ge.name, gr.relation_type, gr.strength "
                    "FROM graph_relations gr "
                    "JOIN graph_entities ge ON gr.target_id = ge.id "
                    "WHERE gr.source_id = :eid "
                    "UNION "
                    "SELECT ge.name, gr.relation_type, gr.strength "
                    "FROM graph_relations gr "
                    "JOIN graph_entities ge ON gr.source_id = ge.id "
                    "WHERE gr.target_id = :eid"
                ),
                {"eid": entity_id},
            ).fetchall()

            results.append(
                {
                    "entity": ent[1],
                    "type": ent[2],
                    "frequency": ent[3],
                    "relevance_score": score,
                    "related_entities": [
                        {"name": r[0], "relation": r[1], "strength": float(r[2])}
                        for r in related[:5]
                    ],
                }
            )

        return {"query": query, "results": results}

    finally:
        session.close()
