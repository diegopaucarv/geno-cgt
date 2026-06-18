"""Agentes CGT — Fase B: síntesis cross-documento (con prompt library)."""

from __future__ import annotations

import json
import logging
import os

from algorithmic_checks import deduplicate_hypotheses
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
    """DEPRECATED since F2.3 — use b1_compare_incidents() from comparator.py instead.

    Legacy sampling distiller. Kept for backward compatibility only.
    VIOLATION: This function sees categorias (existing codes), which the CGT
    comparator should NOT see. The new b1_compare_incidents() only reads
    extracted_incidents, never categories.

    REDIRECT: Calls b1_compare_incidents() and returns a legacy-compatible result.
    """
    import warnings

    warnings.warn(
        "b1_distill_sampling is deprecated. Use b1_compare_incidents() from "
        "comparator.py instead. Redirecting automatically.",
        DeprecationWarning,
        stacklevel=2,
    )

    # ── F4.1.1: Redirect to new B1 comparator ──
    from comparator import b1_compare_incidents

    try:
        result = b1_compare_incidents(proyecto_id)
        logger.info(
            "b1_distill_sampling redirected to b1_compare_incidents: %s", result
        )
        return {
            "sampling_dimensions": [],
            "dimensions_discarded": 0,
            "memos_created": 0,
            "redirected_to": "b1_compare_incidents",
            "comparator_result": result,
        }
    except Exception as e:
        logger.error("b1_distill_sampling redirect failed: %s", e)
        # ── Fallback: return empty result for backward compatibility ──
        return {
            "sampling_dimensions": [],
            "dimensions_discarded": 0,
            "memos_created": 0,
            "redirect_error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════
# B2: OPEN_CODER — Chain B2a (FLASH) → B2b (PRO)
# ═══════════════════════════════════════════════════════════════════════


def _b2a_extract_indicators(segments_text: str) -> dict:
    """DEPRECATED since F4.1 — B2a (FLASH): Extrae indicadores de comportamiento de segmentos.

    This helper was used by the legacy b2_open_code() pipeline. The new architecture
    uses b2_label_groups() from labeler.py instead.
    """
    import warnings

    warnings.warn(
        "_b2a_extract_indicators is deprecated. Use b2_label_groups() from labeler.py instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return llm.run_agent(
        agent_id="fb_indicators_extractor",
        variables={
            "segments": segments_text,
            "object_of_study": "concern",
            "operational_question": "(not yet generated)",
        },
        temperature=0.2,
    )


def _b2b_generate_codes(
    pop_assumption: str, pop_context: str, existing_codes: str, indicators_text: str
) -> dict:
    """DEPRECATED since F4.1 — B2b (PRO): Generate codes from pre-extracted indicators.

    This helper was used by the legacy b2_open_code() pipeline. The new architecture
    uses b2_label_groups() from labeler.py instead.
    """
    import warnings

    warnings.warn(
        "_b2b_generate_codes is deprecated. Use b2_label_groups() from labeler.py instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return llm.run_agent(
        agent_id="fb_code_generator",
        variables={
            "population_assumption": pop_assumption,
            "population_context": pop_context,
            "existing_codes": existing_codes,
            "indicators": indicators_text,
            "object_of_study": "concern",
            "operational_question": "(not yet generated)",
        },
        temperature=0.3,
    )


def _enrich_codes_with_evidence(codes: list[dict], proyecto_id: str) -> list[dict]:
    """DEPRECATED since F4.1 — Post-B2b enrichment: busca evidencia documental para cada código vía RAG.

    This helper was used by the legacy b2_open_code() pipeline. The new architecture
    uses b2_label_groups() from labeler.py instead.

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
    import warnings

    warnings.warn(
        "_enrich_codes_with_evidence is deprecated. Use b2_label_groups() from labeler.py instead.",
        DeprecationWarning,
        stacklevel=2,
    )

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
    """DEPRECATED since F2.3 — use b2_label_groups() from labeler.py instead.

    Legacy open coding pipeline. Kept for reference only.
    VIOLATION: This function does everything (extract indicators, generate codes,
    critique) in one monolithic call. The new architecture splits this into:
      - comparator.py::b1_compare_incidents() — compares incidents
      - labeler.py::b2_label_groups() — labels groups with SelfRefinement loop
      - label_critic.py::b3_critique_labels() — critiques labels (FLASH)
    """
    import warnings

    warnings.warn(
        "b2_open_code is deprecated. Use b2_label_groups() from labeler.py instead. "
        "Redirecting automatically.",
        DeprecationWarning,
        stacklevel=2,
    )

    # ── F4.1.2: Redirect to new B2 labeler ──
    from labeler import b2_label_groups

    try:
        result = b2_label_groups(proyecto_id)
        logger.info("b2_open_code redirected to b2_label_groups: %s", result)
        return {
            "codes_created": result.get("labels_created", 0),
            "codes": [],
            "auto_assigned": 0,
            "b2a_indicators": 0,
            "redirected_to": "b2_label_groups",
            "labeler_result": result,
        }
    except Exception as e:
        logger.error("b2_open_code redirect failed: %s", e)
        # ── Fallback: return empty result for backward compatibility ──
        return {
            "codes_created": 0,
            "codes": [],
            "auto_assigned": 0,
            "b2a_indicators": 0,
            "redirect_error": str(e),
        }


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


def b3_generate_hypotheses(
    proyecto_id: str, incident_groups_json: str | None = None
) -> dict:
    """Generate hypotheses from categories + labeled incident_groups.

    Updated F2.3: Also reads labeled incident_groups (from B2 labeler) in addition
    to traditional categorias. This ensures hypotheses can reference the new
    incident-based categories.

    Updated F4.1.3: Accepts optional incident_groups_json parameter that, when
    provided, takes priority over the DB query for labeled incident_groups.
    This allows callers (e.g., tasks.py) to pass pre-fetched groups from B2's
    output, avoiding redundant DB queries.

    Args:
        proyecto_id: UUID of the project.
        incident_groups_json: Optional JSON string of labeled incident groups
            (list of dicts with 'label' and 'definition' keys). When provided,
            these are used instead of querying the DB for labeled groups.
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

        # Fetch operational question and object of study
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")
        oos_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = oos_row[0] if oos_row and oos_row[0] else "concern"

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

        # ── F2.3: Include both categorias and labeled incident_groups ──
        codes = session.execute(
            text("SELECT nombre, definicion FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()

        # ── F4.1.3: Use incident_groups_json if provided, otherwise query DB ──
        if incident_groups_json:
            try:
                labeled_groups_raw = json.loads(incident_groups_json)
                # Convert JSON objects to (label, definition) tuples
                labeled_groups = [
                    (g.get("label"), g.get("definition"))
                    for g in labeled_groups_raw
                    if isinstance(g, dict)
                ]
                logger.info(
                    "b3_generate_hypotheses: using %d groups from incident_groups_json",
                    len(labeled_groups),
                )
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    "b3_generate_hypotheses: invalid incident_groups_json, "
                    "falling back to DB: %s",
                    e,
                )
                labeled_groups = session.execute(
                    text(
                        "SELECT label, definition FROM incident_groups "
                        "WHERE proyecto_id = :pid AND status = 'labeled' "
                        "AND label IS NOT NULL"
                    ),
                    {"pid": proyecto_id},
                ).fetchall()
        else:
            # Also read labeled incident_groups as additional "categories"
            labeled_groups = session.execute(
                text(
                    "SELECT label, definition FROM incident_groups "
                    "WHERE proyecto_id = :pid AND status = 'labeled' AND label IS NOT NULL"
                ),
                {"pid": proyecto_id},
            ).fetchall()

        # Merge both sources
        all_codes = list(codes)  # (nombre, definicion) tuples
        for lg in labeled_groups:
            if lg[0] and lg[1]:  # label, definition
                # Avoid duplicates if already in categorias
                if not any(c[0] == lg[0] for c in all_codes):
                    all_codes.append((lg[0], lg[1]))

        processes_text = "\n".join(
            f"Doc {i + 1}: {p[0]}" for i, p in enumerate(processes)
        )
        hyp_text = (
            "\n".join(f"- [{h[1]}] {h[0]}" for h in existing)
            if existing
            else "(sin hipótesis)"
        )
        codes_text = (
            "\n".join(f"- {c[0]}: {c[1]}" for c in all_codes)
            if all_codes
            else "(sin códigos)"
        )

        if AGENTIC_MODE:
            raw_hypotheses = b3_generate_hypotheses_agentic(
                proyecto_id,
                pop_assumption,
                pop_ctx[0] if pop_ctx else "",
                processes_text,
                codes_text,
                hyp_text,
                object_of_study,
                operational_question,
            )
        else:
            response = llm.run_agent(
                agent_id="fb_hypothesis_generator",
                variables={
                    "population_assumption": pop_assumption,
                    "population_context": pop_ctx[0] if pop_ctx else "",
                    "processes": processes_text,
                    "codes": codes_text,
                    "existing_hypotheses": hyp_text,
                    "object_of_study": object_of_study,
                    "operational_question": operational_question
                    or "(not yet generated)",
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
    """DEPRECATED since F4.1 — B2b agentic: SelfRefinementLoop (Generate -> Critic -> Refine).

    This helper was used by the legacy b2_open_code() pipeline. The new architecture
    uses b2_label_groups() from labeler.py instead, which has its own SelfRefinement loop.

    Reemplaza la llamada single-shot _b2b_generate_codes() cuando
    AGENTIC_MODE=true. Usa PRO para generar y FLASH para evaluar.
    """
    import sys as _sys
    import warnings

    warnings.warn(
        "_b2b_generate_codes_agentic is deprecated. Use b2_label_groups() from labeler.py instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    _sys.path.insert(0, "/app")
    from app.agents.self_refiner import SelfRefinementLoop

    loop = SelfRefinementLoop(
        agent_id="fb_code_generator",
        llm_client=llm,
        generate_prompt_id="fb_code_generator",
        critic_prompt_id="util_code_critic",
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
            "object_of_study": "concern",
            "operational_question": "(not yet generated)",
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
    object_of_study: str = "concern",
    operational_question: str = "",
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
        agent_id="fb_hypothesis_generator",
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
            "object_of_study": object_of_study,
            "operational_question": operational_question or "(not yet generated)",
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
        agent_id="fb_hypothesis_generator",
        variables={
            "population_assumption": pop_assumption,
            "population_context": pop_context,
            "processes": processes_text,
            "codes": codes_text,
            "existing_hypotheses": hyp_text,
            "object_of_study": object_of_study,
            "operational_question": operational_question or "(not yet generated)",
        },
        temperature=0.4,
    )
    return response.get("hypotheses", [])
