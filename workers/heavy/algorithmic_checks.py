"""
Patrones algorítmicos que NO deben estar en los prompts.

Estas funciones implementan lógica que el sistema puede ejecutar
sin depender del juicio del LLM. El LLM solo recibe datos ya filtrados.

Pattern 1: Anti-duplicación de códigos (B2)
Pattern 2: Deduplicación de hipótesis (B3)
Pattern 3: Filtro de dimensiones demográficas sin evidencia (B1)
Pattern 4: Pre-clasificación Glaser por señales textuales (A2)
Pattern 5: Verificación post-hoc de alucinaciones (todos)
"""

from __future__ import annotations

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
    Verifica que las referencias a entrevistados y segmentos en el output
    del LLM correspondan a datos reales en la base de datos.

    Busca patrones como "Entrevistado 3", "el entrevistado 1", "Doc 2"
    y verifica que existan document_processes con esos índices.

    Returns:
        dict con {valid: bool, issues: [str]}
    """
    issues: list[str] = []
    all_text = str(output)

    # Buscar referencias a entrevistados por índice
    refs = re.findall(
        r"(?:entrevistado|doc(?:umento)?|participante)\s*#?\s*(\d+)",
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
                    f"Referencia a entrevistado {idx} pero solo hay "
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
    - evidence_of_variation cita al menos un entrevistado o proceso específico
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
            for kw in ["entrevistado", "doc", "participante", "describe", "menciona"]
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
# Pattern 4: Pre-clasificación Glaser por señales textuales (A2)
# ═══════════════════════════════════════════════════════════════════════


def preclassify_glaser(segments_text: str) -> dict:
    """
    Pre-clasifica el tipo de dato Glaser basándose en señales textuales
    objetivas. El LLM recibe esta pre-clasificación como contexto y puede
    confirmarla o corregirla.

    Señales:
    - properline: hedging ("yo creo que", "supongo"), lenguaje de deseabilidad
    - interpreted: preguntas del entrevistador visibles, respuestas forzadas
    - vague: respuestas muy cortas, cambios de tema, "no sé"
    - baseline: ninguno de los anteriores, narrativa fluida

    Returns:
        dict con {suggested_type, signals_found, confidence}
    """
    text_lower = segments_text.lower()

    properline_signals = [
        "la verdad que",
        "no sé si está bien decir",
        "yo creo que",
        "supongo",
        "dicen que",
        "se supone que",
        "debería",
        "tendría que",
        "lo correcto es",
        "lo que pasa es que",
        "obviamente",
    ]
    interpreted_signals = [
        "como te dije",
        "como te comenté",
        "me preguntas",
        "si me preguntás",
        "no sé qué decirte",
        "es difícil responder",
    ]
    vague_signals = [
        "no sé",
        "no me acuerdo",
        "no sabría decirte",
        "mmm",
        "ehh",
        "y bueno",
        "y nada",
        "cosas así",
        "ese tipo de cosas",
    ]

    properline_count = sum(1 for s in properline_signals if s in text_lower)
    interpreted_count = sum(1 for s in interpreted_signals if s in text_lower)
    vague_count = sum(1 for s in vague_signals if s in text_lower)

    # Contar respuestas cortas como señal de vague
    lines = [l.strip() for l in segments_text.split("\n") if l.strip()]
    short_lines = sum(1 for l in lines if len(l) < 60)

    total_lines = len(lines) or 1
    short_ratio = short_lines / total_lines

    signals = []
    if properline_count >= 3:
        signals.append(f"properline ({properline_count} marcadores)")
    if interpreted_count >= 3:
        signals.append(f"interpreted ({interpreted_count} marcadores)")
    if vague_count >= 3 or short_ratio > 0.5:
        signals.append(
            f"vague ({vague_count} marcadores, {short_ratio:.0%} líneas cortas)"
        )

    if not signals:
        return {
            "suggested_type": "baseline",
            "signals_found": "Sin marcadores claros de properline, interpreted o vague. El texto parece narrativa fluida y honesta.",
            "confidence": 0.6,
        }

    # El tipo con más señales gana
    counts = {
        "properline": properline_count,
        "interpreted": interpreted_count,
        "vague": vague_count,
    }
    suggested = max(counts, key=counts.get)  # type: ignore[arg-type]

    return {
        "suggested_type": suggested,
        "signals_found": "; ".join(signals),
        "confidence": min(0.9, counts[suggested] / 5),
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

    - similarity > 0.85 → auto-asignar (ni siquiera llamar al LLM)
    - 0.60 < similarity < 0.85 → pedir al LLM que confirme
    - similarity < 0.60 → el LLM genera código nuevo

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
            # Sin embedding → necesita LLM
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
                    "Hipótesis duplicada (Jaccard=%.2f): '%s...' ≈ '%s...'",
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
            # Aún la incluimos pero marcada como reforzada
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
    Calculadora de conteos de evidencia para hipotesis.
    Equivalente al Code in Python (Beta)1 del category saturator.json.

    Tres categorias de evidencia:
    - POSITIVE: evidencia directa a favor de la hipotesis
    - CONTRAST: confirma por oposicion (el fenomeno opuesto)
    - NO_EVIDENCE: el documento no muestra datos relevantes
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
        clasifica la evidencia.

        Returns:
            {hypothesis_id, positive_count, contrast_count,
             no_evidence_count, confirmation_ratio, is_saturated}
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

        positive, contrast, no_evidence = [], [], []

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
                no_evidence.append(str(doc_id))
                continue

            # Clasificar via LLM ligero (FLASH)
            segments_text = "\n---\n".join(r[0][:300] for r in similar)
            if llm_client:
                verdict = llm_client.run_agent(
                    "evidence_classifier",
                    variables={
                        "hypothesis": hyp[0],
                        "segments": segments_text,
                    },
                    temperature=0.1,
                )
                classification = verdict.get("classification", "NO_EVIDENCE")
            else:
                # Sin LLM: heuristica simple
                classification = "NO_EVIDENCE"

            if classification == "POSITIVE":
                positive.append(str(doc_id))
            elif classification == "CONTRAST":
                contrast.append(str(doc_id))
            else:
                no_evidence.append(str(doc_id))

        total = len(docs)
        return {
            "hypothesis_id": hypothesis_id,
            "positive_count": len(positive),
            "contrast_count": len(contrast),
            "no_evidence_count": len(no_evidence),
            "confirmation_ratio": (len(positive) + len(contrast))
            / max(total, 1),
            "is_saturated": len(positive) >= 5,
            "positive_doc_ids": positive,
            "contrast_doc_ids": contrast,
        }
