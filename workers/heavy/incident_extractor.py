"""
F2.2 — Incident Extractor (FLASH, per-segmento).

Aplica las 4 preguntas de Glaser a cada segmento baseline.
Output ≤ 1 párrafo. No ve otros documentos. No ve categorías existentes.
NADA aislado. El jot se produce en gerundio.

La pregunta 4 se parametriza según el object_of_study del proyecto:
  concern  → "¿Cuál es la preocupación principal del participante?"
  emotion  → "¿Cuál es la emoción recurrente del participante?"
  behavior → "¿Cuál es la conducta recurrente del participante?"
  discourse → "¿Cuál es el patrón discursivo recurrente del participante?"
  identity → "¿Cuál es el trabajo identitario recurrente del participante?"
  custom   → "¿Cuál es el patrón recurrente del participante?"

Alimenta la tabla extracted_incidents → Fase B (incident_comparator).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

sys.path.insert(0, "/app")

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()

# ── Mapeo object_of_study → Pregunta 4 de Glaser ─────────────────────

_Q4_MAP: dict[str, str] = {
    "concern": "¿Cuál es la preocupación principal del participante?",
    "emotion": "¿Cuál es la emoción recurrente del participante?",
    "behavior": "¿Cuál es la conducta recurrente del participante?",
    "discourse": "¿Cuál es el patrón discursivo recurrente del participante?",
    "identity": "¿Cuál es el trabajo identitario recurrente del participante?",
    "custom": "¿Cuál es el patrón recurrente del participante?",
}

# ── Output schema (FLASH) ────────────────────────────────────────────

_INCIDENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "jot_text": {
            "type": "string",
            "description": (
                "Jot en gerundio (1-4 palabras). "
                "Primera impresión del incidente. "
                "Ej: 'Escaneando el horizonte de amenazas'"
            ),
        },
        "keep_moving": {
            "type": "boolean",
            "description": (
                "¿Hay más patrones en este segmento? "
                "Siempre true, a menos que el segmento "
                "esté completamente vacío o sea ininteligible."
            ),
        },
        "what_is_this_about": {
            "type": "string",
            "description": (
                "Pregunta 1 de Glaser. ¿De qué trata este dato? 1 oración descriptiva."
            ),
        },
        "what_category": {
            "type": "string",
            "description": (
                "Pregunta 2 de Glaser. ¿Qué categoría indica este incidente? "
                "Nombrar con un gerundio."
            ),
        },
        "what_is_happening": {
            "type": "string",
            "description": (
                "Pregunta 3 de Glaser. ¿Qué está sucediendo realmente? "
                "Interpretar el patrón de comportamiento subyacente."
            ),
        },
        "participants_pattern": {
            "type": "string",
            "description": (
                "Pregunta 4 de Glaser. Parametrizada según el objeto de estudio. "
                "Identificar el patrón recurrente del participante."
            ),
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": (
                "Confianza en la extracción. HIGH ≥ 0.8, MEDIUM 0.5–0.79, LOW < 0.5"
            ),
        },
        "tipo_dato_glaser": {
            "type": "string",
            "enum": ["baseline", "properline", "interpreted", "vague"],
            "description": (
                "Clasificación Glaser del dato: "
                "baseline = dato espontáneo del participante, "
                "properline = dato esperado/socialmente deseable, "
                "interpreted = interpretación del entrevistador, "
                "vague = dato ambiguo o vago."
            ),
        },
    },
    "required": [
        "jot_text",
        "keep_moving",
        "what_is_this_about",
        "what_category",
        "what_is_happening",
        "participants_pattern",
        "confidence",
    ],
}

# ── System prompt template ────────────────────────────────────────────

_SYSTEM_PROMPT = """[ROL]
Eres un extractor de incidentes para Classic Grounded Theory.
Tu tarea es analizar UN segmento de datos y aplicar las 4 preguntas de Glaser.

[PREGUNTAS DE GLASER]
1. ¿De qué trata este dato? — Describe en 1 oración el contenido del segmento.
2. ¿Qué categoría indica este incidente? — Nombra la categoría emergente con un gerundio.
3. ¿Qué está sucediendo realmente en el dato? — Interpreta el patrón de comportamiento subyacente, más allá de lo que el participante dice explícitamente.
4. {q4}

[OBJETO DE ESTUDIO]
object_of_study = {object_of_study}

[INSTRUCCIONES]
- El jot (jot_text) debe ser un gerundio de 1-4 palabras que capture la esencia del incidente.
- keep_moving = true SIEMPRE, a menos que el segmento esté COMPLETAMENTE vacío o sea ininteligible.
- NO compares con otros documentos ni con categorías existentes. Trabaja AISLADO.
- Sé conciso. Cada respuesta debe ser ≤ 1 oración.
- tipo_dato_glaser: clasifica el dato según su naturaleza (baseline | properline | interpreted | vague).
- Responde en español.

[SEGMENTO A ANALIZAR]
{segment_text}"""


def _get_object_of_study(session, proyecto_id: str) -> str:
    """Obtiene el object_of_study del proyecto. Default: 'concern'."""
    row = session.execute(
        text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
        {"pid": proyecto_id},
    ).fetchone()
    if row and row[0]:
        return row[0]
    return "concern"


def _build_prompt(segment_text: str, object_of_study: str) -> str:
    """Construye el system prompt con las 4 preguntas de Glaser."""
    q4 = _Q4_MAP.get(object_of_study, _Q4_MAP["concern"])
    return _SYSTEM_PROMPT.format(
        q4=q4,
        object_of_study=object_of_study,
        segment_text=segment_text,
    )


def extract_incident(segment_id: str, proyecto_id: str) -> dict:
    """Extrae un incidente de un segmento usando las 4 preguntas de Glaser.

    FLASH, 1-pass. Produce un jot (gerundio) y keep_moving flag.
    Inserta en extracted_incidents.

    Args:
        segment_id: UUID del segmento.
        proyecto_id: UUID del proyecto.

    Returns:
        dict con el resultado: {incident_id, jot_text, keep_moving, ...}
    """
    session = SessionLocal()
    try:
        # ── 1. Leer segmento ──────────────────────────────────────────
        seg = session.execute(
            text("SELECT s.texto, s.documento_id FROM segmentos s WHERE s.id = :sid"),
            {"sid": segment_id},
        ).fetchone()

        if not seg:
            logger.warning("extract_incident: segmento %s no encontrado", segment_id)
            return {"error": "segmento_no_encontrado", "segmento_id": segment_id}

        segment_text, documento_id = seg[0], seg[1]

        if not segment_text or not segment_text.strip():
            logger.info(
                "extract_incident: segmento %s vacío — keep_moving=false", segment_id
            )
            # Insertar incidente vacío con keep_moving=False
            result = session.execute(
                text(
                    "INSERT INTO extracted_incidents "
                    "(id, segmento_id, documento_id, proyecto_id, "
                    "jot_text, keep_moving, preguntas_glaser_json) "
                    "VALUES (gen_random_uuid(), :sid, :did, :pid, "
                    ":jot, :km, :pgj) "
                    "RETURNING id"
                ),
                {
                    "sid": segment_id,
                    "did": documento_id,
                    "pid": proyecto_id,
                    "jot": "(segmento vacío)",
                    "km": False,
                    "pgj": json.dumps({"note": "segmento vacío"}),
                },
            )
            session.commit()
            incident_id = str(result.fetchone()[0])
            return {
                "incident_id": incident_id,
                "segmento_id": segment_id,
                "documento_id": documento_id,
                "jot_text": "(segmento vacío)",
                "keep_moving": False,
            }

        # ── 2. Obtener object_of_study ────────────────────────────────
        object_of_study = _get_object_of_study(session, proyecto_id)
        logger.info(
            "extract_incident: seg=%s obj=%s chars=%d",
            segment_id[:8],
            object_of_study,
            len(segment_text),
        )

        # ── 3. Construir prompt y llamar LLM (FLASH) ──────────────────
        system_prompt = _build_prompt(segment_text, object_of_study)

        response = llm._call_llm(
            tier="FLASH",
            model=os.getenv("MODEL_FLASH", "google/gemma-4-31B-it"),
            system_prompt=system_prompt,
            schema=_INCIDENT_SCHEMA,
            max_tokens=2048,
            temperature=0.1,
        )

        # ── 4. Validar respuesta ──────────────────────────────────────
        if response.get("mock_note") or response.get("error"):
            logger.warning(
                "extract_incident: LLM fallback/mock para seg=%s — %s",
                segment_id[:8],
                response.get("mock_note", response.get("error", "")),
            )
            # Insertar con valores default
            result = session.execute(
                text(
                    "INSERT INTO extracted_incidents "
                    "(id, segmento_id, documento_id, proyecto_id, "
                    "jot_text, keep_moving, tipo_dato_glaser, preguntas_glaser_json) "
                    "VALUES (gen_random_uuid(), :sid, :did, :pid, "
                    ":jot, true, :tdg, :pgj) "
                    "RETURNING id"
                ),
                {
                    "sid": segment_id,
                    "did": documento_id,
                    "pid": proyecto_id,
                    "jot": response.get("jot_text", "[MOCK] Procesando incidente"),
                    "tdg": "vague",
                    "pgj": json.dumps(
                        {
                            "what_is_this_about": response.get(
                                "what_is_this_about", ""
                            ),
                            "what_category": response.get("what_category", ""),
                            "what_is_happening": response.get("what_is_happening", ""),
                            "participants_pattern": response.get(
                                "participants_pattern", ""
                            ),
                            "confidence": response.get("confidence", 0.3),
                            "note": "mock_fallback",
                        }
                    ),
                },
            )
            session.commit()
            incident_id = str(result.fetchone()[0])
            return {
                "incident_id": incident_id,
                "segmento_id": segment_id,
                "documento_id": documento_id,
                "jot_text": response.get("jot_text", "[MOCK] Procesando incidente"),
                "keep_moving": True,
                "mock": True,
            }

        jot_text = (response.get("jot_text") or "").strip()
        keep_moving = response.get("keep_moving", True)
        confidence = response.get("confidence", 0.5)
        tipo_dato = response.get("tipo_dato_glaser") or "vague"

        if not jot_text:
            logger.warning("extract_incident: jot vacío para seg=%s", segment_id[:8])
            jot_text = "(jot no generado)"

        # ── 5. Insertar en extracted_incidents ─────────────────────────
        preguntas_json = {
            "what_is_this_about": response.get("what_is_this_about", ""),
            "what_category": response.get("what_category", ""),
            "what_is_happening": response.get("what_is_happening", ""),
            "participants_pattern": response.get("participants_pattern", ""),
            "confidence": confidence,
        }

        result = session.execute(
            text(
                "INSERT INTO extracted_incidents "
                "(id, segmento_id, documento_id, proyecto_id, "
                "jot_text, keep_moving, tipo_dato_glaser, preguntas_glaser_json) "
                "VALUES (gen_random_uuid(), :sid, :did, :pid, "
                ":jot, :km, :tdg, :pgj) "
                "RETURNING id"
            ),
            {
                "sid": segment_id,
                "did": documento_id,
                "pid": proyecto_id,
                "jot": jot_text,
                "km": keep_moving,
                "tdg": tipo_dato,
                "pgj": json.dumps(preguntas_json),
            },
        )
        session.commit()
        incident_id = str(result.fetchone()[0])

        logger.info(
            "extract_incident: incidente %s creado — jot='%s' keep_moving=%s",
            incident_id[:8],
            jot_text,
            keep_moving,
        )

        return {
            "incident_id": incident_id,
            "segmento_id": segment_id,
            "documento_id": documento_id,
            "jot_text": jot_text,
            "keep_moving": keep_moving,
            "confidence": confidence,
            "tipo_dato_glaser": tipo_dato,
        }

    except Exception:
        logger.exception(
            "extract_incident: error en seg=%s proyecto=%s",
            segment_id,
            proyecto_id,
        )
        return {"error": "exception", "segmento_id": segment_id}
    finally:
        session.close()
