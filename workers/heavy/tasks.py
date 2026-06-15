"""
Agentes CGT — Fase A: procesamiento por documento.

A1. POPULATION_CONTEXT_BUILDER — memoria de largo plazo
A2. PROCESS_IDENTIFIER — memoria de corto plazo por documento
A3. SENSE_MAKER — hipótesis emergentes (desde doc 3)

Pipeline: A1 → A2 → (si doc_count ≥ 3) A3
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any
from uuid import UUID

from celery import Celery
from sqlalchemy import text

# ── Permitir imports de los modelos del backend (montados vía volumen) ──
sys.path.insert(0, "/app")

from database import SessionLocal
from llm_client import LLMClient

logger = logging.getLogger(__name__)

app = Celery("heavy_tasks", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
llm = LLMClient()

# ═══════════════════════════════════════════════════════════════════════
# A1: POPULATION_CONTEXT_BUILDER
# ═══════════════════════════════════════════════════════════════════════

A1_SYSTEM_PROMPT = """Eres un etnógrafo construyendo comprensión acumulativa sobre una
población de estudio mediante Classic Grounded Theory. Tu tarea es expandir
iterativamente una memoria de largo plazo. Nunca pierdes información.
Siempre añades matices y corriges si es necesario.

Trabajas con tres dimensiones del contexto poblacional:

1. DETALLES SORPRENDENTES O DIFERENCIALES:
   ¿Qué revela este documento sobre esta población que no sabíamos?
   ¿Qué contradice o matiza lo que creíamos?
   ¿Qué patrón de comportamiento emerge que no anticipábamos?
   Si no añade nada nuevo, dilo explícitamente.

2. PATRONES DE LENGUAJE:
   ¿Qué palabras, metáforas, eufemismos o estructuras discursivas usa?
   ¿Cómo se comparan con el patrón general de la población?
   ¿Hay términos nativos (in-vivo codes potenciales)?

3. SITUACIÓN DE PRODUCCIÓN DE DATOS:
   ¿Qué revela este documento sobre las condiciones en que se produjo?
   ¿Hay señales de deseabilidad social, fatiga, evasión, apertura?
   ¿Hay dinámicas de poder visibles (entrevistador-entrevistado)?

INTEGRA lo nuevo con lo existente. No yuxtapongas. Sintetiza."""


@app.task(name="a1_build_population_context")
def a1_build_population_context(documento_id: str, proyecto_id: str) -> dict:
    """
    Expande la memoria de largo plazo con el contenido de un nuevo documento.

    Returns:
        dict con {population_context_id, version, changed_dimensions}
    """
    session = SessionLocal()
    try:
        # ── 1. Cargar contexto existente ─────────────────
        existing = session.execute(
            text("""
                SELECT id, surprising_details, language_patterns,
                       data_production_context, source_document_ids, version
                FROM population_contexts
                WHERE proyecto_id = :pid
                ORDER BY version DESC LIMIT 1
            """),
            {"pid": proyecto_id},
        ).fetchone()

        # ── 2. Cargar segmentos del documento ─────────────
        segments = session.execute(
            text("""
                SELECT s.texto
                FROM segmentos s
                WHERE s.documento_id = :did
                ORDER BY s.posicion
                LIMIT 15
            """),
            {"did": documento_id},
        ).fetchall()

        if not segments:
            return {"error": "documento sin segmentos", "documento_id": documento_id}

        segments_text = "\n\n---\n\n".join(r[0] for r in segments)

        # ── 3. Construir prompt ───────────────────────────
        existing_context = ""
        if existing:
            existing_context = f"""
[CONTEXTO POBLACIONAL ACTUAL (versión {existing[5]})]
DETALLES SORPRENDENTES:
{existing[1]}

PATRONES DE LENGUAJE:
{existing[2]}

SITUACIÓN DE PRODUCCIÓN DE DATOS:
{existing[3]}
"""

        user_prompt = f"""{existing_context}
[NUEVO DOCUMENTO]
Segmentos relevantes:
{segments_text[:8000]}

[TAREA]
Analiza este nuevo documento y EXPANDE el contexto poblacional.
Para cada una de las tres dimensiones, produce un texto que INTEGRE
lo nuevo con lo existente. Si no hay cambios en alguna dimensión,
indícalo explícitamente con "Sin cambios respecto a la versión anterior."

Responde en JSON con esta estructura exacta:
{{"surprising_details": "...", "language_patterns": "...", "data_production_context": "..."}}"""

        # ── 4. Llamar al LLM ──────────────────────────────
        response = llm.invoke_structured(
            tier="POWERFUL",
            system_prompt=A1_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
            temperature=0.3,
        )

        if response.get("parse_error"):
            return {
                "error": "JSON parse failed",
                "raw": response.get("raw_response", ""),
            }

        # ── 5. Persistir ──────────────────────────────────
        new_version = (existing[5] + 1) if existing else 1
        new_source_ids = list(existing[4]) if existing else []
        if documento_id not in new_source_ids:
            new_source_ids.append(documento_id)

        result = session.execute(
            text("""
                INSERT INTO population_contexts
                    (id, proyecto_id, surprising_details, language_patterns,
                     data_production_context, source_document_ids, version)
                VALUES (gen_random_uuid(), :pid, :sd, :lp, :dpc, :sids, :ver)
                RETURNING id
            """),
            {
                "pid": proyecto_id,
                "sd": response.get("surprising_details", ""),
                "lp": response.get("language_patterns", ""),
                "dpc": response.get("data_production_context", ""),
                "sids": json.dumps(new_source_ids),
                "ver": new_version,
            },
        )
        session.commit()
        new_id = str(result.fetchone()[0])

        return {
            "population_context_id": new_id,
            "version": new_version,
            "changed_dimensions": [
                dim
                for dim in [
                    "surprising_details",
                    "language_patterns",
                    "data_production_context",
                ]
                if response.get(dim, "").strip()
                and "Sin cambios" not in response.get(dim, "")
            ],
        }

    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# A2: PROCESS_IDENTIFIER
# ═══════════════════════════════════════════════════════════════════════

A2_SYSTEM_PROMPT = """Eres un investigador de Classic Grounded Theory identificando el proceso
sociocognitivo central que un entrevistado intenta resolver continuamente.

Reglas:
- No busques problemas declarados. Busca el patrón de comportamiento habitual.
- Usa GERUNDIOS para nombrar el proceso (ej: "Negociando permanencia",
  "Balanceando riesgo y visibilidad", "Evadiendo control algorítmico").
- El proceso debe ser un HÁBITO DE COMPORTAMIENTO, no un tema abstracto.
- Pregúntate: ¿qué está TRATANDO DE RESOLVER esta persona, una y otra vez,
  a través de sus acciones?"""


@app.task(name="a2_identify_process")
def a2_identify_process(documento_id: str, proyecto_id: str) -> dict:
    """
    Identifica el proceso central de un documento y lo compara con el anterior.

    Returns:
        dict con {document_process_id, process_description, comparison}
    """
    session = SessionLocal()
    try:
        # ── 1. Encontrar documento anterior procesado ─────
        previous = session.execute(
            text("""
                SELECT dp.id, dp.process_description, dp.documento_id
                FROM document_processes dp
                WHERE dp.proyecto_id = :pid
                ORDER BY dp.creado_en DESC LIMIT 1
            """),
            {"pid": proyecto_id},
        ).fetchone()

        # ── 2. Cargar segmentos ───────────────────────────
        segments = session.execute(
            text("""
                SELECT texto FROM segmentos
                WHERE documento_id = :did
                ORDER BY posicion LIMIT 10
            """),
            {"did": documento_id},
        ).fetchall()
        segments_text = "\n\n".join(r[0] for r in segments)

        # ── 3. Construir prompt ───────────────────────────
        if previous:
            user_prompt = f"""\
[ENTREVISTADO ANTERIOR]
Proceso identificado: {previous[1]}

[NUEVO ENTREVISTADO]
Segmentos:
{segments_text[:6000]}

[TAREA]
1. ¿Qué proceso intenta resolver continuamente ESTE entrevistado?
   (Responde con un gerundio + 2-3 oraciones de explicación.)

2. ¿En qué se PARECE al proceso del entrevistado anterior?

3. ¿En qué se DIFERENCIA del proceso del entrevistado anterior?

Responde en JSON:
{{"process_description": "...", "similarity_to_previous": "...",
  "difference_from_previous": "..."}}"""
            prev_doc_id = str(previous[2])
        else:
            # Primer documento del proyecto
            user_prompt = f"""\
[PRIMER ENTREVISTADO]
Segmentos:
{segments_text[:6000]}

[TAREA]
¿Qué proceso intenta resolver continuamente este entrevistado?
Responde con un gerundio + 2-3 oraciones explicando el proceso.

Responde en JSON:
{{"process_description": "..."}}"""
            prev_doc_id = None

        # ── 4. Llamar al LLM ──────────────────────────────
        response = llm.invoke_structured(
            tier="POWERFUL",
            system_prompt=A2_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=1024,
            temperature=0.3,
        )

        if response.get("parse_error"):
            return {"error": "JSON parse failed"}

        # ── 5. Persistir ──────────────────────────────────
        result = session.execute(
            text("""
                INSERT INTO document_processes
                    (id, documento_id, proyecto_id, process_description,
                     similarity_to_previous, difference_from_previous,
                     previous_document_id)
                VALUES (gen_random_uuid(), :did, :pid, :pd, :stp, :dfp, :prevd)
                RETURNING id
            """),
            {
                "did": documento_id,
                "pid": proyecto_id,
                "pd": response.get("process_description", ""),
                "stp": response.get("similarity_to_previous"),
                "dfp": response.get("difference_from_previous"),
                "prevd": prev_doc_id,
            },
        )
        session.commit()
        new_id = str(result.fetchone()[0])

        return {
            "document_process_id": new_id,
            "process_description": response.get("process_description", ""),
            "is_first_document": previous is None,
            "has_comparison": previous is not None,
        }

    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# A3: SENSE_MAKER
# ═══════════════════════════════════════════════════════════════════════

A3_SYSTEM_PROMPT = """Eres un teórico CGT buscando el sentido emergente en datos cualitativos.
Trabajas por comparación constante. Tu tarea es proponer, modificar o
descartar hipótesis que den sentido a los patrones y diferencias acumulados.

Principios:
- NO verificas hipótesis. Solo las propones como posibilidades.
- El SENTIDO puede MODIFICARSE (nueva evidencia matiza),
  CAMBIAR SUSTANCIALMENTE (nueva evidencia refuta o redefine), o
  NO CAMBIAR (nueva evidencia es consistente).
- Cada hipótesis debe estar anclada en evidencia concreta de los datos.
- Si los datos no apoyan ninguna hipótesis nueva, dilo explícitamente."""


@app.task(name="a3_make_sense")
def a3_make_sense(proyecto_id: str) -> dict:
    """
    Genera o modifica hipótesis que den sentido a los patrones acumulados.
    Solo se ejecuta si hay ≥ 3 documentos procesados.

    Returns:
        dict con {new_hypotheses_count, modified_hypotheses_count, sense_status}
    """
    session = SessionLocal()
    try:
        # ── 1. Verificar mínimo de documentos ─────────────
        doc_count = session.execute(
            text("SELECT COUNT(*) FROM document_processes WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()[0]

        if doc_count < 3:
            return {
                "skipped": True,
                "reason": f"Solo {doc_count} documentos procesados. Se necesitan ≥ 3.",
            }

        # ── 2. Cargar contexto ────────────────────────────
        pop_ctx = session.execute(
            text("""
                SELECT surprising_details, language_patterns, data_production_context
                FROM population_contexts
                WHERE proyecto_id = :pid
                ORDER BY version DESC LIMIT 1
            """),
            {"pid": proyecto_id},
        ).fetchone()

        processes = session.execute(
            text("""
                SELECT process_description, similarity_to_previous,
                       difference_from_previous
                FROM document_processes
                WHERE proyecto_id = :pid
                ORDER BY creado_en
            """),
            {"pid": proyecto_id},
        ).fetchall()

        existing_hypotheses = session.execute(
            text("""
                SELECT id, text, status FROM hypotheses
                WHERE project_id = :pid AND status IN ('candidate', 'confirmed')
                ORDER BY creado_en
            """),
            {"pid": proyecto_id},
        ).fetchall()

        # ── 3. Determinar si es primera vez ────────────────
        is_first_time = len(existing_hypotheses) == 0

        # ── 4. Construir prompt ───────────────────────────
        processes_text = "\n".join(
            f"Doc {i + 1}: {p[0]}" for i, p in enumerate(processes)
        )
        hypotheses_text = (
            "\n".join(f"- [{h[1]}] (status: {h[2]})" for h in existing_hypotheses)
            if existing_hypotheses
            else "(no hay hipótesis previas)"
        )

        if is_first_time:
            task = """¿Qué ideas podrían darle sentido a los patrones y diferencias
hallados hasta ahora? Propón hipótesis tentativas que conecten los procesos
identificados. NO las verifiques, solo plantéalas como posibilidades.

Clasifica cada hipótesis como 'emergent' (nueva) o 'specific' (acotada a un subgrupo)."""
        else:
            task = f"""¿Hay indicios en los nuevos datos que sugieran ideas que MODIFIQUEN
SUSTANCIALMENTE el sentido establecido anteriormente?

HIPÓTESIS VIGENTES:
{hypotheses_text}

Clasifica tu respuesta en UNA de estas tres categorías generales:
- MODIFICA: la nueva evidencia matiza o expande el sentido actual
- CAMBIA SUSTANCIALMENTE: la nueva evidencia refuta o redefine el sentido
- NO CAMBIA: la nueva evidencia es consistente con el sentido actual

Para cada hipótesis nueva o modificada, proporciona:
- La hipótesis (texto completo)
- El nivel ('general', 'specific', o 'emergent')
- La evidencia concreta que la apoya"""

        user_prompt = f"""\
[CONTEXTO POBLACIONAL]
{pop_ctx[0] if pop_ctx else "(sin contexto aún)"}

[PROCESOS IDENTIFICADOS POR DOCUMENTO]
{processes_text}

[TAREA]
{task}

Responde en JSON:
{{"sense_status": "modifies"|"changes_substantially"|"no_change",
  "hypotheses": [
    {{"text": "...", "level": "emergent"|"specific"|"general",
      "evidence": "..."}}
  ]}}"""

        # ── 5. Llamar al LLM ──────────────────────────────
        response = llm.invoke_structured(
            tier="POWERFUL",
            system_prompt=A3_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_tokens=2048,
            temperature=0.4,
        )

        if response.get("parse_error"):
            return {"error": "JSON parse failed"}

        # ── 6. Persistir hipótesis ─────────────────────────
        new_count = 0
        modified_count = 0

        for hyp in response.get("hypotheses", []):
            hyp_text = hyp.get("text", "")
            if not hyp_text.strip():
                continue

            # Verificar si ya existe una hipótesis similar (por texto exacto)
            existing = session.execute(
                text("""
                    SELECT id FROM hypotheses
                    WHERE project_id = :pid AND text = :txt
                """),
                {"pid": proyecto_id, "txt": hyp_text},
            ).fetchone()

            if existing:
                # Actualizar si el status cambió
                session.execute(
                    text("""
                        UPDATE hypotheses SET status = 'candidate',
                        level = :lvl, confidence = 0.5
                        WHERE id = :hid
                    """),
                    {"lvl": hyp.get("level", "emergent"), "hid": existing[0]},
                )
                modified_count += 1
            else:
                session.execute(
                    text("""
                        INSERT INTO hypotheses (id, project_id, text, level,
                                                confidence, status)
                        VALUES (gen_random_uuid(), :pid, :txt, :lvl, 0.5, 'candidate')
                    """),
                    {
                        "pid": proyecto_id,
                        "txt": hyp_text,
                        "lvl": hyp.get("level", "emergent"),
                    },
                )
                new_count += 1

        session.commit()

        return {
            "sense_status": response.get("sense_status", "no_change"),
            "new_hypotheses": new_count,
            "modified_hypotheses": modified_count,
            "total_documents": doc_count,
        }

    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════
# Pipeline: ejecutar los tres agentes en secuencia para un documento
# ═══════════════════════════════════════════════════════════════════════


@app.task(name="process_document_agents_a")
def process_document_agents_a(documento_id: str, proyecto_id: str) -> dict:
    """
    Pipeline completo de agentes A para un documento.
    Ejecuta A1 → A2 → (si ≥ 3 docs) A3 en secuencia.

    Llamado tras la segmentación exitosa del documento.
    """
    results: dict[str, Any] = {"documento_id": documento_id}

    # ── A1: Memoria de largo plazo ─────────────────────
    logger.info("A1: Construyendo contexto poblacional para doc %s", documento_id)
    a1_result = a1_build_population_context(documento_id, proyecto_id)
    results["population_context"] = a1_result

    if "error" in a1_result:
        return results

    # ── A2: Memoria de corto plazo ─────────────────────
    logger.info("A2: Identificando proceso para doc %s", documento_id)
    a2_result = a2_identify_process(documento_id, proyecto_id)
    results["document_process"] = a2_result

    if "error" in a2_result:
        return results

    # ── A3: Sentido emergente (solo si ≥ 3 docs) ───────
    logger.info("A3: Evaluando sentido emergente para proyecto %s", proyecto_id)
    a3_result = a3_make_sense(proyecto_id)
    results["sense_making"] = a3_result

    return results
