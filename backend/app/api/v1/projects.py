import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.core.nlp_models import get_current_spacy
from app.db.database import get_db
from app.models.domain.category import Categoria
from app.models.domain.document import Documento
from app.models.domain.project import Proyecto
from app.models.domain.project_config_history import ProjectConfigHistory
from app.models.domain.user import Usuario
from app.schemas import ProjectCreate, ProjectResponse
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# ── spaCy model (lazy-loaded via model manager) ───────────────────────


def _get_nlp():
    """Lazy-load the spaCy model via the model manager."""
    return get_current_spacy()


# ── Spanish equivalents for canonical object_of_study types ──

_OOS_SPANISH_MAP: dict[str, str] = {
    "concern": "preocupación",
    "emotion": "emoción",
    "behavior": "comportamiento",
    "discourse": "discurso",
    "identity": "identidad",
}

# ── Similarity thresholds ──

_SUGGEST_THRESHOLD = 0.5  # if similarity > this, suggest the canonical type
_ACCEPT_THRESHOLD = 0.3  # if similarity < this to ALL types, accept as custom


def _validate_custom_label_with_spacy(
    custom_label: str,
) -> dict:
    """
    Run spaCy semantic similarity between custom_label and the 5 canonical types
    (using their Spanish equivalents).

    Returns a dict with:
        - suggestion: canonical type to suggest (or None)
        - similarities: {canonical_type: similarity_score}
        - accepted: bool (True if custom label is distinct enough)
    """
    if not custom_label or not custom_label.strip():
        return {"suggestion": None, "similarities": {}, "accepted": True}

    nlp = _get_nlp()
    label_doc = nlp(custom_label.strip())

    similarities: dict[str, float] = {}
    for canonical, spanish in _OOS_SPANISH_MAP.items():
        canonical_doc = nlp(spanish)
        sim = label_doc.similarity(canonical_doc)
        similarities[canonical] = round(float(sim), 4)

    # Check for suggestion: is custom_label similar to any canonical type?
    max_sim = max(similarities.values()) if similarities else 0.0
    suggestion: str | None = None
    if max_sim > _SUGGEST_THRESHOLD:
        # Find the canonical type with highest similarity
        suggestion = max(similarities, key=lambda k: similarities[k])

    # Accept if below threshold to ALL types (truly distinct)
    accepted = max_sim < _ACCEPT_THRESHOLD

    return {
        "suggestion": suggestion,
        "similarities": similarities,
        "accepted": accepted,
        "max_similarity": round(max_sim, 4),
    }


# ── Population article helper (avoids double articles like "los los docentes") ──
_POP_ARTICLES = {
    "el",
    "la",
    "los",
    "las",
    "o",
    "a",
    "os",
    "as",
    "the",
    "der",
    "die",
    "das",
}


def _format_population_phrase(article: str, population: str) -> str:
    """Return 'article population' but skip article if population already starts with one."""
    pop_lower = population.strip().lower()
    first_word = pop_lower.split()[0] if pop_lower else ""
    if first_word in _POP_ARTICLES:
        return population
    return f"{article} {population}"


# ── Stem-changing verb lookup (infinitive → 3sg, 3pl) ──
_STEM_CHANGING = {
    "resolver": ("resuelve", "resuelven"),
    "poder": ("puede", "pueden"),
    "volver": ("vuelve", "vuelven"),
    "pensar": ("piensa", "piensan"),
    "querer": ("quiere", "quieren"),
    "pedir": ("pide", "piden"),
    "sentir": ("siente", "sienten"),
    "encontrar": ("encuentra", "encuentran"),
    "recordar": ("recuerda", "recuerdan"),
    "dormir": ("duerme", "duermen"),
    "jugar": ("juega", "juegan"),
    "construir": ("construye", "construyen"),
    "interpretar": ("interpreta", "interpretan"),
}


def _conjugate_verb(verb: str, population: str) -> str:
    """Conjugate processing_verb to match population (always plural 3rd person).

    Uses spaCy to detect language. For Spanish, applies basic 3rd-person-plural
    conjugation rules. For English, returns the verb unchanged (no plural conjugation).
    """
    result = _conjugate_verb_full(verb, population)
    return result["verb"]


def _conjugate_verb_full(verb: str, population: str) -> dict:
    """Conjugate verb and detect population number/gender via spaCy.

    Returns dict with:
      - verb: conjugated verb (3rd person, matching population number)
      - number: "singular" | "plural"
      - gender: "masculine" | "feminine" | None
      - article: "el"/"la"/"los"/"las" (Spanish) or "the" (English)
      - language: detected language code
    """
    if not verb or not population:
        return {
            "verb": verb or "resolve",
            "number": "plural",
            "gender": None,
            "article": "the",
            "language": "en",
        }

    try:
        nlp = _get_nlp()
        pop_doc = nlp(population[:100])
        lang = nlp.meta.get("lang", "en")
        is_spanish = lang == "es"
        if not is_spanish:
            es_tokens = sum(
                1 for t in pop_doc if hasattr(t, "lang_") and t.lang_ == "es"
            )
            en_tokens = sum(
                1 for t in pop_doc if hasattr(t, "lang_") and t.lang_ == "en"
            )
            if es_tokens > en_tokens:
                is_spanish = True
                lang = "es"
    except Exception:
        # spaCy not available — fall back to simple heuristics
        lang = "es" if any(c in population.lower() for c in "áéíóúñü") else "en"
        is_spanish = lang == "es"
    verb_lower = verb.lower().strip()
    is_portuguese = lang == "pt"
    is_german = lang == "de"

    # ── Detect population number & gender via spaCy morphology ──
    pop_lower = population.strip().lower()
    tokens = pop_lower.split()

    number = "singular"
    gender = None
    article = "the"

    # spaCy-first: use morphological analysis for ALL languages
    try:
        for token in pop_doc:
            morph_num = token.morph.get("Number")
            if morph_num:
                number = "plural" if "Plur" in morph_num else "singular"
                morph_gen = token.morph.get("Gender")
                if morph_gen:
                    gender = "masculine" if "Masc" in morph_gen else "feminine"
                break
    except Exception:
        pass  # spaCy unavailable, fall through to heuristics

    # Build article from detected number/gender
    if is_spanish or is_portuguese:
        if not gender:
            # Fallback: check articles
            plural_arts = {"los", "las", "os", "as", "uns", "umas"}
            singular_arts = {"el", "la", "o", "a", "um", "uma"}
            masc_arts = {"el", "los", "un", "unos", "o", "os", "um", "uns"}
            for tok in tokens:
                if tok in plural_arts:
                    number, gender = (
                        "plural",
                        ("masculine" if tok in masc_arts else "feminine"),
                    )
                    article = tok
                    break
                if tok in singular_arts:
                    number, gender = (
                        "singular",
                        ("masculine" if tok in masc_arts else "feminine"),
                    )
                    article = tok
                    break
        if not gender:
            gender = "masculine"  # default for Spanish/Portuguese
        if is_spanish:
            article = (
                "los"
                if gender == "masculine" and number == "plural"
                else "las"
                if gender == "feminine" and number == "plural"
                else "el"
                if gender == "masculine"
                else "la"
            )
        else:
            article = (
                "os"
                if gender == "masculine" and number == "plural"
                else "as"
                if gender == "feminine" and number == "plural"
                else "o"
                if gender == "masculine"
                else "a"
            )

        # Conjugation
        if is_spanish:
            forms = _conjugate_spanish_verb(verb_lower)
            conjugated = forms["pl"] if number == "plural" else forms["sg"]
        else:
            if number == "plural":
                if verb_lower.endswith("ar"):
                    conjugated = verb_lower[:-2] + "am"
                elif verb_lower.endswith("er") or verb_lower.endswith("ir"):
                    conjugated = verb_lower[:-2] + "em"
                else:
                    conjugated = verb_lower
            else:
                if verb_lower.endswith("ar"):
                    conjugated = verb_lower[:-2] + "a"
                elif verb_lower.endswith("er") or verb_lower.endswith("ir"):
                    conjugated = verb_lower[:-2] + "e"
                else:
                    conjugated = verb_lower

    elif is_german:
        article = "die"
        for tok in tokens:
            if tok in {"der", "die", "das", "den", "dem", "des"}:
                article = tok
                number = "singular" if tok in {"der", "die", "das"} else "plural"
                break
        if number == "plural":
            conjugated = (
                verb_lower + "en" if not verb_lower.endswith("en") else verb_lower
            )
        else:
            conjugated = (
                verb_lower[:-2] + "t" if verb_lower.endswith("en") else verb_lower + "t"
            )

    else:
        # English / other: spaCy already set number; just conjugate (no conjugation in English)
        conjugated = verb_lower

    return {
        "verb": conjugated,
        "number": number,
        "gender": gender,
        "article": article,
        "language": lang,
    }


# ── Pattern noun metadata (for article/pronoun agreement across languages) ──
_PATTERN_META = {
    "concern": {
        "es": {
            "noun": "preocupación",
            "gender": "f",
            "plural": "preocupaciones",
        },
        "en": {"noun": "concern", "plural": "concerns"},
        "de": {"noun": "Sorge", "gender": "f", "plural": "Sorgen"},
        "pt": {"noun": "preocupação", "gender": "f", "plural": "preocupações"},
    },
    "emotion": {
        "es": {
            "noun": "emoción",
            "gender": "f",
            "plural": "emociones",
        },
        "en": {"noun": "emotion", "plural": "emotions"},
        "de": {
            "noun": "Emotion",
            "gender": "f",
            "plural": "Emotionen",
        },
        "pt": {
            "noun": "emoção",
            "gender": "f",
            "plural": "emoções",
        },
    },
    "behavior": {
        "es": {
            "noun": "conducta",
            "gender": "f",
            "plural": "conductas",
        },
        "en": {"noun": "behavior", "plural": "behaviors"},
        "de": {
            "noun": "Verhalten",
            "gender": "n",
            "plural": "Verhalten",
        },
        "pt": {
            "noun": "comportamento",
            "gender": "m",
            "plural": "comportamentos",
        },
    },
    "discourse": {
        "es": {
            "noun": "narrativa compartida",
            "gender": "f",
            "plural": "narrativas compartidas",
        },
        "en": {"noun": "shared narrative", "plural": "shared narratives"},
        "de": {
            "noun": "geteiltes Narrativ",
            "gender": "n",
            "plural": "geteilte Narrative",
        },
        "pt": {
            "noun": "narrativa compartilhada",
            "gender": "f",
            "plural": "narrativas compartilhadas",
        },
    },
    "identity": {
        "es": {
            "noun": "negociación de identidad",
            "gender": "f",
            "plural": "negociaciones de identidad",
        },
        "en": {"noun": "identity negotiation", "plural": "identity negotiations"},
        "de": {
            "noun": "Identitätsverhandlung",
            "gender": "f",
            "plural": "Identitätsverhandlungen",
        },
        "pt": {
            "noun": "negociação de identidade",
            "gender": "f",
            "plural": "negociações de identidade",
        },
    },
    "meaning": {
        "es": {
            "noun": "significado",
            "gender": "m",
            "plural": "significados",
        },
        "en": {"noun": "meaning", "plural": "meanings"},
        "de": {
            "noun": "Bedeutung",
            "gender": "f",
            "plural": "Bedeutungen",
        },
        "pt": {
            "noun": "significado",
            "gender": "m",
            "plural": "significados",
        },
    },
    "custom": {
        "es": {"noun": "patrón", "gender": "m", "plural": "patrones"},
        "en": {"noun": "pattern", "plural": "patterns"},
        "de": {"noun": "Muster", "gender": "n", "plural": "Muster"},
        "pt": {"noun": "padrão", "gender": "m", "plural": "padrões"},
    },
}
# ── Core qualifier word per language (inserted by templates at correct position) ──
_CORE_WORD = {
    "es": "principal",
    "en": "core",
    "de": "zentrale",
    "pt": "principal",
}

# ── Spanish verb conjugator (3rd person present indicative) ──

# Stem-changing patterns: infinitive ending determines the stem change
_STEM_CHANGE = {
    # o → ue
    "acordar": "acuerd",
    "acostar": "acuest",
    "almorzar": "almuerz",
    "aprobar": "aprueb",
    "colgar": "cuelg",
    "contar": "cuent",
    "costar": "cuest",
    "demostrar": "demuestr",
    "devolver": "devuelv",
    "dormir": "duerm",
    "encontrar": "encuentr",
    "envolver": "envuelv",
    "morder": "muerd",
    "morir": "muer",
    "mostrar": "muestr",
    "mover": "muev",
    "poder": "pued",
    "probar": "prueb",
    "recordar": "recuerd",
    "resolver": "resuelv",
    "rogar": "rueg",
    "soler": "suel",
    "sonar": "suen",
    "soñar": "sueñ",
    "tostar": "tuest",
    "volar": "vuel",
    "volver": "vuelv",
    # e → ie
    "acertar": "aciert",
    "advertir": "advirt",
    "calentar": "calient",
    "cerrar": "cierr",
    "comenzar": "comienz",
    "confesar": "confies",
    "convertir": "convirt",
    "defender": "defiend",
    "despertar": "despiert",
    "divertir": "divirt",
    "empezar": "empiez",
    "encender": "enciend",
    "entender": "entiend",
    "fregar": "frieg",
    "gobernar": "gobiern",
    "hervir": "hirv",
    "mentir": "mient",
    "negar": "nieg",
    "nevar": "niev",
    "pensar": "piens",
    "perder": "pierd",
    "preferir": "prefir",
    "querer": "quier",
    "regar": "rieg",
    "sentar": "sient",
    "sentir": "sient",
    "sugerir": "sugir",
    "temblar": "tiembl",
    "tender": "tiend",
    "venir": "vien",
    "verter": "viert",
    # e → i
    "competir": "compit",
    "conseguir": "consig",
    "corregir": "corrig",
    "decir": "dic",
    "despedir": "despid",
    "elegir": "elig",
    "freír": "frí",
    "medir": "mid",
    "pedir": "pid",
    "perseguir": "persig",
    "reír": "rí",
    "repetir": "repit",
    "seguir": "sig",
    "servir": "sirv",
    "sonreír": "sonrí",
    "vestir": "vist",
    # Fully irregular (3rd person forms)
    "ir": "va",
    "ser": "es",
    "estar": "está",
    "haber": "ha",
    "saber": "sabe",
    "dar": "da",
    "ver": "ve",
    "caber": "cabe",
    "caer": "cae",
    "traer": "trae",
    "oír": "oye",
    "construir": "construye",
    "huir": "huye",
    "incluir": "incluye",
    "concluir": "concluye",
    "destruir": "destruye",
    "sustituir": "sustituye",
    "tener": "tiene",
    "poner": "pone",
    "salir": "sale",
    "hacer": "hace",
    "valer": "vale",
    "conocer": "conoce",
    "parecer": "parece",
    "crecer": "crece",
    "nacer": "nace",
    "conducir": "conduce",
    "producir": "produce",
    "traducir": "traduce",
    "lucir": "luce",
}


def _conjugate_spanish_verb(verb: str) -> dict:
    """Return {sg: 3rd-singular, pl: 3rd-plural} present indicative for a Spanish verb."""
    v = verb.lower().strip()
    if not v:
        return {"sg": v, "pl": v}

    # Check fully irregular (returned form is the singular stem)
    if v in _STEM_CHANGE:
        stem = _STEM_CHANGE[v]
        # Fully irregular: stem IS the 3sg form, plural adds -n
        if v in {
            "ir",
            "ser",
            "estar",
            "haber",
            "saber",
            "dar",
            "ver",
            "caber",
            "caer",
            "traer",
            "oír",
            "tener",
            "poner",
            "salir",
            "hacer",
            "valer",
            "conocer",
            "parecer",
            "crecer",
            "nacer",
            "conducir",
            "producir",
            "traducir",
            "lucir",
        }:
            return {"sg": stem, "pl": stem + "n"}
        if v in {"decir"}:
            return {"sg": stem + "e", "pl": stem + "en"}
        # construir-type: -uir → -uye/-uyen
        if v.endswith("uir") and stem.endswith("ye"):
            return {"sg": stem, "pl": stem + "n"}
        # venir: vien → viene/vienen
        if v == "venir":
            return {"sg": stem + "e", "pl": stem + "en"}
        # sentir-type: stem-change + regular endings
        return {"sg": stem + "e", "pl": stem + "en"}

    # Regular verbs
    if v.endswith("ar"):
        return {"sg": v[:-2] + "a", "pl": v[:-2] + "an"}
    elif v.endswith("er"):
        return {"sg": v[:-2] + "e", "pl": v[:-2] + "en"}
    elif v.endswith("ir"):
        return {"sg": v[:-2] + "e", "pl": v[:-2] + "en"}
    else:
        return {"sg": v, "pl": v}


# ── Declarative question templates per language ──
# Variables available: {pop}, {pat_art}, {noun}, {core}, {plural},
#                       {pron_sg}, {pron_pl}, {verb}, {pop_raw}

_QUESTION_TEMPLATES = {
    "es": {
        "rq": "¿Cuál es {pat_art} {noun} {core} de {pop} y cómo {pron_sg} {verb} continuamente?",
        "oq_discovery": "¿Qué {plural} comunes hay en {pop} y cómo {pron_pl} {verb}?",
        "oq_selective": "¿En qué maneras {pop} {verb} su {noun} {core}?",
        "oq_theoretical": "¿Qué proceso explica cómo {pop} {verb} {pat_art} {noun} {core}?",
    },
    "en": {
        "rq": "What is the {core} {noun} of {pop_raw} and how do they continuously {verb} {pron_sg}?",
        "oq_discovery": "What common {plural} exist in {pop_raw} and how do they {verb} {pron_pl}?",
        "oq_selective": "In what ways does {pop_raw} {verb} its {core} {noun}?",
        "oq_theoretical": "What process explains how {pop_raw} {verb} the {core} {noun}?",
    },
    "pt": {
        "rq": "Qual é {pat_art} {noun} {core} de {pop} e como {pron_sg} {verb} continuamente?",
        "oq_discovery": "Quais {plural} comuns existem em {pop} e como {pron_pl} {verb}?",
        "oq_selective": "Em que maneiras {pop} {verb} seu {noun} {core}?",
        "oq_theoretical": "Que processo explica como {pop} {verb} {pat_art} {noun} {core}?",
    },
    "de": {
        "rq": "Was ist {pat_art} {core} {noun} von {pop} und wie {verb} {pron_sg} kontinuierlich?",
        "oq_discovery": "Welche häufigen {plural} gibt es bei {pop} und wie {verb} sie diese?",
        "oq_selective": "Auf welche Weise {verb} {pop} sein {noun} {core}?",
        "oq_theoretical": "Welcher Prozess erklärt, wie {pop} {pat_art} {noun} {core} {verb}?",
    },
}


def _build_questions(
    lang: str,
    pop_phrase: str,
    population: str,
    pat_art: str,
    pattern_noun: str,
    pattern_plural: str,
    pronoun_sg: str,
    pronoun_pl: str,
    conjugated: str,
) -> dict:
    """Build all question variants from a declarative template."""
    core_word = _CORE_WORD.get(lang, "core")
    templates = _QUESTION_TEMPLATES.get(lang, _QUESTION_TEMPLATES["en"])

    vars_dict = {
        "pop": pop_phrase,
        "pop_raw": population,
        "pat_art": pat_art,
        "noun": pattern_noun,
        "core": core_word,
        "plural": pattern_plural,
        "pron_sg": pronoun_sg,
        "pron_pl": pronoun_pl,
        "verb": conjugated,
    }

    return {
        "research_question": templates["rq"].format(**vars_dict),
        "oq_discovery": templates["oq_discovery"].format(**vars_dict),
        "oq_selective": templates["oq_selective"].format(**vars_dict),
        "oq_theoretical": templates["oq_theoretical"].format(**vars_dict),
    }


def _detect_singular_population(population: str) -> str | None:
    """Check if population description appears singular (warn but don't block).

    Returns a warning message if singular detected, None otherwise.
    """
    if not population or not population.strip():
        return None

    singular_articles = {"un", "una", "el", "la"}
    tokens = population.strip().lower().split()

    for i, tok in enumerate(tokens):
        if tok in singular_articles:
            return (
                f"Population description appears singular (contains '{tok}'). "
                "The population_generalizer will pluralize it."
            )

    return None


router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

# ── Política de mutación por defecto ──────────────────────────────────

DEFAULT_MUTATION_POLICY: dict[str, str] = {
    "population_description": "suggest",
    "temporal_frame": "suggest",
    "spatial_frame": "suggest",
    "object_of_study": "require_approval",
    "pattern_of_interest": "require_approval",
    "coding_styles": "suggest",
    "gerundio_esperado": "suggest",
    "segmentation_config": "auto",
}

VALID_MUTATION_LEVELS = {"auto", "suggest", "require_approval", "locked"}

VALID_OBJECTS_OF_STUDY = {
    "concern",
    "emotion",
    "behavior",
    "discourse",
    "identity",
    "custom",
    "meaning",
}


# ── Helpers ───────────────────────────────────────────────────────────


async def _record_config_change(
    db: AsyncSession,
    project_id: UUID,
    *,
    field: str,
    old_value: str | None,
    new_value: str,
    triggered_by: str = "user",
    agent_run_id: str | None = None,
    mutation_level: str | None = None,
    rationale: str | None = None,
    confidence: float | None = None,
    context: dict | None = None,
) -> ProjectConfigHistory:
    """Registra un cambio de configuración en el historial inmutable."""
    entry = ProjectConfigHistory(
        proyecto_id=project_id,
        field=field,
        old_value=old_value,
        new_value=new_value,
        triggered_by=triggered_by,
        agent_run_id=agent_run_id,
        mutation_level=mutation_level,
        rationale=rationale,
        confidence=confidence,
        context=context,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    result = await db.execute(
        select(Proyecto).where(Proyecto.creador_id == current_user.id)
    )
    return result.scalars().all()


@router.post("", status_code=201, response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    data = body.model_dump()
    # Remove fields that are NOT Proyecto columns (stored in JSONB later)
    custom_label = data.pop("custom_label", None)
    processing_verb = data.pop("processing_verb", "").strip() or "resolve"
    processing_gerund = data.pop("processing_gerund", "").strip() or "resolving"
    oos = data.get("object_of_study", "concern")
    if oos and oos not in VALID_OBJECTS_OF_STUDY:
        raise HTTPException(
            400,
            f"object_of_study invalido: '{oos}'. "
            f"Valores permitidos: {', '.join(sorted(VALID_OBJECTS_OF_STUDY))}",
        )
    data["object_of_study"] = oos or "concern"

    # ── spaCy validation for custom object_of_study ──
    spacy_result: dict | None = None
    if oos == "custom" and custom_label and custom_label.strip():
        try:
            spacy_result = _validate_custom_label_with_spacy(custom_label)
            logger.info(
                "spaCy custom_label validation: label=%r suggestion=%s max_sim=%.4f",
                custom_label,
                spacy_result.get("suggestion"),
                spacy_result.get("max_similarity", 0),
            )
        except Exception as e:
            logger.warning("spaCy validation failed for custom_label: %s", e)
            spacy_result = {
                "suggestion": None,
                "similarities": {},
                "accepted": True,
                "max_similarity": 0.0,
            }

    proyecto = Proyecto(**data, creador_id=current_user.id)
    db.add(proyecto)
    await db.commit()
    await db.refresh(proyecto)

    # ── Store custom_label + spaCy result in population_assumption ──
    if oos == "custom" and custom_label and custom_label.strip():
        pop = proyecto.population_assumption or {}
        pop["custom_label"] = custom_label.strip()
        if spacy_result:
            pop["custom_label_spacy"] = spacy_result
        proyecto.population_assumption = pop
        await db.commit()
        await db.refresh(proyecto)

    # ── Store processing_verb in population_assumption ──
    pop = proyecto.population_assumption or {}
    pop["processing_verb"] = processing_verb
    pop["processing_gerund"] = processing_gerund
    # Default methodological framework
    pop.setdefault("methodological_framework", "classic_gt")
    proyecto.population_assumption = pop
    await db.commit()
    await db.refresh(proyecto)

    # ── Conjugate processing_verb to match population (always plural 3rd person) ──
    raw_pop_for_verb = body.supuesto_poblacional
    if raw_pop_for_verb and raw_pop_for_verb.strip():
        try:
            pvc = _conjugate_verb(processing_verb, raw_pop_for_verb)
            pop = proyecto.population_assumption or {}
            pop["processing_verb_conjugated"] = pvc
            proyecto.population_assumption = pop
            await db.commit()
            await db.refresh(proyecto)
            logger.info(
                "Verb conjugated: verb=%r conjugated=%r for project=%s",
                pv,
                pvc,
                proyecto.id,
            )
        except Exception as e:
            logger.warning("Verb conjugation failed for project=%s: %s", proyecto.id, e)

    # ── Generate RQ preview immediately and store it ──
    raw_pop = body.supuesto_poblacional
    if raw_pop and raw_pop.strip() and processing_verb:
        try:
            conj = _conjugate_verb_full(processing_verb, raw_pop)
            pop_phrase = _format_population_phrase(conj["article"], raw_pop)
            meta = _PATTERN_META.get(oos, _PATTERN_META["custom"])
            lang_meta = meta.get(conj["language"], meta.get("en", {}))
            pnoun = lang_meta.get("noun", "pattern")
            pplural = lang_meta.get("plural", "patterns")
            pgender = lang_meta.get("gender", "n")
            if oos == "custom" and custom_label and custom_label.strip():
                pnoun = custom_label.strip()
                pplural = pnoun + "s" if not pnoun.endswith("s") else pnoun
            # Resolve articles/pronouns
            lang = conj["language"]
            if lang == "es":
                if pgender == "f":
                    pat_art, pron_sg, pron_pl = "la", "la", "las"
                else:
                    pat_art, pron_sg, pron_pl = "el", "lo", "los"
            elif lang == "pt":
                if pgender == "f":
                    pat_art, pron_sg, pron_pl = "a", "a", "as"
                else:
                    pat_art, pron_sg, pron_pl = "o", "o", "os"
            elif lang == "de":
                if pgender == "f":
                    pat_art, pron_sg, pron_pl = "die", "sie", "sie"
                elif pgender == "n":
                    pat_art, pron_sg, pron_pl = "das", "es", "sie"
                else:
                    pat_art, pron_sg, pron_pl = "der", "ihn", "sie"
            else:
                pat_art, pron_sg, pron_pl = "the", "it", "them"
            questions = _build_questions(
                lang=lang,
                pop_phrase=pop_phrase,
                population=raw_pop,
                pat_art=pat_art,
                pattern_noun=pnoun,
                pattern_plural=pplural,
                pronoun_sg=pron_sg,
                pronoun_pl=pron_pl,
                conjugated=conj["verb"],
            )
            pop = proyecto.population_assumption or {}
            pop["research_question"] = {
                "research_question": questions["research_question"],
                "operational_question": questions["oq_discovery"],
                "oq_discovery": questions["oq_discovery"],
                "oq_selective": questions["oq_selective"],
                "oq_theoretical": questions["oq_theoretical"],
                "generated_at": datetime.utcnow().isoformat(),
                "auto_generated": True,
            }
            proyecto.population_assumption = pop
            await db.commit()
            await db.refresh(proyecto)
            logger.info("RQ stored at creation for project=%s", proyecto.id)
        except Exception as e:
            logger.warning("RQ generation at creation failed: %s", e)

    # ── Detect singular population (warn only, don't block) ──
    raw_pop = body.supuesto_poblacional
    singular_warning = _detect_singular_population(raw_pop) if raw_pop else None
    if singular_warning:
        logger.info(
            "Singular population detected for project=%s: %s",
            proyecto.id,
            singular_warning,
        )
        pop = proyecto.population_assumption or {}
        pop["population_warning"] = singular_warning
        proyecto.population_assumption = pop
        await db.commit()
        await db.refresh(proyecto)

    # ── F1.2: f0_population_generalizer (FLASH, single-shot) ──
    if raw_pop and raw_pop.strip():
        try:
            from app.core.llm_config import get_model_for_prompt
            from app.core.together_client import TogetherLLM
            from app.prompts import PROMPT_REGISTRY

            template = PROMPT_REGISTRY["f0_population_generalizer"]
            messages = template.build_messages(raw_population_description=raw_pop)
            # Forzar JSON: Gemma Flash no respeta response_format, necesita instruccion explicita
            messages.append(
                {
                    "role": "user",
                    "content": "Responde EXCLUSIVAMENTE en formato JSON, sin markdown, sin explicacion adicional.",
                }
            )
            model = get_model_for_prompt("f0_population_generalizer")

            llm = TogetherLLM()
            response = await asyncio.to_thread(
                llm.chat,
                model=model,
                messages=messages,
            )

            # Parse JSON from text (gemma flash no soporta response_format JSON schema)
            raw_content = response.get("content", "{}")
            content = {}
            try:
                content = json.loads(raw_content)
            except json.JSONDecodeError:
                import re

                matches = list(
                    re.finditer(
                        r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_content, re.DOTALL
                    )
                )
                for m in matches:
                    try:
                        content = json.loads(m.group(0))
                        break
                    except json.JSONDecodeError:
                        continue

            # Mapear keys en espanol → ingles (Gemma a veces responde en espanol)
            KEY_MAP = {
                "population_generalizada": "generalized_population",
                "poblacion_generalizada": "generalized_population",
                "marco_espacial": "spatial_frame",
                "marco_temporal": "temporal_frame",
                "confianza": "confidence",
                "justificacion": "rationale",
            }
            content = {KEY_MAP.get(k, k): v for k, v in content.items()}

            # Merge with any existing population_assumption
            current = proyecto.population_assumption or {}
            current["population_description"] = raw_pop
            current["generalized_population"] = content.get(
                "generalized_population", ""
            )
            current["spatial_frame"] = content.get("spatial_frame", "sparse")
            current["temporal_frame"] = content.get(
                "temporal_frame", "present_continuous"
            )
            current["generalizer_confidence"] = content.get("confidence", 0.5)
            current["generalizer_rationale"] = content.get("rationale", "")
            proyecto.population_assumption = current

            await db.commit()
            await db.refresh(proyecto)
            logger.info(
                "f0_population_generalizer: project=%s spatial=%s temporal=%s",
                proyecto.id,
                current.get("spatial_frame"),
                current.get("temporal_frame"),
            )
        except Exception as e:
            logger.warning(
                "f0_population_generalizer failed for project=%s: %s",
                proyecto.id,
                e,
            )
            # Non-blocking: project is created even if generalizer fails

    return proyecto


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    # Conteos para el dashboard
    doc_count = await db.scalar(
        select(func.count(Documento.id)).where(Documento.proyecto_id == project_id)
    )
    cat_count = await db.scalar(
        select(func.count(Categoria.id)).where(Categoria.proyecto_id == project_id)
    )

    # Devolvemos el proyecto + metadata extra
    return {
        **proyecto.__dict__,
        "num_documentos": doc_count,
        "num_categorias": cat_count,
    }


@router.put("/{project_id}/config/population-assumption")
async def update_population_assumption(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """C04: Configurar population_assumption en Fase 0."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    allowed_keys = {
        "object_of_study",
        "temporal_frame",
        "spatial_frame",
        "population_description",
        "gerundio_esperado",
        "custom_label",
    }
    update_data = {k: v for k, v in body.items() if k in allowed_keys}

    if not update_data:
        raise HTTPException(
            400, "No se recibieron campos válidos para population_assumption"
        )

    # ── spaCy validation for custom_label ──
    if "custom_label" in update_data:
        cl = update_data["custom_label"]
        resolved_oos = update_data.get(
            "object_of_study",
            proyecto.population_assumption.get(
                "object_of_study", proyecto.object_of_study
            )
            if proyecto.population_assumption
            else proyecto.object_of_study,
        )
        if resolved_oos == "custom" and cl and str(cl).strip():
            try:
                spacy_result = _validate_custom_label_with_spacy(str(cl))
                logger.info(
                    "spaCy custom_label validation (pop-assumption): label=%r suggestion=%s",
                    cl,
                    spacy_result.get("suggestion"),
                )
                update_data["custom_label_spacy"] = spacy_result
            except Exception as e:
                logger.warning(
                    "spaCy validation failed for custom_label (pop-assumption): %s", e
                )
        elif resolved_oos != "custom":
            # Clear spacy data if not custom
            update_data.pop("custom_label_spacy", None)
            current_extra = proyecto.population_assumption or {}
            current_extra.pop("custom_label_spacy", None)

    # Record history for each changed key
    current = proyecto.population_assumption or {}
    for key, value in update_data.items():
        old_val = current.get(key)
        await _record_config_change(
            db,
            project_id,
            field=f"population_assumption.{key}",
            old_value=json.dumps(old_val) if old_val is not None else None,
            new_value=json.dumps(value),
            triggered_by="user",
        )

    current.update(update_data)
    proyecto.population_assumption = current

    # ── F0.3.5: Sync object_of_study to dedicated column ──
    if "object_of_study" in update_data:
        oos = update_data["object_of_study"]
        if oos not in VALID_OBJECTS_OF_STUDY:
            raise HTTPException(
                400,
                f"object_of_study invalido: '{oos}'. "
                f"Valores permitidos: {', '.join(sorted(VALID_OBJECTS_OF_STUDY))}",
            )
        if oos != proyecto.object_of_study:
            proyecto.object_of_study = oos
            # Reset pipeline state if pattern type changes
            if proyecto.estado not in ("collecting", "coding"):
                proyecto.estado = "coding"
                logger.info(
                    "Project %s: object_of_study changed via pop-assumption, resetting to 'coding'",
                    proyecto.id,
                )

    await db.commit()
    await db.refresh(proyecto)
    return {
        "status": "updated",
        "population_assumption": proyecto.population_assumption,
        "supuesto_poblacional": proyecto.supuesto_poblacional,
    }


@router.post("/{project_id}/config/population-assumption/generalize")
async def generalize_population(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Re-run the f0_population_generalizer (FLASH) for an existing project.

    Called when the user wants to re-generate or generate for the first time
    the generalized population from the raw supuesto_poblacional.
    """
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    raw_pop = proyecto.supuesto_poblacional
    if not raw_pop or not raw_pop.strip():
        raise HTTPException(400, "No hay supuesto_poblacional para generalizar")

    try:
        from app.core.llm_config import get_model_for_prompt
        from app.core.together_client import TogetherLLM
        from app.prompts import PROMPT_REGISTRY

        template = PROMPT_REGISTRY["f0_population_generalizer"]
        messages = template.build_messages(raw_population_description=raw_pop)
        messages.append(
            {
                "role": "user",
                "content": "Responde EXCLUSIVAMENTE en formato JSON, sin markdown, sin explicacion adicional.",
            }
        )
        model = get_model_for_prompt("f0_population_generalizer")

        llm = TogetherLLM()
        response = await asyncio.to_thread(llm.chat, model=model, messages=messages)

        raw_content = response.get("content", "{}")
        content = {}
        try:
            content = json.loads(raw_content)
        except json.JSONDecodeError:
            import re

            matches = list(
                re.finditer(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw_content, re.DOTALL)
            )
            for m in matches:
                try:
                    content = json.loads(m.group(0))
                    break
                except json.JSONDecodeError:
                    continue

        KEY_MAP = {
            "population_generalizada": "generalized_population",
            "poblacion_generalizada": "generalized_population",
            "marco_espacial": "spatial_frame",
            "marco_temporal": "temporal_frame",
            "confianza": "confidence",
            "justificacion": "rationale",
        }
        content = {KEY_MAP.get(k, k): v for k, v in content.items()}

        current = proyecto.population_assumption or {}
        current["population_description"] = raw_pop
        current["generalized_population"] = content.get("generalized_population", "")
        current["spatial_frame"] = content.get("spatial_frame", "sparse")
        current["temporal_frame"] = content.get("temporal_frame", "present_continuous")
        current["generalizer_confidence"] = content.get("confidence", 0.5)
        current["generalizer_rationale"] = content.get("rationale", "")
        proyecto.population_assumption = current

        await db.commit()
        await db.refresh(proyecto)

        return {
            "status": "generalized",
            "population_assumption": proyecto.population_assumption,
            "supuesto_poblacional": proyecto.supuesto_poblacional,
        }
    except Exception as e:
        logger.warning(
            "generalize_population failed for project=%s: %s", proyecto.id, e
        )
        raise HTTPException(500, f"Generalizer failed: {str(e)}")


@router.post("/research-question/preview")
async def preview_research_question_standalone(
    body: dict,
):
    """Standalone RQ preview — no project/auth required. Used by creation form."""
    population = (body.get("population") or "").strip()
    oos = (body.get("object_of_study") or "concern").strip()
    verb = (body.get("processing_verb") or "resolve").strip()
    custom_label = (body.get("custom_label") or "").strip()

    if not population:
        raise HTTPException(400, "population is required")
    if oos not in VALID_OBJECTS_OF_STUDY:
        raise HTTPException(400, f"Invalid object_of_study: {oos}")

    conj = _conjugate_verb_full(verb, population)
    conjugated = conj["verb"]
    pop_number = conj["number"]
    pop_article = conj["article"]
    lang = conj["language"]
    pop_phrase = _format_population_phrase(pop_article, population)

    meta = _PATTERN_META.get(oos, _PATTERN_META["custom"])
    lang_meta = meta.get(lang, meta.get("en", {}))
    pattern_noun = lang_meta.get("noun", "pattern")
    pattern_plural = lang_meta.get("plural", "patterns")
    pattern_gender = lang_meta.get("gender", "n")

    if oos == "custom" and custom_label:
        pattern_noun = custom_label
        pattern_plural = (
            custom_label + "s" if not custom_label.endswith("s") else custom_label
        )

    # Pattern article/pronoun — resolve singular AND plural forms
    if lang == "es":
        if pattern_gender == "f":
            pat_art, pronoun_sg, pronoun_pl = "la", "la", "las"
        else:
            pat_art, pronoun_sg, pronoun_pl = "el", "lo", "los"
    elif lang == "pt":
        if pattern_gender == "f":
            pat_art, pronoun_sg, pronoun_pl = "a", "a", "as"
        else:
            pat_art, pronoun_sg, pronoun_pl = "o", "o", "os"
    elif lang == "de":
        if pattern_gender == "f":
            pat_art, pronoun_sg, pronoun_pl = "die", "sie", "sie"
        elif pattern_gender == "n":
            pat_art, pronoun_sg, pronoun_pl = "das", "es", "sie"
        else:
            pat_art, pronoun_sg, pronoun_pl = "der", "ihn", "sie"
    else:
        pat_art, pronoun_sg, pronoun_pl = "the", "it", "them"

    # ── Build all questions from declarative templates ──
    questions = _build_questions(
        lang=lang,
        pop_phrase=pop_phrase,
        population=population,
        pat_art=pat_art,
        pattern_noun=pattern_noun,
        pattern_plural=pattern_plural,
        pronoun_sg=pronoun_sg,
        pronoun_pl=pronoun_pl,
        conjugated=conjugated,
    )

    return {
        "research_question": questions["research_question"],
        "operational_question": questions["oq_discovery"],
        "oq_discovery": questions["oq_discovery"],
        "oq_selective": questions["oq_selective"],
        "oq_theoretical": questions["oq_theoretical"],
        "population_number": pop_number,
        "conjugated_verb": conjugated,
        "language": lang,
    }


@router.post("/{project_id}/research-question/preview")
async def preview_research_question(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Returns a live preview of both the research question and operational question.

    Uses spaCy for proper verb conjugation, article agreement, and pronoun selection.
    Body: {population, object_of_study, processing_verb, custom_label?}
    """
    population = (body.get("population") or "").strip()
    oos = (body.get("object_of_study") or "concern").strip()
    verb = (body.get("processing_verb") or "resolve").strip()
    custom_label = (body.get("custom_label") or "").strip()

    if not population:
        raise HTTPException(400, "population is required")
    if oos not in VALID_OBJECTS_OF_STUDY:
        raise HTTPException(400, f"Invalid object_of_study: {oos}")

    # ── Conjugate verb and detect population metadata ──
    conj = _conjugate_verb_full(verb, population)
    conjugated = conj["verb"]
    pop_number = conj["number"]
    pop_article = conj["article"]
    lang = conj["language"]
    pop_phrase = _format_population_phrase(pop_article, population)

    # ── Get pattern noun metadata ──
    meta = _PATTERN_META.get(oos, _PATTERN_META["custom"])
    lang_meta = meta.get(lang, meta.get("en", {}))
    pattern_noun = lang_meta.get("noun", "pattern")
    pattern_plural = lang_meta.get("plural", "patterns")
    pattern_gender = lang_meta.get("gender", "n")

    # Use custom_label if provided for custom type
    if oos == "custom" and custom_label:
        pattern_noun = custom_label
        pattern_plural = (
            custom_label + "s" if not custom_label.endswith("s") else custom_label
        )

    # ── Build article and pronoun for pattern ──
    # Pattern article/pronoun
    if lang == "es":
        if pattern_gender == "f":
            pattern_article, pronoun_sg, pronoun_pl = "la", "la", "las"
        else:
            pattern_article, pronoun_sg, pronoun_pl = "el", "lo", "los"
    elif lang == "pt":
        if pattern_gender == "f":
            pattern_article, pronoun_sg, pronoun_pl = "a", "a", "as"
        else:
            pattern_article, pronoun_sg, pronoun_pl = "o", "o", "os"
    elif lang == "de":
        if pattern_gender == "f":
            pattern_article, pronoun_sg, pronoun_pl = "die", "sie", "sie"
        elif pattern_gender == "n":
            pattern_article, pronoun_sg, pronoun_pl = "das", "es", "sie"
        else:
            pattern_article, pronoun_sg, pronoun_pl = "der", "ihn", "sie"
    else:
        pattern_article, pronoun_sg, pronoun_pl = "the", "it", "them"

    # ── Build all questions from declarative templates ──
    questions = _build_questions(
        lang=lang,
        pop_phrase=pop_phrase,
        population=population,
        pat_art=pattern_article,
        pattern_noun=pattern_noun,
        pattern_plural=pattern_plural,
        pronoun_sg=pronoun_sg,
        pronoun_pl=pronoun_pl,
        conjugated=conjugated,
    )

    return {
        "project_id": str(project_id),
        "research_question": questions["research_question"],
        "operational_question": questions["oq_discovery"],
        "oq_discovery": questions["oq_discovery"],
        "oq_selective": questions["oq_selective"],
        "oq_theoretical": questions["oq_theoretical"],
        "population_number": pop_number,
        "population_gender": conj.get("gender"),
        "population_article": pop_article,
        "pattern_gender": pattern_gender,
        "pattern_article": pattern_article,
        "pronoun": pronoun,
        "conjugated_verb": conjugated,
        "language": lang,
    }


@router.put("/{project_id}/research-question")
async def update_research_question(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Allows the researcher to manually edit the stored research question."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    pa = dict(proyecto.population_assumption or {})
    rq_data = dict(pa.get("research_question", {}))

    if "research_question" in body:
        rq_data["research_question"] = body["research_question"]
    if "operational_question" in body:
        rq_data["operational_question"] = body["operational_question"]

    pa["research_question"] = rq_data
    proyecto.population_assumption = pa
    await db.commit()
    await db.refresh(proyecto)

    return {
        "project_id": str(project_id),
        **rq_data,
    }


# ═══════════════════════════════════════════════════════════════════════
# Config endpoints — lectura y política de mutaciones
# ═══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/config")
async def get_project_config(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve toda la configuración actual del proyecto."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    policy = proyecto.config_mutation_policy or DEFAULT_MUTATION_POLICY

    return {
        "project_id": str(proyecto.id),
        "nombre": proyecto.nombre,
        "estado": proyecto.estado,
        "ruta_de_codificacion": proyecto.ruta_de_codificacion,
        # ── Configuración epistemológica ──
        "supuesto_poblacional": proyecto.supuesto_poblacional,
        "object_of_study": proyecto.object_of_study,
        "population_assumption": proyecto.population_assumption or {},
        # ── Estilos de codificación ──
        "coding_style_instruction": proyecto.coding_style_instruction,
        # ── Segmentación ──
        "config_segmentacion": proyecto.config_segmentacion or {},
        # ── Política de mutaciones ──
        "mutation_policy": policy,
        # ── Sugerencias pendientes (cambios propuestos por agentes, nivel "suggest") ──
        "pending_suggestions": await _get_pending_suggestions(db, project_id),
    }


@router.get("/{project_id}/config/history")
async def get_project_config_history(
    project_id: UUID,
    field: str | None = Query(None, description="Filtrar por campo específico"),
    limit: int = Query(50, ge=1, le=200, description="Máximo de entradas"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Devuelve el historial de cambios de configuración del proyecto (tipo git log)."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    query = (
        select(ProjectConfigHistory)
        .where(ProjectConfigHistory.proyecto_id == project_id)
        .order_by(ProjectConfigHistory.creado_en.desc())
    )
    if field:
        query = query.where(ProjectConfigHistory.field == field)
    query = query.limit(limit)

    result = await db.execute(query)
    entries = result.scalars().all()

    return {
        "project_id": str(project_id),
        "total": len(entries),
        "entries": [
            {
                "id": str(e.id),
                "field": e.field,
                "old_value": e.old_value,
                "new_value": e.new_value,
                "triggered_by": e.triggered_by,
                "agent_run_id": e.agent_run_id,
                "mutation_level": e.mutation_level,
                "rationale": e.rationale,
                "confidence": e.confidence,
                "context": e.context,
                "timestamp": e.creado_en.isoformat() if e.creado_en else None,
            }
            for e in entries
        ],
    }


# ═══════════════════════════════════════════════════════════════════════
# F0.6: Nemotrón — Research Question endpoints
# ═══════════════════════════════════════════════════════════════════════


@router.get("/{project_id}/research-question")
async def get_research_question(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Returns the stored research question for a project.

    The research question is stored in population_assumption.research_question
    after the Nemotrón agent generates it.
    """
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    pa = proyecto.population_assumption or {}
    rq_data = pa.get("research_question")

    if not rq_data:
        return {
            "project_id": str(project_id),
            "research_question": None,
            "operational_question": None,
            "rationale": None,
            "key_dimensions": None,
            "generated_at": None,
            "message": "No research question generated yet. Use POST .../generate to create one.",
        }

    return {
        "project_id": str(project_id),
        **rq_data,
    }


# ═══════════════════════════════════════════════════════════════════════
# Config endpoints — lectura y política de mutaciones (continuación)
# ═══════════════════════════════════════════════════════════════════════


@router.put("/{project_id}/config/mutation-policy")
async def update_mutation_policy(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Actualiza la política de mutaciones automáticas del proyecto.

    Body: {"population_description": "auto", "object_of_study": "require_approval", ...}
    Solo se aceptan claves válidas con niveles válidos.
    """
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    current_policy = proyecto.config_mutation_policy or dict(DEFAULT_MUTATION_POLICY)

    updated = False
    for key, level in body.items():
        if key not in DEFAULT_MUTATION_POLICY:
            continue  # Ignorar claves desconocidas
        if level not in VALID_MUTATION_LEVELS:
            continue  # Ignorar niveles inválidos
        if current_policy.get(key) != level:
            await _record_config_change(
                db,
                project_id,
                field=f"mutation_policy.{key}",
                old_value=current_policy.get(key, "suggest"),
                new_value=level,
                triggered_by="user",
            )
            current_policy[key] = level
            updated = True

    if not updated:
        return {
            "status": "no_changes",
            "message": "No se detectaron cambios en la política",
            "mutation_policy": current_policy,
        }

    proyecto.config_mutation_policy = current_policy
    await db.commit()
    await db.refresh(proyecto)

    return {
        "status": "updated",
        "message": f"Política de mutaciones actualizada",
        "mutation_policy": proyecto.config_mutation_policy,
    }


async def _get_pending_suggestions(db: AsyncSession, project_id: UUID) -> list[dict]:
    """Devuelve sugerencias pendientes de agentes (nivel 'suggest')
    que el investigador aún no ha aceptado/rechazado.

    Por ahora recuperamos las entradas de historial con mutation_level='suggest'
    más recientes para cada campo.
    """
    from sqlalchemy import text as sa_text

    # Obtener la sugerencia más reciente por campo con nivel 'suggest'
    rows = await db.execute(
        sa_text(
            """
            SELECT DISTINCT ON (field)
                id, field, old_value, new_value, triggered_by,
                rationale, confidence, context, creado_en
            FROM project_config_history
            WHERE proyecto_id = :pid
              AND mutation_level = 'suggest'
            ORDER BY field, creado_en DESC
            """
        ),
        {"pid": project_id},
    )

    return [
        {
            "id": str(row[0]),
            "field": row[1],
            "old_value": row[2],
            "new_value": row[3],
            "triggered_by": row[4],
            "rationale": row[5],
            "confidence": row[6],
            "context": row[7],
            "timestamp": row[8].isoformat() if row[8] else None,
        }
        for row in rows
    ]


@router.put("/{project_id}")
async def update_project(
    project_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Editar nombre, descripcion poblacional, y config del proyecto."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    updatable = {"nombre", "supuesto_poblacional", "object_of_study"}
    pattern_changed = False
    new_oos = body.get("object_of_study")
    for key, value in body.items():
        if key in updatable and value is not None:
            if key == "object_of_study" and value not in VALID_OBJECTS_OF_STUDY:
                raise HTTPException(
                    400,
                    detail=f"object_of_study invalido: '{value}'. "
                    f"Valores permitidos: {', '.join(sorted(VALID_OBJECTS_OF_STUDY))}",
                )
            if key == "object_of_study" and value != proyecto.object_of_study:
                pattern_changed = True
            setattr(proyecto, key, value)

    # ── Handle custom_label: spaCy validation + JSONB sync ──
    custom_label = body.get("custom_label")
    if custom_label is not None:
        resolved_oos = new_oos if new_oos is not None else proyecto.object_of_study
        if resolved_oos == "custom" and custom_label and str(custom_label).strip():
            # Run spaCy validation
            try:
                spacy_result = _validate_custom_label_with_spacy(str(custom_label))
                logger.info(
                    "spaCy custom_label validation (update): label=%r suggestion=%s max_sim=%.4f",
                    custom_label,
                    spacy_result.get("suggestion"),
                    spacy_result.get("max_similarity", 0),
                )
            except Exception as e:
                logger.warning(
                    "spaCy validation failed for custom_label (update): %s", e
                )
                spacy_result = {
                    "suggestion": None,
                    "similarities": {},
                    "accepted": True,
                    "max_similarity": 0.0,
                }
            # Store in population_assumption
            pop = proyecto.population_assumption or {}
            pop["custom_label"] = str(custom_label).strip()
            pop["custom_label_spacy"] = spacy_result
            proyecto.population_assumption = pop
        elif resolved_oos != "custom":
            # Clear custom_label if object_of_study is no longer "custom"
            pop = proyecto.population_assumption or {}
            pop.pop("custom_label", None)
            pop.pop("custom_label_spacy", None)
            proyecto.population_assumption = pop

    # ── Handle processing_verb ──
    processing_verb = body.get("processing_verb")
    if processing_verb is not None:
        pop = proyecto.population_assumption or {}
        pop["processing_verb"] = str(processing_verb).strip() or "resolve"
        proyecto.population_assumption = pop
    processing_gerund = body.get("processing_gerund")
    if processing_gerund is not None:
        pop = proyecto.population_assumption or {}
        pop["processing_gerund"] = str(processing_gerund).strip() or "resolving"
        proyecto.population_assumption = pop
    # Ensure methodological_framework default
    pop = proyecto.population_assumption or {}
    pop.setdefault("methodological_framework", "classic_gt")
    proyecto.population_assumption = pop

    # ── F0.3.5: Si cambia el tipo de patron, reiniciar pipeline ──
    if pattern_changed and proyecto.estado not in ("collecting", "coding"):
        proyecto.estado = "coding"
        logger.info(
            "Project %s: object_of_study changed, resetting state to 'coding'",
            proyecto.id,
        )

    await db.commit()
    await db.refresh(proyecto)
    return {
        "status": "updated",
        "id": str(proyecto.id),
        "nombre": proyecto.nombre,
        "estado": proyecto.estado,
        "object_of_study": proyecto.object_of_study,
        "supuesto_poblacional": proyecto.supuesto_poblacional,
        "population_assumption": proyecto.population_assumption,
    }


@router.delete("/{project_id}", status_code=200)
async def delete_project(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina un proyecto y todos sus datos asociados (cascada)."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")
    if str(proyecto.creador_id) != str(current_user.id):
        raise HTTPException(403, "No autorizado")

    nombre = proyecto.nombre
    await db.delete(proyecto)
    await db.commit()
    return {"status": "deleted", "nombre": nombre, "id": str(project_id)}


@router.delete("/{project_id}/documents", status_code=200)
async def delete_all_documents(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Elimina todos los documentos de un proyecto y resetea su estado."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    from sqlalchemy import text as sa_text

    # Contar docs antes de borrar
    count = await db.scalar(
        select(func.count(Documento.id)).where(Documento.proyecto_id == project_id)
    )

    # Borrar en orden: codigos → segmentos → documentos
    await db.execute(
        sa_text(
            "DELETE FROM codigos_segmento WHERE segmento_id IN "
            "(SELECT id FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid))"
        ),
        {"pid": project_id},
    )
    await db.execute(
        sa_text(
            "DELETE FROM segmentos WHERE documento_id IN "
            "(SELECT id FROM documentos WHERE proyecto_id = :pid)"
        ),
        {"pid": project_id},
    )
    await db.execute(
        sa_text("DELETE FROM documentos WHERE proyecto_id = :pid"),
        {"pid": project_id},
    )

    # Resetear estado del proyecto
    proyecto.estado = "collecting"
    await db.commit()

    return {"status": "deleted", "count": count, "project_id": str(project_id)}


@router.get("/{project_id}/stage-progress")
async def get_stage_progress(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Returns count of documents processed by each agent for this project."""
    proyecto = await db.get(Proyecto, project_id)
    if not proyecto:
        raise HTTPException(404, "Proyecto no encontrado")

    rows = await db.execute(
        text(
            "SELECT dsp.agent_id, COUNT(*) as count "
            "FROM document_stage_progress dsp "
            "JOIN documentos d ON d.id = dsp.documento_id "
            "WHERE d.proyecto_id = :pid "
            "GROUP BY dsp.agent_id"
        ),
        {"pid": project_id},
    )
    result = rows.fetchall()
    return {row[0]: row[1] for row in result}
