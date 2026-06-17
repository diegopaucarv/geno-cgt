"""Agentes CGT — Fase B: síntesis cross-documento (con prompt library)."""

from __future__ import annotations

import json
import logging
import os

from algorithmic_checks import (
    deduplicate_hypotheses,
    filter_empty_dimensions,
    prescreen_segments_against_codes,
)
from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()

# Lazy pgvector registration (needs psycopg2 connection available)
_vector_registered = False


def _ensure_vector_adapter():
    global _vector_registered
    if not _vector_registered:
        try:
            from pgvector.psycopg2 import register_vector

            register_vector()
            _vector_registered = True
        except Exception as e:
            logger.warning("pgvector adapter registration failed: %s", e)


# Feature flag para modo agencial (activar con AGENTIC_MODE=true)
AGENTIC_MODE = os.getenv("AGENTIC_MODE", "false").lower() in ("1", "true", "yes")


def _get_population_assumption(session, proyecto_id: str) -> str:
    row = session.execute(
        text("SELECT supuesto_poblacional FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if row and row[0]:
        return row[0]
    return "hábitos hipotéticos de comportamiento que procesan preocupaciones similares"


# ═══════════════════════════════════════════════════════════════════════
# B1: SAMPLING_DISTILLER
# ═══════════════════════════════════════════════════════════════════════


def _get_coding_style_instruction(session, proyecto_id: str) -> str:
    """Lee los coding_styles del proyecto y devuelve instruccion combinada."""
    config = session.execute(
        text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    style_keys = ["gerundio", "in_vivo"]  # default
    if config and config[0] and isinstance(config[0], dict):
        style_keys = config[0].get("coding_styles", style_keys)
        if isinstance(style_keys, str):
            style_keys = [style_keys]

    # Embedded instructions (avoid import dependency in worker)
    instructions = {
        "gerundio": "Nombra cada código con un GERUNDIO (-ando/-iendo). Ej: 'Negociando límites'.",
        "nominalizacion": "Nombra cada código con un SUSTANTIVO derivado de verbo (-ción, -miento). Ej: 'Negociación de límites'.",
        "parafrasis": "Nombra cada código con una FRASE CORTA descriptiva (3-8 palabras). Ej: 'El algoritmo decide sin consultar'.",
        "tema_subtema": "Nombra cada código como TEMA → subtema. Ej: 'Control algorítmico → Resistencia'.",
        "causal": "Nombra cada código como CADENA CAUSAL (A → B). Ej: 'Falta de transparencia → Desconfianza'.",
        "in_vivo": "Nombra cada código con una CITA TEXTUAL del entrevistado (entre comillas). Ej: '\"cada uno tiene su maña\"'.",
    }
    if len(style_keys) == 1:
        return instructions.get(style_keys[0], instructions["gerundio"])
    return (
        "Puedes usar CUALQUIERA de estos estilos:\n"
        + "\n".join(f"  • {instructions[k]}" for k in style_keys if k in instructions)
        + "\n\nElige el más adecuado para cada código según el contenido."
    )


def b1_distill_sampling(proyecto_id: str) -> dict:
    session = SessionLocal()
    try:
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
        codes = session.execute(
            text("SELECT nombre, definicion FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        processes_text = "\n".join(
            f"Doc {i + 1}: {p[0]}" for i, p in enumerate(processes)
        )
        codes_text = (
            "\n".join(f"- {c[0]}: {c[1]}" for c in codes) if codes else "(sin códigos)"
        )

        response = llm.run_agent(
            agent_id="b1",
            variables={
                "population_assumption": pop_assumption,
                "population_context": pop_ctx[0] if pop_ctx else "",
                "processes": processes_text,
                "codes": codes_text,
            },
            temperature=0.4,
        )

        memo_count = 0
        for dim in response.get("sampling_dimensions", []):
            content = f"Dimensión: {dim.get('name')}\n{dim.get('description')}\nContraste: {dim.get('contrast_criteria')}\nExtremos: {dim.get('extreme_criteria')}\nConsistentes: {dim.get('consistent_criteria')}"
            session.execute(
                text(
                    "INSERT INTO memos (id, proyecto_id, autor_id, tipo, estado, contenido, hash_tema, es_confidencial) VALUES (gen_random_uuid(), :pid, (SELECT creador_id FROM proyectos WHERE id=:pid2), 'MUESTREO', 'ABIERTO', :content, NULL, false)"
                ),
                {"pid": proyecto_id, "pid2": proyecto_id, "content": content},
            )
            memo_count += 1

        raw_dimensions = response.get("sampling_dimensions", [])
        filtered_dimensions = filter_empty_dimensions(raw_dimensions)
        discarded = len(raw_dimensions) - len(filtered_dimensions)
        session.commit()
        return {
            "sampling_dimensions": filtered_dimensions,
            "dimensions_discarded": discarded,
            "memos_created": memo_count,
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# B2: OPEN_CODER — Chain B2a (FLASH) → B2b (PRO)
# ═══════════════════════════════════════════════════════════════════════


def _b2a_extract_indicators(segments_text: str) -> dict:
    """B2a (FLASH): Extrae indicadores de comportamiento de segmentos."""
    return llm.run_agent(
        agent_id="b2a", variables={"segments": segments_text}, temperature=0.2
    )


def _b2b_generate_codes(
    pop_assumption: str, pop_context: str, existing_codes: str, indicators_text: str
) -> dict:
    """B2b (PRO): Genera códigos en gerundio a partir de indicadores pre-extraídos."""
    return llm.run_agent(
        agent_id="b2b",
        variables={
            "population_assumption": pop_assumption,
            "population_context": pop_context,
            "existing_codes": existing_codes,
            "indicators": indicators_text,
        },
        temperature=0.3,
    )


def _enrich_codes_with_evidence(codes: list[dict], proyecto_id: str) -> list[dict]:
    """Post-B2b enrichment: busca evidencia documental para cada código vía RAG.

    Para cada código generado por B2b:
      1. Usa nombre + definición como query
      2. search_segments(query, proyecto_id, top_k=8) → RRF (semántico + léxico)
      3. Filtra segmentos con score >= 0.5
      4. Agrupa por documento_id único
      5. puntaje_relevancia = COUNT(DISTINCT documentos con evidencia)
      6. Adjunta evidence: [{documento, documento_id, segmentos}]

    Args:
        codes: Lista de códigos crudos del LLM (con code_name, definition).
        proyecto_id: UUID del proyecto.

    Returns:
        Lista de códigos enriquecidos con puntaje_relevancia y evidence.
    """
    import sys as _sys

    _sys.path.insert(0, "/app")
    from app.agents.tools.search_tools import search_segments

    MIN_SCORE = 0.5

    enriched: list[dict] = []
    for code in codes:
        name = (code.get("code_name") or "").strip()
        definition = (code.get("definition") or "").strip()
        if not name or not definition:
            code["puntaje_relevancia"] = 0
            code["evidence"] = []
            enriched.append(code)
            continue

        # 1. Query rica: nombre + definición
        query = f"{name}: {definition}"

        # 2. Buscar segmentos vía RRF
        try:
            results = search_segments(query, proyecto_id, top_k=8)
        except Exception as e:
            logger.warning("Evidence enrichment failed for code '%s': %s", name, e)
            code["puntaje_relevancia"] = 0
            code["evidence"] = []
            enriched.append(code)
            continue

        if not results or (len(results) == 1 and "error" in results[0]):
            code["puntaje_relevancia"] = 0
            code["evidence"] = []
            enriched.append(code)
            continue

        # 3. Agrupar por documento_id único (score >= MIN_SCORE)
        doc_groups: dict[str, dict] = {}
        for r in results:
            score = r.get("score", 0)
            if score < MIN_SCORE:
                continue

            doc_id = r.get("documento_id", "unknown")
            doc_name = r.get("documento_nombre", "desconocido")

            if doc_id not in doc_groups:
                doc_groups[doc_id] = {
                    "documento": doc_name,
                    "documento_id": doc_id,
                    "segmentos": [],
                }

            doc_groups[doc_id]["segmentos"].append(
                {
                    "id": r.get("segmento_id", ""),
                    "texto": (r.get("texto") or "")[:300],
                    "score": round(score, 4),
                }
            )

        # 4. puntaje_relevancia = COUNT DISTINCT docs con evidencia
        code["puntaje_relevancia"] = len(doc_groups)
        code["evidence"] = list(doc_groups.values())

        enriched.append(code)

    return enriched


def b2_open_code(proyecto_id: str) -> dict:
    """
    Pipeline B2 completo:
    1. Pattern 1: pre-filtra segmentos contra códigos existentes (auto-asigna >0.85)
    2. B2a (FLASH): extrae indicadores de comportamiento
    3. B2b (PRO): genera códigos a partir de indicadores
    """
    session = SessionLocal()
    try:
        pop_assumption = _get_population_assumption(session, proyecto_id)
        pop_ctx = session.execute(
            text(
                "SELECT surprising_details FROM population_contexts WHERE proyecto_id = :pid ORDER BY version DESC LIMIT 1"
            ),
            {"pid": proyecto_id},
        ).fetchone()
        existing_codes = session.execute(
            text("SELECT nombre, definicion FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        codes_text = (
            "\n".join(f"- {c[0]}: {c[1]}" for c in existing_codes)
            if existing_codes
            else "(sin códigos)"
        )

        # ── Step 1: Pattern 1 — pre-filtrar (C05: baseline_data primero) ──
        unassigned_ids = session.execute(
            text(
                "SELECT s.id FROM segmentos s JOIN documentos d ON s.documento_id = d.id "
                "WHERE d.proyecto_id = :pid "
                "AND s.id NOT IN (SELECT segmento_id FROM codigos_segmento) "
                "ORDER BY CASE WHEN s.tipo_dato_glaser = 'baseline_data' THEN 0 "
                "WHEN s.tipo_dato_glaser IS NULL THEN 1 ELSE 2 END, s.posicion LIMIT 20"
            ),
            {"pid": proyecto_id},
        ).fetchall()
        unassigned_id_list = [str(r[0]) for r in unassigned_ids]

        prescreen = prescreen_segments_against_codes(
            unassigned_id_list, session, proyecto_id
        )
        auto_assigned = 0
        for item in prescreen["auto_assign"]:
            session.execute(
                text(
                    "INSERT INTO codigos_segmento (segmento_id, categoria_id, estado, confianza, origen) VALUES (:sid, :cid, 'asignado', :conf, 'ia') ON CONFLICT DO NOTHING"
                ),
                {
                    "sid": item["segment_id"],
                    "cid": item["code_id"],
                    "conf": item["score"],
                },
            )
            auto_assigned += 1
        if auto_assigned:
            session.commit()
            logger.info("Auto-asignados %d segmentos", auto_assigned)

        needs_llm_ids = list(prescreen["needs_new_code"])
        if prescreen["needs_confirmation"]:
            needs_llm_ids.extend(
                item["segment_id"] for item in prescreen["needs_confirmation"]
            )

        if not needs_llm_ids:
            session.commit()
            return {
                "codes_created": 0,
                "codes": [],
                "auto_assigned": auto_assigned,
                "b2a_indicators": 0,
            }

        # Cargar textos de segmentos que necesitan LLM
        unassigned = session.execute(
            text(
                "SELECT texto FROM segmentos WHERE id::text = ANY(:ids) ORDER BY posicion LIMIT 8"
            ),
            {"ids": needs_llm_ids[:10]},
        ).fetchall()
        segments_text = "\n---\n".join(r[0] for r in unassigned) if unassigned else ""

        # ── Step 2: B2a (FLASH) — extraer indicadores ──
        b2a_response = _b2a_extract_indicators(segments_text)
        indicators_list = b2a_response.get("indicators", [])
        indicators_text = (
            json.dumps(indicators_list, indent=2, ensure_ascii=False)
            if indicators_list
            else segments_text[:4000]
        )

        # ── Step 3: B2b (PRO) — generar códigos ──
        if AGENTIC_MODE:
            b2b_response = _b2b_generate_codes_agentic(
                pop_assumption=pop_assumption,
                pop_context=pop_ctx[0] if pop_ctx else "",
                existing_codes=codes_text,
                indicators_text=indicators_text,
            )
        else:
            b2b_response = _b2b_generate_codes(
                pop_assumption=pop_assumption,
                pop_context=pop_ctx[0] if pop_ctx else "",
                existing_codes=codes_text,
                indicators_text=indicators_text,
            )

        # ── Step 4: Enrich codes with documentary evidence (RAG search) ──
        raw_codes = b2b_response.get("codes", [])
        if raw_codes:
            enriched_codes = _enrich_codes_with_evidence(raw_codes, proyecto_id)
            avg_relevance = sum(
                c.get("puntaje_relevancia", 0) for c in enriched_codes
            ) / max(len(enriched_codes), 1)
            logger.info(
                "Evidence enrichment: %d codes, avg relevance=%.1f docs",
                len(enriched_codes),
                avg_relevance,
            )
        else:
            enriched_codes = []

        created = 0
        for code in enriched_codes:
            name = code.get("code_name", "").strip()
            definition = (code.get("definition") or "").strip()
            if not name or not definition:
                continue
            relevance = code.get("puntaje_relevancia", 0)
            session.execute(
                text(
                    "INSERT INTO categorias (id, proyecto_id, nombre, definicion, version, estado_saturacion, puntaje_relevancia, es_central) "
                    "VALUES (gen_random_uuid(), :pid, :name, :def, 1, 'ABIERTO', :relevance, false)"
                ),
                {
                    "pid": proyecto_id,
                    "name": name,
                    "def": definition,
                    "relevance": relevance,
                },
            )
            created += 1
        session.commit()

        return {
            "codes_created": created,
            "codes": enriched_codes,
            "auto_assigned": auto_assigned,
            "b2a_indicators": len(indicators_list),
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# B3: HYPOTHESIS_GENERATOR
# ═══════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════
# B2.5: GROUNDING — asignar códigos a segmentos vía similitud
# ═══════════════════════════════════════════════════════════════════════


def b2_5_assign_codes_to_segments(proyecto_id: str) -> dict:
    """
    Post-B2 grounding: asigna códigos (nuevos y existentes) a segmentos
    usando similitud de embeddings (pgvector cosine distance).

    Para cada código sin segmentos asignados:
      1. Genera embedding de su definición vía TEI
      2. Busca los top-5 segmentos más similares en el proyecto
      3. Inserta en codigos_segmento si similitud >= 0.60

    Llamado tras B2 (open coding). Si el código ya tiene segmentos asignados,
    no se re-asigna (respeta asignaciones existentes).
    """
    session = SessionLocal()
    try:
        # 1. Obtener códigos que NO tienen segmentos asignados aún
        codes = session.execute(
            text("""
                SELECT c.id, c.nombre, c.definicion
                FROM categorias c
                WHERE c.proyecto_id = :pid
                  AND c.id NOT IN (
                      SELECT DISTINCT categoria_id FROM codigos_segmento
                  )
                ORDER BY c.actualizado_en DESC
                LIMIT 30
            """),
            {"pid": proyecto_id},
        ).fetchall()

        if not codes:
            return {
                "codes_processed": 0,
                "segments_assigned": 0,
                "reason": "todos los códigos ya tienen segmentos",
            }

        # 2. Intentar embedder las definiciones vía TEI
        try:
            import requests

            tei_url = os.getenv("TEI_URL", "http://tei:8080")
            definitions = [f"{c[1]}: {c[2]}" for c in codes]
            resp = requests.post(
                f"{tei_url}/v1/embeddings",
                json={"input": definitions, "model": "voyageai/voyage-4-nano"},
                timeout=30.0,
            )
            resp.raise_for_status()
            embeddings = [item["embedding"] for item in resp.json()["data"]]
        except Exception as e:
            logger.warning("TEI no disponible para grounding: %s. Fallback a skip.", e)
            return {
                "codes_processed": 0,
                "segments_assigned": 0,
                "reason": f"TEI no disponible: {e}",
            }

        # 3. Para cada código, buscar segmentos similares y asignar
        total_assigned = 0
        codes_processed = 0

        for (code_id, code_name, code_def), code_emb in zip(codes, embeddings):
            _ensure_vector_adapter()  # register pgvector before first <=> query
            # Buscar top-5 segmentos más similares (con embedding)
            similar = session.execute(
                text("""
                    SELECT s.id, 1.0 - (s.embedding <=> :query_vec) AS score
                    FROM segmentos s
                    JOIN documentos d ON s.documento_id = d.id
                    WHERE d.proyecto_id = :pid
                      AND s.embedding IS NOT NULL
                    ORDER BY score DESC
                    LIMIT 5
                """),
                {"query_vec": code_emb, "pid": proyecto_id},
            ).fetchall()

            if not similar:
                continue

            assigned_for_code = 0
            for seg_row in similar:
                seg_id = str(seg_row[0])
                score = float(seg_row[1])

                if score < 0.60:
                    continue

                session.execute(
                    text(
                        "INSERT INTO codigos_segmento (segmento_id, categoria_id, estado, confianza, origen) "
                        "VALUES (:sid, :cid, 'asignado', :conf, 'ia') "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "sid": seg_id,
                        "cid": str(code_id),
                        "conf": round(score, 3),
                    },
                )
                assigned_for_code += 1

            if assigned_for_code > 0:
                codes_processed += 1
                total_assigned += assigned_for_code

        session.commit()
        logger.info(
            "Grounding: %d códigos asignados a %d segmentos",
            codes_processed,
            total_assigned,
        )

        # Actualizar puntaje_relevancia = COUNT(DISTINCT documentos)
        session.execute(
            text("""
                UPDATE categorias c SET puntaje_relevancia = (
                    SELECT COUNT(DISTINCT s.documento_id)
                    FROM codigos_segmento cs
                    JOIN segmentos s ON cs.segmento_id = s.id
                    WHERE cs.categoria_id = c.id
                )
                WHERE c.proyecto_id = :pid
            """),
            {"pid": proyecto_id},
        )
        session.commit()
        logger.info("Relevance scores updated for project %s", proyecto_id[:8])

        return {
            "codes_processed": codes_processed,
            "segments_assigned": total_assigned,
            "total_codes_without_segments": len(codes),
        }

    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# B3: HYPOTHESIS_GENERATOR
# ═══════════════════════════════════════════════════════════════════════


def b3_generate_hypotheses(proyecto_id: str) -> dict:
    session = SessionLocal()
    try:
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
        codes = session.execute(
            text("SELECT nombre, definicion FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        processes_text = "\n".join(
            f"Doc {i + 1}: {p[0]}" for i, p in enumerate(processes)
        )
        hyp_text = (
            "\n".join(f"- [{h[1]}] {h[0]}" for h in existing)
            if existing
            else "(sin hipótesis)"
        )
        codes_text = (
            "\n".join(f"- {c[0]}: {c[1]}" for c in codes) if codes else "(sin códigos)"
        )

        if AGENTIC_MODE:
            raw_hypotheses = b3_generate_hypotheses_agentic(
                proyecto_id,
                pop_assumption,
                pop_ctx[0] if pop_ctx else "",
                processes_text,
                codes_text,
                hyp_text,
            )
        else:
            response = llm.run_agent(
                agent_id="b3",
                variables={
                    "population_assumption": pop_assumption,
                    "population_context": pop_ctx[0] if pop_ctx else "",
                    "processes": processes_text,
                    "codes": codes_text,
                    "existing_hypotheses": hyp_text,
                },
                temperature=0.4,
            )
            raw_hypotheses = response.get("hypotheses", [])
        filtered = deduplicate_hypotheses(raw_hypotheses, session, proyecto_id)
        created = 0
        reinforced = 0
        for hyp in filtered:
            hyp_text = hyp.get("text", "").strip()
            if not hyp_text:
                continue
            if hyp.get("dedup_status") == "reinforced":
                reinforced += 1
                continue
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
            created += 1
        session.commit()
        return {
            "hypotheses_created": created,
            "hypotheses_reinforced": reinforced,
            "hypotheses": response.get("hypotheses", []),
        }
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Agentic versions (AGENTIC_MODE=true)
# ═══════════════════════════════════════════════════════════════════════


def _b2b_generate_codes_agentic(
    pop_assumption: str, pop_context: str, existing_codes: str, indicators_text: str
) -> dict:
    """B2b agentic: SelfRefinementLoop (Generate -> Critic -> Refine).

    Reemplaza la llamada single-shot _b2b_generate_codes() cuando
    AGENTIC_MODE=true. Usa PRO para generar y FLASH para evaluar.
    """
    import sys as _sys

    _sys.path.insert(0, "/app")
    from app.agents.self_refiner import SelfRefinementLoop

    loop = SelfRefinementLoop(
        agent_id="b2b",
        llm_client=llm,
        generate_prompt_id="b2b",
        critic_prompt_id="code_critic",
        max_iterations=3,
        timeout_seconds=300.0,
    )

    result = loop.run(
        project_id="b2b_batch",
        generate_vars={
            "population_assumption": pop_assumption,
            "population_context": pop_context,
            "existing_codes": existing_codes,
            "indicators": indicators_text,
        },
    )

    if result.success:
        logger.info(
            "Agentic B2b: %d codes in %d iterations (reasoning=%s)",
            len(result.data.get("codes", [])),
            result.iterations,
            result.had_reasoning,
        )
        return result.data

    # Fallback to single-shot on failure
    logger.warning("Agentic B2b failed: %s. Falling back to single-shot.", result.error)
    return _b2b_generate_codes(
        pop_assumption, pop_context, existing_codes, indicators_text
    )


def b3_generate_hypotheses_agentic(
    proyecto_id: str,
    pop_assumption: str,
    pop_context: str,
    processes_text: str,
    codes_text: str,
    hyp_text: str,
) -> list[dict]:
    """B3 agentic: ReactRunner con tools para buscar evidencia antes de generar hipotesis.

    Reemplaza la llamada single-shot b3_generate_hypotheses() cuando
    AGENTIC_MODE=true. El agente puede llamar search_segments, get_code_details,
    etc. para verificar evidencia antes de hipotetizar.
    """
    import sys as _sys

    _sys.path.insert(0, "/app")
    from app.agents.react_runner import ReactRunner
    from app.agents.tool_registry import ToolRegistry
    from app.agents.tools.db_tools import (
        get_all_codes,
        get_code_details,
        get_existing_hypotheses,
    )
    from app.agents.tools.search_tools import search_segments, search_similar_codes

    tools = ToolRegistry()
    tools.register(
        search_segments,
        "search_segments",
        "Busca segmentos semanticamente en el corpus.",
    )
    tools.register(
        get_code_details,
        "get_code_details",
        "Obten definicion e incidentes de un codigo.",
    )
    tools.register(
        get_all_codes, "get_all_codes", "Lista todos los codigos del proyecto."
    )
    tools.register(
        get_existing_hypotheses,
        "get_existing_hypotheses",
        "Lista hipotesis ya generadas.",
    )
    tools.register(
        search_similar_codes,
        "search_similar_codes",
        "Busca codigos similares (anti-redundancia).",
    )

    runner = ReactRunner(
        agent_id="b3",
        llm_client=llm,
        tool_registry=tools,
        max_iterations=5,
        timeout_seconds=300.0,
    )

    result = runner.run(
        project_id=proyecto_id,
        role_description="Eres un generador de hipotesis para Grounded Theory con acceso a herramientas de busqueda.",
        generate_vars={
            "population_assumption": pop_assumption,
            "population_context": pop_context,
            "processes": processes_text,
            "codes": codes_text,
            "existing_hypotheses": hyp_text,
        },
    )

    if result.success:
        logger.info(
            "Agentic B3: %d hypotheses in %d iterations (reasoning=%s, tool_calls=%d)",
            len(result.data.get("hypotheses", [])),
            result.iterations,
            result.had_reasoning,
            sum(1 for t in result.trace if t.get("type") == "tool_call"),
        )
        return result.data.get("hypotheses", [])

    # Fallback to single-shot on failure
    logger.warning("Agentic B3 failed: %s. Falling back to single-shot.", result.error)
    response = llm.run_agent(
        agent_id="b3",
        variables={
            "population_assumption": pop_assumption,
            "population_context": pop_context,
            "processes": processes_text,
            "codes": codes_text,
            "existing_hypotheses": hyp_text,
        },
        temperature=0.4,
    )
    return response.get("hypotheses", [])
