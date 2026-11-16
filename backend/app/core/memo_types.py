# backend/app/core/memo_types.py
"""Fuente única del catálogo de categorías de memo, localizado a en/es/de/pt.

Cada entrada de ``META`` define icono, color, agente requerido y las
etiquetas/descripciones en los cuatro idiomas soportados. Usado por:
- GET /entity-type-colors: filtros y badges del historial de memos
- GET /available-memo-types: dropdown del modal "Añadir memo"
- POST/PATCH /memos: validación de tipo
"""

SUPPORTED_LANGS = ("en", "es", "de", "pt")
DEFAULT_LANG = "es"

META = {
    "HIPOTESIS": {
        "icon": "💡",
        "color": "#D29922",
        "requires_agent": "fb_hypothesis_generator",
        "labels": {
            "en": "Hypothesis",
            "es": "Hipótesis",
            "de": "Hypothese",
            "pt": "Hipótese",
        },
        "descriptions": {
            "en": "Emerging hypothesis about relationships between concepts",
            "es": "Hipótesis emergente sobre relaciones entre conceptos",
            "de": "Aufkommende Hypothese über Beziehungen zwischen Konzepten",
            "pt": "Hipótese emergente sobre relações entre conceitos",
        },
    },
    "CATEGORIA": {
        "icon": "🏷️",
        "color": "#A371F7",
        "requires_agent": "fd_category_synthesizer",
        "labels": {
            "en": "Category",
            "es": "Categoría",
            "de": "Kategorie",
            "pt": "Categoria",
        },
        "descriptions": {
            "en": "Research category. It is persisted to the categorias table.",
            "es": "Categoría de investigación. Se persiste en la tabla categorias.",
            "de": "Forschungskategorie. Sie wird in der Tabelle categorias gespeichert.",
            "pt": "Categoria de investigação. É persistida na tabela categorias.",
        },
    },
    "PROPIEDAD": {
        "icon": "📐",
        "color": "#58A6FF",
        "requires_agent": "fb_code_generator",
        "labels": {
            "en": "Property",
            "es": "Propiedad",
            "de": "Eigenschaft",
            "pt": "Propriedade",
        },
        "descriptions": {
            "en": "Property or dimension of an existing category",
            "es": "Propiedad o dimensión de una categoría existente",
            "de": "Eigenschaft oder Dimension einer bestehenden Kategorie",
            "pt": "Propriedade ou dimensão de uma categoria existente",
        },
    },
    "RELACION": {
        "icon": "🔗",
        "color": "#3FB950",
        "requires_agent": "fd_category_synthesizer",
        "labels": {
            "en": "Relationship",
            "es": "Relación",
            "de": "Beziehung",
            "pt": "Relação",
        },
        "descriptions": {
            "en": "Conceptual relationship between categories",
            "es": "Relación conceptual entre categorías",
            "de": "Konzeptionelle Beziehung zwischen Kategorien",
            "pt": "Relação conceitual entre categorias",
        },
    },
    "METODOLOGICO": {
        "icon": "📋",
        "color": "#8B949E",
        "labels": {
            "en": "Methodological",
            "es": "Metodológico",
            "de": "Methodisch",
            "pt": "Metodológico",
        },
        "descriptions": {
            "en": "Note about the method, sampling decisions, design adjustments",
            "es": "Nota sobre el método, decisiones de muestreo, ajustes al diseño",
            "de": "Notiz zur Methode, zu Sampling-Entscheidungen, Design-Anpassungen",
            "pt": "Nota sobre o método, decisões de amostragem, ajustes ao desenho",
        },
    },
    "MUESTREO": {
        "icon": "🎯",
        "color": "#FF6B35",
        "labels": {
            "en": "Sampling",
            "es": "Muestreo",
            "de": "Sampling",
            "pt": "Amostragem",
        },
        "descriptions": {
            "en": "Inclusion/exclusion criteria, theoretical sampling dimensions",
            "es": "Criterios de inclusión/exclusión, dimensiones de muestreo teórico",
            "de": "Ein-/Ausschlusskriterien, Dimensionen des theoretischen Samplings",
            "pt": "Critérios de inclusão/exclusão, dimensões de amostragem teórica",
        },
    },
    "GENERAL": {
        "icon": "📝",
        "color": "#79C0FF",
        "labels": {
            "en": "General",
            "es": "General",
            "de": "General",
            "pt": "General",
        },
        "descriptions": {
            "en": "Uncategorized observation, idea, or reflection",
            "es": "Observación, idea, o reflexión no categorizada",
            "de": "Nicht kategorisierte Beobachtung, Idee oder Reflexion",
            "pt": "Observação, ideia ou reflexão não categorizada",
        },
    },
    "TEORICO": {
        "icon": "🔬",
        "color": "#FF6B35",
        "requires_agent": "fc_main_concern_proposer",
        "labels": {
            "en": "Theoretical code",
            "es": "Código Teórico",
            "de": "Theoretischer Code",
            "pt": "Código teórico",
        },
        "descriptions": {
            "en": "Custom theoretical family (the 12 built-in ones are left untouched). "
            "Requires structured_fields.",
            "es": "Familia teórica personalizada (las 12 built-in no se tocan). "
            "Requiere structured_fields.",
            "de": "Benutzerdefinierte theoretische Familie (die 12 eingebauten bleiben "
            "unberührt). Erfordert structured_fields.",
            "pt": "Família teórica personalizada (as 12 built-in não são alteradas). "
            "Requer structured_fields.",
        },
    },
    "DATABASE_NODE": {
        "icon": "🟦",
        "color": "#79C0FF",
        "requires_agent": "ff_database_a_proposer",
        "labels": {
            "en": "Node (DB A)",
            "es": "Nodo (DB A)",
            "de": "Knoten (DB A)",
            "pt": "Nó (DB A)",
        },
        "descriptions": {
            "en": "Node of the flat theoretical model. Requires entity_type.",
            "es": "Nodo del modelo teórico plano. Requiere entity_type.",
            "de": "Knoten des flachen theoretischen Modells. Erfordert entity_type.",
            "pt": "Nó do modelo teórico plano. Requer entity_type.",
        },
    },
    "DATABASE_EDGE": {
        "icon": "➡️",
        "color": "#3FB950",
        "requires_agent": "ff_database_b_proposer",
        "labels": {
            "en": "Edge (DB B)",
            "es": "Edge (DB B)",
            "de": "Kante (DB B)",
            "pt": "Aresta (DB B)",
        },
        "descriptions": {
            "en": "Relationship of the theoretical model. Requires source/target + "
            "relationship_type.",
            "es": "Relación del modelo teórico. Requiere source/target + relationship_type.",
            "de": "Beziehung des theoretischen Modells. Erfordert source/target + "
            "relationship_type.",
            "pt": "Relação do modelo teórico. Requer source/target + relationship_type.",
        },
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


def _normalize_lang(lang: str | None) -> str:
    if lang and lang.lower() in SUPPORTED_LANGS:
        return lang.lower()
    return DEFAULT_LANG


def _localized(key: str, lang: str | None = None) -> dict:
    """Entrada del catálogo con label/description resueltos al idioma pedido."""
    lang = _normalize_lang(lang)
    meta = META[key]
    entry = {
        "key": key,
        "label": meta["labels"][lang],
        "icon": meta["icon"],
        "color": meta["color"],
        "description": meta["descriptions"][lang],
    }
    if meta.get("requires_agent"):
        entry["requires_agent"] = meta["requires_agent"]
    return entry


def get_all_types(lang: str | None = None) -> list[dict]:
    """Todos los tipos con metadata (para filtros del frontend)."""
    return [_localized(k, lang) for k in META]


def get_types_for_stage(stage: str, lang: str | None = None) -> list[dict]:
    """Devuelve tipos disponibles enriquecidos con metadata."""
    keys = MEMO_TYPES_BY_STAGE.get(stage, MEMO_TYPES_BY_STAGE["collecting"])
    return [_localized(k, lang) for k in keys if k in META]


def get_all_type_keys() -> list[str]:
    """Claves de todas las categorías del catálogo."""
    return list(META)


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
