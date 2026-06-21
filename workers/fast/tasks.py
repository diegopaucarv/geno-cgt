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
import sys
from typing import List
from uuid import UUID

from celery import Celery
from config import REDIS_URL, TEI_URL
from sqlalchemy import text

sys.path.insert(0, "/app")

# ── Usamos el mismo LLMClient y database que el worker-heavy ──
from database import SessionLocal
from llm_client import LLMClient

logger = logging.getLogger(__name__)

app = Celery("fast_tasks", broker=REDIS_URL, backend=REDIS_URL)
llm = LLMClient()

# ═══════════════════════════════════════════════════════════════════════
# GraphRAG: Extracción de entidades y relaciones
# ═══════════════════════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = """[ROL]
Eres un extractor de entidades y relaciones para investigación cualitativa (Grounded Theory).

[TAREA]
Del siguiente segmento del documento, extrae:
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
            agent_id="util_graph_entity_extractor",
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


# ═══════════════════════════════════════════════════════════════════════
# Punctuation agent — añade puntuación a textos crudos (FLASH)
# ═══════════════════════════════════════════════════════════════════════


import signal as _signal

from celery import Task as _CeleryTask


class AbortableTask(_CeleryTask):
    """Tarea Celery que puede ser abortada limpiamente con SIGTERM."""

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
        logger.warning("Task %s received SIGTERM", self.name)
        if self._original_sigterm:
            _signal.signal(_signal.SIGTERM, self._original_sigterm)
        raise Exception(f"Task {self.name} cancelled by SIGTERM")


@app.task(name="punctuate_text", base=AbortableTask, bind=True)
def punctuate_text(
    self,
    texto: str,
    max_chars: int = 3000,
    documento_id: str = "",
) -> dict:
    """
    Anade puntuacion a texto crudo de documentos.
    Si el texto excede max_chars, lo divide en bloques y procesa iterativamente.
    Si se proporciona documento_id, actualiza el texto en la DB tras la puntuacion.
    """
    texto = texto.strip()
    if not texto:
        return {"punctuated_text": "", "changes_made": False}

    # ── Estado: marcar inicio de preprocesamiento ──
    if documento_id:
        session = SessionLocal()
        try:
            session.execute(
                text("UPDATE documentos SET estado = 'preprocesando' WHERE id = :did"),
                {"did": documento_id},
            )
            session.commit()
            logger.info("Preprocessing started for doc=%s", documento_id)
        except Exception as e:
            logger.warning("Failed to set estado=preprocesando: %s", e)
            session.rollback()
        finally:
            session.close()

    # Pre-corrección: intentar recuperar encoding Latin-1 mal interpretado como UTF-8
    try:
        fixed = texto.encode("latin-1", errors="replace").decode(
            "utf-8", errors="replace"
        )
        if fixed.count(chr(65533)) < texto.count(chr(65533)):
            logger.info(
                "Punctuator: encoding reparado (%d→%d U+FFFD)",
                texto.count(chr(65533)),
                fixed.count(chr(65533)),
            )
            texto = fixed
    except Exception:
        pass

    logger.info("Punctuator: recibido %d chars. Muestra: %s", len(texto), texto[:80])

    def _safe_punctuate(
        raw: str, expected_len: int | None = None, attempt: int = 0
    ) -> dict:
        """Llama al punctuator y valida integridad del texto."""
        try:
            response = llm.run_agent(
                "util_punctuator",
                variables={"raw_text": raw},
                temperature=0.3,
            )
        except Exception as e:
            logger.error("Punctuator LLM call failed: %s", e)
            raise
        out = response.get("punctuated_text", raw)
        # Usar expected_len si se proporciona (bloques con overlap)
        compare_len = expected_len if expected_len is not None else len(raw)
        ratio = len(out) / max(compare_len, 1)

        # Guardrail 1: texto truncado (<80%)
        if ratio < 0.8:
            return _handle_bad_output(
                raw, out, ratio, "TRUNCACIÓN", attempt, expected_len
            )

        # Guardrail 2: alucinación — texto inflado (>120%)
        if ratio > 1.2:
            return _handle_bad_output(
                raw, out, ratio, "INFLADO (posible alucinación)", attempt, expected_len
            )

        return response

    def _handle_bad_output(
        raw: str,
        out: str,
        ratio: float,
        label: str,
        attempt: int,
        expected_len: int | None = None,
    ) -> dict:
        logger.warning(
            "Punctuator: %s (%.0f%%). Intento %d…",
            label,
            ratio * 100,
            attempt + 1,
        )
        if attempt >= 2:
            # No revertir — guardar el texto preprocesado igual, marcando el warning
            logger.warning(
                "Punctuator: %s tras %d intentos. Guardando con advertencia.",
                label,
                attempt + 1,
            )
            return {
                "punctuated_text": out,
                "changes_made": True,
                "warning": f"{label} ({ratio * 100:.0f}%% del original)",
            }
        warn = (
            "\n\n[ADVERTENCIA CRÍTICA]\n"
            f"La salida es {ratio * 100:.0f}%% del original. "
            "SOLO añade puntuación y mayúsculas. "
            "Mantén el texto IDÉNTICO en contenido y longitud. "
            "Devuelve el texto COMPLETO con la puntuación corregida."
        )
        return _safe_punctuate(raw + warn, expected_len, attempt + 1)

    try:
        # Si el texto es corto, procesar en una sola llamada
        if len(texto) <= max_chars:
            response = _safe_punctuate(texto)
            result = {
                "punctuated_text": response.get("punctuated_text", texto),
                "changes_made": response.get("changes_made", False),
            }
        else:
            # Texto largo: dividir en bloques por límites semánticos naturales
            paragraphs = texto.split("\n")
            blocks = []
            current = ""
            for p in paragraphs:
                if len(current) + len(p) < max_chars:
                    current += p + "\n"
                else:
                    if current:
                        blocks.append(current.strip())
                    # Si el párrafo es más largo que max_chars, buscar el último punto
                    if len(p) > max_chars:
                        sub = p
                        while len(sub) > max_chars:
                            # Buscar el último . o ? o ! antes del límite
                            cut = max_chars
                            for sep in [". ", "? ", "! ", ".\n", ".\r"]:
                                idx = sub.rfind(sep, 0, max_chars)
                                if idx > max_chars // 2:
                                    cut = idx + len(sep)
                                    break
                            blocks.append(sub[:cut].strip())
                            sub = sub[cut:].strip()
                        current = sub + "\n"
                    else:
                        current = p + "\n"
            if current:
                blocks.append(current.strip())

            logger.info(
                "Punctuator: %d chars -> %d blocks (max_chars=%d)",
                len(texto),
                len(blocks),
                max_chars,
            )

            # Procesar bloques en paralelo
            from concurrent.futures import ThreadPoolExecutor, as_completed

            punctuated_blocks = [""] * len(blocks)
            changes = False

            with ThreadPoolExecutor(max_workers=4) as executor:
                future_to_idx = {}
                for i, block in enumerate(blocks):
                    # Añadir overlap: últimas 2-3 oraciones del bloque anterior
                    if i > 0:
                        prev = blocks[i - 1]
                        # Buscar los últimos 200 chars que empiecen en un límite natural
                        overlap_start = max(0, len(prev) - 300)
                        for sep in [". ", "? ", "! ", ".\n"]:
                            idx = prev.rfind(sep, overlap_start)
                            if idx >= 0:
                                overlap_start = idx + len(sep)
                                break
                        overlap = prev[overlap_start:]
                        if overlap:
                            block = overlap + "\n\n[CONTINÚA AQUÍ]\n\n" + block

                    future_to_idx[
                        executor.submit(_safe_punctuate, block, len(blocks[i]))
                    ] = i

                for future in as_completed(future_to_idx):
                    i = future_to_idx[future]
                    try:
                        response = future.result()
                        out = response.get("punctuated_text", blocks[i])
                        # Quitar overlap del output
                        if i > 0:
                            out_parts = out.split("[CONTINÚA AQUÍ]")
                            if len(out_parts) > 1:
                                out = out_parts[-1].strip()
                        punctuated_blocks[i] = out
                        if response.get("changes_made", False):
                            changes = True
                    except Exception as e:
                        logger.warning(
                            "Punctuator: bloque %d falló: %s. Usando original.", i, e
                        )
                        punctuated_blocks[i] = blocks[i]

            result = {
                "punctuated_text": "\n\n".join(punctuated_blocks),
                "changes_made": changes,
                "blocks_processed": len(blocks),
            }

        # Validación final: advertir si hay pérdida pero guardar igual
        final_text = result["punctuated_text"]
        if len(final_text) < len(texto) * 0.8:
            logger.warning(
                "Punctuator: PÉRDIDA de texto (%.0f%% → %.0f%%). Guardando con advertencia.",
                len(texto),
                len(final_text),
            )
            result["warning"] = (
                f"Texto reducido al {len(final_text) / max(len(texto), 1) * 100:.0f}%% del original"
            )

        # Always persist — worker is the authority on estado transitions
        if documento_id:
            logger.info(
                "Punctuator: guardando. OUT muestra: %s", result["punctuated_text"][:80]
            )
            session = SessionLocal()
            try:
                import json as _json

                # Get current metadatos
                row = session.execute(
                    text("SELECT metadatos FROM documentos WHERE id = :did"),
                    {"did": documento_id},
                ).fetchone()
                if row:
                    meta = row[0] if row[0] else {}
                    if isinstance(meta, str):
                        meta = _json.loads(meta)
                    # Preservar texto_original si no existe aún
                    if "texto_original" not in meta:
                        meta["texto_original"] = meta.get("texto_extraido", "")
                    meta["texto_preprocesado"] = result["punctuated_text"]
                    meta["texto_puntuado"] = True
                    if result.get("warning"):
                        meta["preprocess_warning"] = result["warning"]
                    session.execute(
                        text("UPDATE documentos SET metadatos = :meta WHERE id = :did"),
                        {"meta": _json.dumps(meta), "did": documento_id},
                    )
                    session.execute(
                        text(
                            "UPDATE documentos SET estado = 'preprocesado' WHERE id = :did"
                        ),
                        {"did": documento_id},
                    )
                    session.execute(
                        text(
                            "INSERT INTO document_stage_progress (documento_id, agent_id) "
                            "VALUES (:did, 'util_punctuator') ON CONFLICT DO NOTHING"
                        ),
                        {"did": documento_id},
                    )
                    session.commit()
                    logger.info(
                        "Punctuator: updated doc %s with punctuated text",
                        documento_id,
                    )
                    logger.info("Preprocessing completed for doc=%s", documento_id)
            except Exception as e:
                logger.warning("Punctuator DB update failed: %s", e)
                session.rollback()
            finally:
                session.close()

    except Exception as e:
        logger.error("Punctuator task failed: %s", e)
        if documento_id:
            session = SessionLocal()
            try:
                session.execute(
                    text("UPDATE documentos SET estado = 'error' WHERE id = :did"),
                    {"did": documento_id},
                )
                session.commit()
            except Exception as db_err:
                logger.warning("Failed to set estado=error: %s", db_err)
                session.rollback()
            finally:
                session.close()
        raise

    return result


# ═══════════════════════════════════════════════════════════════════════
# F0: Population Generalizer — ejecutado después del HITL gate de open coding
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="generalize_population", queue="fast")
def generalize_population(proyecto_id: str):
    """F0: Generaliza la población después del HITL gate de open coding.

    Toma chosen_population (elegida por el investigador en el HITL gate)
    y la research_question del proyecto, y produce:
      - spatial_frame
      - temporal_frame
      - generalized_population

    Guarda el resultado en proyectos.population_assumption (JSONB).
    """
    session = SessionLocal()
    try:
        # ── 1. Obtener chosen_population y research_question ──────────
        row = session.execute(
            text(
                "SELECT chosen_population, supuesto_poblacional "
                "FROM proyectos WHERE id = :pid"
            ),
            {"pid": proyecto_id},
        ).fetchone()

        if not row:
            logger.error("Project %s not found for generalize_population", proyecto_id)
            return {"error": "Project not found", "proyecto_id": proyecto_id}

        chosen_population = row[0]
        research_question = row[1] or ""

        if not chosen_population:
            logger.info(
                "No chosen_population for project %s, skipping population generalization",
                proyecto_id,
            )
            return {
                "status": "skipped",
                "reason": "no chosen_population",
                "proyecto_id": proyecto_id,
            }

        # ── 2. Llamar al LLM con el agente population_generalizer ─────
        logger.info(
            "Generalizing population for project=%s: %s",
            proyecto_id,
            chosen_population[:120],
        )

        response = llm.run_agent(
            "population_generalizer",
            variables={
                "chosen_population": chosen_population,
                "research_question": research_question,
            },
        )

        spatial_frame = response.get("spatial_frame")
        temporal_frame = response.get("temporal_frame")
        generalized_population = response.get("generalized_population")
        rationale = response.get("rationale", "")

        if not spatial_frame or not temporal_frame or not generalized_population:
            logger.warning(
                "Incomplete population generalization for project=%s: %s",
                proyecto_id,
                response,
            )

        # ── 3. Leer population_assumption actual (si existe) ──────────
        existing_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()

        import json as _json

        current_assumption = {}
        if existing_row and existing_row[0]:
            current_assumption = (
                existing_row[0]
                if isinstance(existing_row[0], dict)
                else _json.loads(existing_row[0])
            )

        # ── 4. Merge y guardar ────────────────────────────────────────
        current_assumption["spatial_frame"] = spatial_frame
        current_assumption["temporal_frame"] = temporal_frame
        current_assumption["generalized_population"] = generalized_population
        if rationale:
            current_assumption["population_generalization_rationale"] = rationale

        session.execute(
            text("UPDATE proyectos SET population_assumption = :pa WHERE id = :pid"),
            {
                "pa": _json.dumps(current_assumption),
                "pid": proyecto_id,
            },
        )
        session.commit()

        logger.info(
            "Population generalized for project=%s: spatial=%s temporal=%s",
            proyecto_id,
            spatial_frame,
            temporal_frame,
        )

        return {
            "status": "ok",
            "proyecto_id": proyecto_id,
            "spatial_frame": spatial_frame,
            "temporal_frame": temporal_frame,
            "generalized_population": generalized_population,
        }

    except Exception as e:
        logger.error("generalize_population failed for project=%s: %s", proyecto_id, e)
        session.rollback()
        return {"error": str(e), "proyecto_id": proyecto_id}
    finally:
        session.close()
