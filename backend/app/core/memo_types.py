# backend/app/core/memo_types.py
"""Tipos de memo disponibles por etapa del proyecto.

Usado por:
- GET /available-memo-types: dropdown del frontend
- POST /memos: validación de tipo permitido
- MemoHistory: filtros por entity type
"""

META = {
    "HIPOTESIS": {
        "label": "Hipótesis",
        "icon": "💡",
        "color": "#D29922",
        "description": "Hipótesis emergente sobre relaciones entre conceptos",
    },
    "CATEGORIA": {
        "label": "Categoría",
        "icon": "🏷️",
        "color": "#A371F7",
        "description": "Categoría de investigación. Se persiste en la tabla categorias.",
    },
    "PROPIEDAD": {
        "label": "Propiedad",
        "icon": "📐",
        "color": "#58A6FF",
        "description": "Propiedad o dimensión de una categoría existente",
    },
    "RELACION": {
        "label": "Relación",
        "icon": "🔗",
        "color": "#3FB950",
        "description": "Relación conceptual entre categorías",
    },
    "METODOLOGICO": {
        "label": "Metodológico",
        "icon": "📋",
        "color": "#8B949E",
        "description": "Nota sobre el método, decisiones de muestreo, ajustes al diseño",
    },
    "MUESTREO": {
        "label": "Muestreo",
        "icon": "🎯",
        "color": "#FF6B35",
        "description": "Criterios de inclusión/exclusión, dimensiones de muestreo teórico",
    },
    "GENERAL": {
        "label": "General",
        "icon": "📝",
        "color": "#79C0FF",
        "description": "Observación, idea, o reflexión no categorizada",
    },
    "TEORICO": {
        "label": "Código Teórico",
        "icon": "🔬",
        "color": "#FF6B35",
        "description": "Familia teórica personalizada (las 12 built-in no se tocan). Requiere structured_fields.",
    },
    "DATABASE_NODE": {
        "label": "Nodo (DB A)",
        "icon": "🟦",
        "color": "#79C0FF",
        "description": "Nodo del modelo teórico plano. Requiere entity_type.",
    },
    "DATABASE_EDGE": {
        "label": "Edge (DB B)",
        "icon": "➡️",
        "color": "#3FB950",
        "description": "Relación del modelo teórico. Requiere source/target + relationship_type.",
    },
}

STAGE_ORDER = [
    "collecting",
    "coding",
    "finding_cc",
    "reducing",
    "saturating",
    "building_db",
    "playground_ready",
    "completed",
]

MEMO_TYPES_BY_STAGE: dict[str, list[str]] = {
    "collecting": ["METODOLOGICO", "MUESTREO", "GENERAL"],
    "coding": ["HIPOTESIS", "METODOLOGICO", "MUESTREO", "PROPIEDAD", "GENERAL"],
    "finding_cc": [
        "HIPOTESIS",
        "CATEGORIA",
        "PROPIEDAD",
        "RELACION",
        "METODOLOGICO",
        "MUESTREO",
        "GENERAL",
    ],
    "reducing": [
        "HIPOTESIS",
        "CATEGORIA",
        "PROPIEDAD",
        "RELACION",
        "METODOLOGICO",
        "MUESTREO",
        "GENERAL",
    ],
    "saturating": [
        "HIPOTESIS",
        "CATEGORIA",
        "PROPIEDAD",
        "RELACION",
        "METODOLOGICO",
        "MUESTREO",
        "GENERAL",
    ],
    "building_db": [
        "HIPOTESIS",
        "CATEGORIA",
        "PROPIEDAD",
        "RELACION",
        "DATABASE_NODE",
        "DATABASE_EDGE",
        "METODOLOGICO",
        "MUESTREO",
        "GENERAL",
    ],
    "playground_ready": [
        "HIPOTESIS",
        "CATEGORIA",
        "PROPIEDAD",
        "RELACION",
        "TEORICO",
        "DATABASE_NODE",
        "DATABASE_EDGE",
        "METODOLOGICO",
        "MUESTREO",
        "GENERAL",
    ],
    "completed": [
        "HIPOTESIS",
        "CATEGORIA",
        "PROPIEDAD",
        "RELACION",
        "TEORICO",
        "DATABASE_NODE",
        "DATABASE_EDGE",
        "METODOLOGICO",
        "MUESTREO",
        "GENERAL",
    ],
}


def get_types_for_stage(stage: str) -> list[dict]:
    """Devuelve tipos disponibles enriquecidos con metadata."""
    keys = MEMO_TYPES_BY_STAGE.get(stage, MEMO_TYPES_BY_STAGE["collecting"])
    return [{"key": k, **META[k]} for k in keys if k in META]


def get_all_types() -> list[dict]:
    """Todos los tipos con metadata (para filtros del frontend)."""
    return [{"key": k, **v} for k, v in META.items()]


def get_stage_index(stage: str) -> int:
    """Índice ordinal de la etapa. -1 si no existe."""
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def family_to_entity_type(family: str) -> str:
    """Mapea agent_family → entity type para filtros de memos del sistema."""
    _map = {
        "inductive_data": "CATEGORIA",
        "inductive_concepts": "HIPOTESIS",
        "descriptive_data": "METODOLOGICO",
        "structural": "DATABASE_NODE",
        "elaborative": "RELACION",
        "evaluative": "CATEGORIA",
    }
    return _map.get(family, "GENERAL")
