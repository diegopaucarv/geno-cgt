"""
Patrones algorítmicos que NO deben estar en los prompts.

Estas funciones implementan lógica que el sistema puede ejecutar
sin depender del juicio del LLM. El LLM solo recibe datos ya filtrados.

Pattern 1: Anti-duplicación de códigos (B2)
Pattern 2: Deduplicación de hipótesis (B3)
Pattern 3: Filtro de dimensiones demográficas sin evidencia (B1)
Pattern 4: Clasificación Glaser del documento completo (pre-segmentación)
Pattern 5: Verificación post-hoc de alucinaciones (todos)
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# Pattern 5 (se ejecuta primero — es el más transversal)
# ═══════════════════════════════════════════════════════════════════════


def check_output_references(
    output: dict,
    session,
    proyecto_id: str,
) -> dict:
    """
    Verifica que las referencias a participantes y segmentos en el output
    del LLM correspondan a datos reales en la base de datos.

    Busca patrones como "Participante 3", "el participante 1", "Doc 2"
    y verifica que existan document_processes con esos índices.

    Returns:
        dict con {valid: bool, issues: [str]}
    """
    issues: list[str] = []
    all_text = str(output)

    # Buscar referencias a participantes por índice
    refs = re.findall(
        r"(?:doc(?:umento)?|participante)\s*#?\s*(\d+)",
        all_text,
        re.IGNORECASE,
    )

    if refs:
        max_doc_count = session.execute(
            text("SELECT COUNT(*) FROM document_processes WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()[0]

        for ref in refs:
            idx = int(ref)
            if idx > max_doc_count:
                issues.append(
                    f"Referencia a participante {idx} pero solo hay "
                    f"{max_doc_count} procesados"
                )

    # Buscar citas textuales entrecomilladas que no estén en segmentos
    quoted = re.findall(r'"([^"]{15,})"', all_text)
    for quote in quoted[:3]:  # solo verificar primeras 3
        exists = session.execute(
            text(
                "SELECT 1 FROM segmentos s "
                "JOIN documentos d ON s.documento_id = d.id "
                "WHERE d.proyecto_id = :pid AND s.texto ILIKE :q"
            ),
            {"pid": proyecto_id, "q": f"%{quote[:30]}%"},
        ).fetchone()
        if not exists:
            issues.append(f"Cita textual no encontrada en segmentos: '{quote[:60]}...'")

    return {"valid": len(issues) == 0, "issues": issues}


# ═══════════════════════════════════════════════════════════════════════
# Pattern 3: Filtro de dimensiones demográficas sin evidencia (B1)
# ═══════════════════════════════════════════════════════════════════════


def filter_empty_dimensions(dimensions: List[dict]) -> List[dict]:
    """
    Descarta dimensiones de muestreo que no tienen evidencia cualitativa
    o que solo mencionan variables demográficas sin citar datos.

    Una dimensión es válida si:
    - evidence_of_variation cita al menos un participante o proceso específico
    - NO es puramente demográfica sin respaldo en los datos

    Returns:
        Lista filtrada de dimensiones válidas.
    """
    demographic_only_patterns = [
        r"^\s*edad\s*$",
        r"^\s*género\s*$",
        r"^\s*sexo\s*$",
        r"^\s*nivel\s+(?:de\s+)?educación\s*$",
        r"^\s*ingresos?\s*$",
    ]

    valid: List[dict] = []
    for dim in dimensions:
        name = dim.get("name", "").strip().lower()
        evidence = dim.get("evidence_of_variation", "").strip()

        # ¿Es puramente demográfica?
        is_demographic_only = any(re.match(p, name) for p in demographic_only_patterns)

        # ¿Tiene evidencia cualitativa?
        has_evidence = len(evidence) > 30 and any(
            kw in evidence.lower()
            for kw in ["doc", "participante", "describe", "menciona"]
        )

        if is_demographic_only and not has_evidence:
            logger.info("Descartando dimensión demográfica sin evidencia: %s", name)
            continue

        if not has_evidence:
            logger.info("Dimensión con evidencia insuficiente: %s", name)
            continue

        valid.append(dim)

    return valid


# ═══════════════════════════════════════════════════════════════════════
# Pattern 4: Clasificación Glaser del documento completo (pre-segmentación)
# ═══════════════════════════════════════════════════════════════════════


def classify_document_glaser(
    raw_text: str,
    research_question: str,
    object_of_study: str,
    llm_client,
    max_retries: int = 3,
) -> dict:
    """Clasifica un documento COMPLETO por tipos de datos Glaser (pre-segmentacion).

    Envia el texto crudo completo al LLM con la research question como ancla.
    El LLM inserta tags Markdown (<!-- baseline_data -->...<!-- /baseline_data -->)
    para delimitar secciones por tipo Glaser. Un parser extrae las secciones
    etiquetadas, con un loop de reintento para robustez.

    SOLO el texto baseline_data se envia al segmentador.
    Los demas tipos se almacenan como metadata.

    Args:
        raw_text: Texto completo del documento (post-correccion de puntuacion).
        research_question: La research question principal del proyecto.
        object_of_study: El objeto de estudio (concern, emotion, behavior, etc.).
        llm_client: Instancia de LLMClient.
        max_retries: Maximos reintentos del LLM si el parseo falla.

    Returns:
        {
            "status": "ok" | "error",
            "sections": {
                "baseline_data": str,        # ← se envia al segmentador
                "properline_data": str,      # metadata
                "interpreted_data": str,     # metadata
                "vague_data": str,           # metadata
                "interviewer_context": str,  # metadata
            },
            "baseline_text": str,  # alias de conveniencia
            "error": str | None,
            "retries": int,
        }
    """
    # Importacion tardia para evitar dependencia circular con el worker NLP
    try:
        from workers.nlp.glaser_parser import parse_glaser_tags
    except ImportError:
        logger.warning("glaser_parser not found in workers.nlp, trying relative import")
        # En el worker heavy, el PYTHONPATH puede diferir
        import os
        import sys

        nlp_path = os.path.join(os.path.dirname(__file__), "..", "nlp")
        if nlp_path not in sys.path:
            sys.path.insert(0, nlp_path)
        from glaser_parser import parse_glaser_tags

    if not raw_text or not raw_text.strip():
        return {
            "status": "error",
            "sections": {},
            "baseline_text": "",
            "error": "Empty input text",
            "retries": 0,
        }

    def _call_llm(text: str, error_feedback: str | None = None) -> str:
        """Llama al LLM. En reintento, antepone el feedback de error."""
        variables: dict = {
            "raw_text": text,
            "research_question": research_question,
            "object_of_study": object_of_study,
        }
        if error_feedback:
            variables["raw_text"] = (
                f"[PREVIOUS ATTEMPT FAILED: {error_feedback}]\n\n{text}"
            )
        response = llm_client.run_agent(
            agent_id="fa_glaser_data_classifier",
            variables=variables,
        )
        # El nuevo prompt devuelve texto plano, no JSON
        if hasattr(response, "data") and isinstance(response.data, dict):
            return response.data.get(
                "tagged_text", response.data.get("text", str(response))
            )
        if isinstance(response, dict):
            return response.get("tagged_text", response.get("text", str(response)))
        return str(response)

    def _retry_callback(previous_tagged: str, error_msg: str) -> str:
        """Callback de reintento: re-llama al LLM con feedback del parser."""
        return _call_llm(raw_text, error_msg)

    # ── Primer intento ──
    try:
        tagged_text = _call_llm(raw_text)
    except Exception as e:
        logger.warning(
            "Glaser classification LLM call failed: %s. Using raw text as fallback.",
            e,
        )
        return {
            "status": "error",
            "sections": {"baseline_data": raw_text},
            "baseline_text": raw_text,
            "error": f"LLM call failed: {e}",
            "retries": 0,
        }

    # ── Parsear con loop de reintento ──
    result = parse_glaser_tags(
        tagged_text,
        max_retries=max_retries,
        retry_callback=_retry_callback,
    )

    return {
        "status": result["status"],
        "sections": result["sections"],
        "baseline_text": result["sections"].get("baseline_data", ""),
        "error": result.get("error"),
        "retries": result["retries"],
    }


# ═══════════════════════════════════════════════════════════════════════
# Pattern 1: Anti-duplicación de códigos (B2)
# ═══════════════════════════════════════════════════════════════════════


def prescreen_segments_against_codes(
    unassigned_segment_ids: List[str],
    session,
    proyecto_id: str,
    high_threshold: float = 0.85,
    medium_threshold: float = 0.60,
) -> dict:
    """
    Pre-filtra segmentos sin codificar contra códigos existentes usando
    similitud de embeddings.

    - similarity > 0.85 -> auto-asignar (ni siquiera llamar al LLM)
    - 0.60 < similarity < 0.85 -> pedir al LLM que confirme
    - similarity < 0.60 -> el LLM genera código nuevo

    Si los segmentos no tienen embedding, devuelve todos como "necesitan LLM".

    Returns:
        {
            auto_assign: [{segment_id, code_id, code_name, score}],
            needs_confirmation: [{segment_id, candidate_codes: [...]}],
            needs_new_code: [segment_id, ...]
        }
    """
    result = {
        "auto_assign": [],
        "needs_confirmation": [],
        "needs_new_code": [],
    }

    for seg_id in unassigned_segment_ids:
        # Obtener embedding del segmento
        row = session.execute(
            text("SELECT embedding FROM segmentos WHERE id = :sid"),
            {"sid": seg_id},
        ).fetchone()

        if not row or row[0] is None:
            # Sin embedding -> necesita LLM
            result["needs_new_code"].append(seg_id)
            continue

        embedding = row[0]

        # Buscar códigos similares
        similar = session.execute(
            text("""
                SELECT c.id, c.nombre, c.definicion,
                       1.0 - (c.embedding_centroide <=> :vec) AS score
                FROM categorias c
                WHERE c.proyecto_id = :pid
                  AND c.embedding_centroide IS NOT NULL
                ORDER BY score DESC
                LIMIT 3
            """),
            {"vec": embedding, "pid": proyecto_id},
        ).fetchall()

        if not similar:
            result["needs_new_code"].append(seg_id)
            continue

        top_score = similar[0][3]

        if top_score >= high_threshold:
            result["auto_assign"].append(
                {
                    "segment_id": seg_id,
                    "code_id": str(similar[0][0]),
                    "code_name": similar[0][1],
                    "score": round(float(top_score), 3),
                }
            )
        elif top_score >= medium_threshold:
            result["needs_confirmation"].append(
                {
                    "segment_id": seg_id,
                    "candidate_codes": [
                        {
                            "code_id": str(r[0]),
                            "code_name": r[1],
                            "score": round(float(r[3]), 3),
                        }
                        for r in similar
                        if r[3] >= medium_threshold
                    ],
                }
            )
        else:
            result["needs_new_code"].append(seg_id)

    return result


# ═══════════════════════════════════════════════════════════════════════
# Pattern 2: Deduplicación de hipótesis (B3)
# ═══════════════════════════════════════════════════════════════════════


def deduplicate_hypotheses(
    new_hypotheses: List[dict],
    session,
    proyecto_id: str,
    similarity_threshold: float = 0.85,
) -> List[dict]:
    """
    Compara hipótesis nuevas contra las existentes usando similitud
    textual simple (Jaccard sobre palabras). Si una hipótesis nueva
    es muy similar a una existente, la marca como 'reinforced' en vez
    de insertarla como duplicado.

    Returns:
        Lista de hipótesis filtradas, con campo 'dedup_status' añadido.
    """
    # Obtener hipótesis existentes
    existing = session.execute(
        text(
            "SELECT id, text FROM hypotheses WHERE project_id = :pid AND status != 'rejected'"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    if not existing:
        for h in new_hypotheses:
            h["dedup_status"] = "new"
        return new_hypotheses

    filtered: List[dict] = []
    for hyp in new_hypotheses:
        hyp_text = hyp.get("text", "")
        if not hyp_text.strip():
            continue

        hyp_words = set(hyp_text.lower().split())
        if not hyp_words:
            filtered.append(hyp)
            continue

        is_duplicate = False
        for ex_id, ex_text in existing:
            ex_words = set(ex_text.lower().split())
            if not ex_words:
                continue
            intersection = hyp_words & ex_words
            union = hyp_words | ex_words
            jaccard = len(intersection) / len(union) if union else 0

            if jaccard >= similarity_threshold:
                logger.info(
                    "Hipotesis duplicada (Jaccard=%.2f): '%s...' = '%s...'",
                    jaccard,
                    hyp_text[:50],
                    ex_text[:50],
                )
                hyp["dedup_status"] = "reinforced"
                hyp["reinforced_existing_id"] = str(ex_id)
                is_duplicate = True
                break

        if not is_duplicate:
            hyp["dedup_status"] = "new"
            filtered.append(hyp)
        else:
            # Aun la incluimos pero marcada como reforzada
            filtered.append(hyp)

    return filtered


# ═══════════════════════════════════════════════════════════════════════
# A5: Triada ENRICH / SUBDIVIDE / DIVIDE (Recategorizacion.json)
# ═══════════════════════════════════════════════════════════════════════


def triadic_recategorization_decision(
    incident_group_a: list[dict],
    incident_group_b: list[dict],
    current_category: dict,
) -> dict:
    """
    Protocolo triadico heredado del AI Agent de Recategorizacion.json.

    Arbol de decision:
    1. Comparten esencia central?
       - SI -> ENRICH o SUBDIVIDE
       - NO -> DIVIDE

    2. Si comparten esencia: diferencias son de grado/matiz
       o configuran perfiles cualitativamente distintos?
       - Grado/matiz -> ENRICH
       - Perfiles distintos -> SUBDIVIDE

    3. Si SUBDIVIDE: subtipos mutuamente excluyentes?
       - SI -> subcategorias discretas
       - NO -> gradiente con anclas

    Nota: Esta funcion prepara el contexto. La decision final la toma
    el LLM via el prompt recategorization_decider.md.
    """
    # Construir el contexto estructurado para el LLM
    context = {
        "category": current_category,
        "group_a_count": len(incident_group_a),
        "group_b_count": len(incident_group_b),
        "group_a_sample": incident_group_a[:3],
        "group_b_sample": incident_group_b[:3],
    }
    return context


# ═══════════════════════════════════════════════════════════════════════
# A11: Hypothesis Evidence Counter (category saturator.json, Code1)
# ═══════════════════════════════════════════════════════════════════════


class HypothesisEvidenceCounter:
    """
    Analizador inductivo de patrones para hipotesis.
    Equivalente al Code in Python (Beta)1 del category saturator.json.

    Cuatro categorias de revelacion:
    - REVEALS_NEW_PROPERTY: revela una nueva dimension, propiedad o condicion del fenomeno
    - REVEALS_VARIATION: muestra una variacion del mismo patron subyacente
    - REVEALS_COUNTERPATTERN: muestra un patron opuesto que complejiza la hipotesis
    - NO_NEW_INFORMATION: el documento no agrega nada nuevo
    """

    def count_evidence(
        self,
        hypothesis_id: str,
        proyecto_id: str,
        session,
        llm_client=None,
    ) -> dict:
        """
        Itera todos los documentos del proyecto. Para cada uno,
        busca segmentos relevantes via similitud de embeddings y
        analiza que revelan inductivamente sobre el fenomeno.

        Returns:
            {hypothesis_id, new_property_count, variation_count,
             counterpattern_count, no_new_info_count, discovery_rate, is_saturated}
        """
        hyp = session.execute(
            text("SELECT text FROM hypotheses WHERE id = :hid"),
            {"hid": hypothesis_id},
        ).fetchone()
        if not hyp:
            return {"error": "hypothesis not found"}

        docs = session.execute(
            text("SELECT id FROM documentos WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()

        new_property, variation, counterpattern, no_new_info = [], [], [], []

        for (doc_id,) in docs:
            # Buscar segmentos con embedding mas cercano
            similar = session.execute(
                text("""
                    SELECT s.texto, 1.0 - (s.embedding <=>
                        (SELECT embedding FROM segmentos
                         WHERE documento_id = :did AND embedding IS NOT NULL
                         LIMIT 1)) AS score
                    FROM segmentos s
                    WHERE s.documento_id = :did AND s.embedding IS NOT NULL
                    ORDER BY score DESC LIMIT 3
                """),
                {"did": str(doc_id)},
            ).fetchall()

            if not similar or similar[0][1] < 0.5:
                no_new_info.append(str(doc_id))
                continue

            # Clasificar via LLM ligero (FLASH)
            segments_text = "\n---\n".join(r[0][:300] for r in similar)
            if llm_client:
                verdict = llm_client.run_agent(
                    "fb_evidence_classifier",
                    variables={
                        "hypothesis": hyp[0],
                        "segments": segments_text,
                    },
                    temperature=0.1,
                )
                classification = verdict.get("classification", "NO_NEW_INFORMATION")
            else:
                # Sin LLM: heuristica simple
                classification = "NO_NEW_INFORMATION"

            if classification == "REVEALS_NEW_PROPERTY":
                new_property.append(str(doc_id))
            elif classification == "REVEALS_VARIATION":
                variation.append(str(doc_id))
            elif classification == "REVEALS_COUNTERPATTERN":
                counterpattern.append(str(doc_id))
            else:
                no_new_info.append(str(doc_id))

        total = len(docs)
        return {
            "hypothesis_id": hypothesis_id,
            "new_property_count": len(new_property),
            "variation_count": len(variation),
            "counterpattern_count": len(counterpattern),
            "no_new_info_count": len(no_new_info),
            "discovery_rate": (len(new_property) + len(variation) + len(counterpattern))
            / max(total, 1),
            "is_saturated": len(new_property) == 0 and len(variation) > 0,
            "new_property_doc_ids": new_property,
            "variation_doc_ids": variation,
            "counterpattern_doc_ids": counterpattern,
        }
