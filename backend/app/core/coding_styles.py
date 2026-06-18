"""
Coding Style Library — Saldaña-inspired qualitative coding methods.

Cada estilo define:
- name: nombre legible
- instruction: inyectada en prompts de generación de códigos y renombres
- examples: ejemplos en español
- validation_pattern: regex opcional para validar que el LLM siguió el estilo

Uso:
    from app.core.coding_styles import CODING_STYLES, get_style_instruction
    instruction = get_style_instruction("gerundio")
    # → "Nombra cada código con un GERUNDIO (verbo terminado en -ando/-iendo)..."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════════════
# Definición de estilos
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class CodingStyle:
    key: str
    name: str
    instruction: str
    rename_instruction: str
    examples: list[str] = field(default_factory=list)
    saldana_category: str = ""  # Categoría en el manual de Saldaña


CODING_STYLES: dict[str, CodingStyle] = {
    # ── Gerundios (default CGT) ────────────────────────────
    "gerundio": CodingStyle(
        key="gerundio",
        name="Gerundios (Glaser)",
        instruction=(
            "Nombra cada código con un GERUNDIO (verbo terminado en -ando/-iendo). "
            "El gerundio debe capturar un PATRÓN DE COMPORTAMIENTO, no un tema estático. "
            "Ejemplos: 'Negociando límites', 'Evadiendo control', 'Balanceando riesgo'."
        ),
        rename_instruction=(
            "Sugiere renombres como GERUNDIOS. El nuevo nombre debe reflejar "
            "la definición expandida como un patrón de comportamiento activo."
        ),
        examples=[
            "Negociando límites",
            "Evadiendo control algorítmico",
            "Balanceando riesgo y visibilidad",
            "Construyendo confianza interdisciplinaria",
        ],
        saldana_category="Process Coding",
    ),
    # ── Verbos nominalizados (-ción, -miento) ──────────────
    "nominalizacion": CodingStyle(
        key="nominalizacion",
        name="Verbos nominalizados (-ción, -miento)",
        instruction=(
            "Nombra cada código con un SUSTANTIVO derivado de un verbo "
            "(terminado en -ción, -miento, -ancia, -ura). "
            "El nombre debe capturar el PROCESO como concepto abstracto. "
            "Ejemplos: 'Negociación de límites', 'Evitación del control', 'Balance de riesgo'."
        ),
        rename_instruction=(
            "Sugiere renombres como SUSTANTIVOS derivados de verbos. "
            "Prefiere -ción, -miento, -ancia."
        ),
        examples=[
            "Negociación de límites",
            "Evitación del control algorítmico",
            "Construcción de confianza",
            "Resistencia a la automatización",
        ],
        saldana_category="Process Coding (nominalized)",
    ),
    # ── Paráfrasis descriptiva ────────────────────────────
    "parafrasis": CodingStyle(
        key="parafrasis",
        name="Paráfrasis descriptiva",
        instruction=(
            "Nombra cada código con una FRASE CORTA que describa el contenido "
            "del segmento en tus propias palabras (no uses gerundios forzados). "
            "La frase debe capturar la IDEA CENTRAL en 3-8 palabras. "
            "Ejemplos: 'El algoritmo decide sin consultar', 'Aceptar pedidos no rentables para sobrevivir'."
        ),
        rename_instruction=(
            "Sugiere renombres como FRASES CORTAS descriptivas. "
            "Captura la idea central expandida en lenguaje natural."
        ),
        examples=[
            "El algoritmo decide sin consultar al repartidor",
            "Aceptar cualquier pedido por miedo a penalización",
            "Los veteranos enseñan estrategias a los nuevos",
        ],
        saldana_category="Descriptive Coding",
    ),
    # ── TEMA / subtema ────────────────────────────────────
    "tema_subtema": CodingStyle(
        key="tema_subtema",
        name="TEMA / subtema",
        instruction=(
            "Nombra cada código con un TEMA principal y, si aplica, un SUBTEMA "
            "separado por '→'. El tema debe ser un concepto abstracto, no una descripción. "
            "Ejemplos: 'Control algorítmico → Resistencia', 'Supervivencia económica → Estrategias adaptativas'."
        ),
        rename_instruction=(
            "Sugiere renombres como TEMA → subtema. "
            "Si la definición se expandió, el subtema puede refinarse o añadirse."
        ),
        examples=[
            "Control algorítmico → Resistencia cotidiana",
            "Supervivencia económica → Estrategias de corto plazo",
            "Identidad profesional → Amenaza percibida",
        ],
        saldana_category="Thematic Coding",
    ),
    # ── Cadenas causales ──────────────────────────────────
    "causal": CodingStyle(
        key="causal",
        name="Cadenas causales (A → B)",
        instruction=(
            "Nombra cada código como una CADENA CAUSAL usando '→' para indicar dirección. "
            "El código debe expresar: CONDICIÓN o CAUSA → CONSECUENCIA o ESTRATEGIA. "
            "Ejemplos: 'Falta de transparencia → Desconfianza en la plataforma', "
            "'Algoritmo opaco → Micro-resistencias adaptativas'."
        ),
        rename_instruction=(
            "Sugiere renombres como CADENAS CAUSALES (A → B). "
            "Si la definición se expandió, refina la causa o la consecuencia."
        ),
        examples=[
            "Falta de transparencia algorítmica → Desconfianza sistémica",
            "Penalización por rechazo → Aceptación de pedidos no rentables",
            "Experiencia acumulada → Sofisticación de estrategias de evasión",
        ],
        saldana_category="Causal Coding",
    ),
    # ── In Vivo (citas literales) ─────────────────────────
    "in_vivo": CodingStyle(
        key="in_vivo",
        name="In Vivo (citas literales)",
        instruction=(
            "Nombra cada código usando una CITA TEXTUAL CORTA del participante "
            "(entre comillas). La cita debe capturar una expresión llamativa, "
            "una metáfora nativa, o un término que el participante usa repetidamente. "
            "Ejemplos: '\"la aplicación no te dice nada\"', '\"cada uno tiene su maña\"', '\"acepto las que valen\"'."
        ),
        rename_instruction=(
            "Sugiere renombres como CITAS TEXTUALES del participante. "
            "Solo sugiere renombre si encontrás una cita MÁS PRECISA que la actual."
        ),
        examples=[
            '"la aplicación no te dice nada"',
            '"cada uno tiene su maña"',
            '"si no acepto, me quedo sin nada"',
        ],
        saldana_category="In Vivo Coding",
    ),
}


# ═══════════════════════════════════════════════════════════════════════
# API pública
# ═══════════════════════════════════════════════════════════════════════


def get_style(key: str) -> CodingStyle:
    """Obtiene un estilo por key. Fallback a gerundio."""
    return CODING_STYLES.get(key, CODING_STYLES["gerundio"])


def get_code_instruction(key: str) -> str:
    """Instrucción para prompts de generación de códigos (b2b, incident_elaborator)."""
    return get_style(key).instruction


def get_rename_instruction(key: str) -> str:
    """Instrucción para prompts de renombre (incident_elaborator)."""
    return get_style(key).rename_instruction


def get_examples(key: str) -> list[str]:
    """Ejemplos del estilo para inyectar en prompts."""
    return get_style(key).examples


def get_all_styles() -> list[dict]:
    """Lista de estilos disponibles para el frontend (selector UI)."""
    return [
        {
            "key": s.key,
            "name": s.name,
            "saldana_category": s.saldana_category,
            "examples": s.examples[:2],
        }
        for s in CODING_STYLES.values()
    ]


def get_default_style() -> str:
    """Estilo default para CGT: gerundio."""
    return "gerundio"


def get_default_style_instruction() -> str:
    """Instrucción default para prompts: gerundio."""
    return get_code_instruction(get_default_style())


# ═══════════════════════════════════════════════════════════════════════
# Soporte multi-estilo
# ═══════════════════════════════════════════════════════════════════════


def get_combined_instruction(keys: list[str]) -> str:
    """
    Combina instrucciones de múltiples estilos en una sola.
    El investigador puede elegir varios estilos simultáneamente.
    Ej: ["gerundio", "in_vivo"] → instrucción que permite ambos.
    """
    if not keys:
        keys = ["gerundio"]
    if len(keys) == 1:
        return get_code_instruction(keys[0])

    instructions = [get_style(k).instruction for k in keys if k in CODING_STYLES]
    combined = (
        "Puedes usar CUALQUIERA de estos estilos de codificación:\n"
        + "\n".join(f"  • {i}" for i in instructions)
        + "\n\nElige el estilo más adecuado para cada código según el contenido del segmento."
    )
    return combined


def get_combined_rename_instruction(keys: list[str]) -> str:
    """Combina instrucciones de renombre de múltiples estilos."""
    if not keys:
        keys = ["gerundio"]
    if len(keys) == 1:
        return get_rename_instruction(keys[0])

    instructions = [get_style(k).rename_instruction for k in keys if k in CODING_STYLES]
    combined = (
        "Puedes sugerir renombres en CUALQUIERA de estos estilos:\n"
        + "\n".join(f"  • {i}" for i in instructions)
        + "\n\nElige el estilo más adecuado según cómo evolucionó la definición."
    )
    return combined


def get_default_styles() -> list[str]:
    """Estilos default para CGT: gerundio + in_vivo."""
    return ["gerundio", "in_vivo"]
