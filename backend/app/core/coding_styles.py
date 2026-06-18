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
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class CodingStyleI18n:
    """Per-language instructional tokens. Injected into prompts and JSON schemas."""

    label_name: str  # "gerundio" / "gerund" / "Gerundium" / "gerúndio"
    label_format: str  # "-ando/-iendo" / "-ing" / "-end" / "-ndo"
    label_desc: str  # Full description for schema fields
    label_examples: str  # Comma-separated examples in this language
    label_anti: str  # What NOT to do
    instruction: str  # The full code generation instruction in this language
    rename_instruction: str  # The rename instruction in this language


@dataclass
class CodingStyle:
    key: str
    name: str
    instruction: str
    rename_instruction: str
    examples: list[str] = field(default_factory=list)
    saldana_category: str = ""  # Categoría en el manual de Saldaña
    i18n: dict[str, CodingStyleI18n] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
# Definición de estilos
# ═══════════════════════════════════════════════════════════════════════


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
        i18n={
            "es": CodingStyleI18n(
                label_name="gerundio",
                label_format="-ando/-iendo",
                label_desc="Nombre en gerundio de 2-6 palabras. Captura el patrón de comportamiento recurrente.",
                label_examples="Negociando límites, Evadiendo control algorítmico, Balanceando riesgo y visibilidad, Construyendo confianza interdisciplinaria",
                label_anti="Lenguaje llano, sin gerundios",
                instruction=(
                    "Nombra cada código con un GERUNDIO (verbo terminado en -ando/-iendo). "
                    "El gerundio debe capturar un PATRÓN DE COMPORTAMIENTO, no un tema estático."
                ),
                rename_instruction=(
                    "Sugiere renombres como GERUNDIOS. El nuevo nombre debe reflejar "
                    "la definición expandida como un patrón de comportamiento activo."
                ),
            ),
            "en": CodingStyleI18n(
                label_name="gerund",
                label_format="-ing",
                label_desc="Gerund name of 2-6 words. Captures the recurring behavioral process.",
                label_examples="Negotiating boundaries, Evading algorithmic control, Balancing risk and visibility, Building cross-disciplinary trust",
                label_anti="Plain language, no gerunds",
                instruction=(
                    "Name each code with a GERUND (verb ending in -ing). "
                    "The gerund should capture a BEHAVIORAL PATTERN, not a static topic."
                ),
                rename_instruction=(
                    "Suggest renames as GERUNDS. The new name should reflect "
                    "the expanded definition as an active behavioral pattern."
                ),
            ),
            "de": CodingStyleI18n(
                label_name="Gerundium",
                label_format="-end",
                label_desc="Gerundium-Name aus 2–6 Wörtern. Erfasst den wiederkehrenden Verhaltensprozess.",
                label_examples="Grenzen verhandelnd, Algorithmische Kontrolle umgehend, Risiko und Sichtbarkeit ausbalancierend, Interdisziplinäres Vertrauen aufbauend",
                label_anti="Schlichte Sprache, keine Gerundien",
                instruction=(
                    "Benenne jeden Code mit einem GERUNDIUM (Verb mit der Endung -end). "
                    "Das Gerundium muss ein VERHALTENSMUSTER erfassen, kein statisches Thema."
                ),
                rename_instruction=(
                    "Schlage Umbenennungen als GERUNDIEN vor. Der neue Name soll "
                    "die erweiterte Definition als aktives Verhaltensmuster widerspiegeln."
                ),
            ),
            "pt": CodingStyleI18n(
                label_name="gerúndio",
                label_format="-ndo",
                label_desc="Nome em gerúndio de 2–6 palavras. Captura o padrão de comportamento recorrente.",
                label_examples="Negociando limites, Evitando o controle algorítmico, Balanceando risco e visibilidade, Construindo confiança interdisciplinar",
                label_anti="Linguagem plana, sem gerúndios",
                instruction=(
                    "Nomeie cada código com um GERÚNDIO (verbo terminado em -ndo). "
                    "O gerúndio deve capturar um PADRÃO DE COMPORTAMENTO, não um tema estático."
                ),
                rename_instruction=(
                    "Sugira renomeações como GERÚNDIOS. O novo nome deve refletir "
                    "a definição expandida como um padrão de comportamento ativo."
                ),
            ),
        },
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
        i18n={
            "es": CodingStyleI18n(
                label_name="sustantivo nominalizado",
                label_format="-ción, -miento, -ancia, -ura",
                label_desc="Sustantivo abstracto derivado de un verbo. Captura el proceso como concepto.",
                label_examples="Negociación de límites, Evitación del control algorítmico, Construcción de confianza, Resistencia a la automatización",
                label_anti="Sin gerundios ni verbos simples",
                instruction=(
                    "Nombra cada código con un SUSTANTIVO derivado de un verbo "
                    "(terminado en -ción, -miento, -ancia, -ura). "
                    "El nombre debe capturar el PROCESO como concepto abstracto."
                ),
                rename_instruction=(
                    "Sugiere renombres como SUSTANTIVOS derivados de verbos. "
                    "Prefiere -ción, -miento, -ancia."
                ),
            ),
            "en": CodingStyleI18n(
                label_name="nominalized verb",
                label_format="-tion, -ment, -ance",
                label_desc="Abstract noun derived from a verb, capturing the process as a concept.",
                label_examples="Negotiation of boundaries, Evasion of algorithmic control, Construction of trust, Resistance to automation",
                label_anti="No gerunds or bare verbs",
                instruction=(
                    "Name each code with a NOUN derived from a verb "
                    "(ending in -tion, -ment, -ance, -al). "
                    "The name should capture the PROCESS as an abstract concept."
                ),
                rename_instruction=(
                    "Suggest renames as NOUNS derived from verbs. "
                    "Prefer -tion, -ment, -ance."
                ),
            ),
            "de": CodingStyleI18n(
                label_name="nominalisiertes Verb",
                label_format="-ung, -tion, -ment",
                label_desc="Abstraktes Substantiv, abgeleitet von einem Verb. Erfasst den Prozess als Konzept.",
                label_examples="Aushandlung von Grenzen, Umgehung algorithmischer Kontrolle, Aufbau von Vertrauen, Widerstand gegen Automatisierung",
                label_anti="Keine Gerundien oder bloße Verben",
                instruction=(
                    "Benenne jeden Code mit einem SUBSTANTIV, das von einem Verb abgeleitet ist "
                    "(Endung -ung, -tion, -ment). "
                    "Der Name soll den PROZESS als abstraktes Konzept erfassen."
                ),
                rename_instruction=(
                    "Schlage Umbenennungen als VERBALABSTRAKTA vor. "
                    "Bevorzuge -ung, -tion, -ment."
                ),
            ),
            "pt": CodingStyleI18n(
                label_name="substantivo nominalizado",
                label_format="-ção, -mento, -ância, -ura",
                label_desc="Substantivo abstrato derivado de um verbo. Captura o processo como conceito.",
                label_examples="Negociação de limites, Evitação do controle algorítmico, Construção de confiança, Resistência à automação",
                label_anti="Sem gerúndios ou verbos simples",
                instruction=(
                    "Nomeie cada código com um SUBSTANTIVO derivado de um verbo "
                    "(terminado em -ção, -mento, -ância, -ura). "
                    "O nome deve capturar o PROCESSO como conceito abstrato."
                ),
                rename_instruction=(
                    "Sugira renomeações como SUBSTANTIVOS derivados de verbos. "
                    "Prefira -ção, -mento, -ância."
                ),
            ),
        },
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
        i18n={
            "es": CodingStyleI18n(
                label_name="paráfrasis descriptiva",
                label_format="frase de 3-8 palabras",
                label_desc="Frase corta descriptiva que captura la idea central en lenguaje natural.",
                label_examples="El algoritmo decide sin consultar al repartidor, Aceptar cualquier pedido por miedo a penalización, Los veteranos enseñan estrategias a los nuevos",
                label_anti="Sin gerundios forzados ni jerga",
                instruction=(
                    "Nombra cada código con una FRASE CORTA que describa el contenido "
                    "del segmento en tus propias palabras (no uses gerundios forzados). "
                    "La frase debe capturar la IDEA CENTRAL en 3-8 palabras."
                ),
                rename_instruction=(
                    "Sugiere renombres como FRASES CORTAS descriptivas. "
                    "Captura la idea central expandida en lenguaje natural."
                ),
            ),
            "en": CodingStyleI18n(
                label_name="descriptive phrase",
                label_format="3-8 word phrase",
                label_desc="Short descriptive phrase capturing the central idea in natural language.",
                label_examples="The algorithm decides without consulting the driver, Accepting any order fearing penalties, Veterans teach strategies to newcomers",
                label_anti="No forced gerunds or jargon",
                instruction=(
                    "Name each code with a SHORT PHRASE that describes the segment's "
                    "content in your own words (no forced gerunds). "
                    "The phrase should capture the CENTRAL IDEA in 3-8 words."
                ),
                rename_instruction=(
                    "Suggest renames as short DESCRIPTIVE PHRASES. "
                    "Capture the expanded central idea in natural language."
                ),
            ),
            "de": CodingStyleI18n(
                label_name="beschreibende Phrase",
                label_format="3–8-Wort-Phrase",
                label_desc="Kurze beschreibende Phrase, die die Kernidee in natürlicher Sprache erfasst.",
                label_examples="Der Algorithmus entscheidet ohne Rücksprache mit dem Fahrer, Angst vor Sanktionen führt zur Annahme aller Aufträge, Erfahrene Fahrer geben Strategien an Neue weiter",
                label_anti="Keine erzwungenen Gerundien oder Fachjargon",
                instruction=(
                    "Benenne jeden Code mit einer KURZEN PHRASE, die den Inhalt des Segments "
                    "in eigenen Worten beschreibt (keine erzwungenen Gerundien). "
                    "Die Phrase soll die KERNIDEE in 3–8 Wörtern erfassen."
                ),
                rename_instruction=(
                    "Schlage Umbenennungen als kurze BESCHREIBENDE PHRASEN vor. "
                    "Erfasse die erweiterte Kernidee in natürlicher Sprache."
                ),
            ),
            "pt": CodingStyleI18n(
                label_name="frase descritiva",
                label_format="frase de 3-8 palavras",
                label_desc="Frase curta descritiva que captura a ideia central em linguagem natural.",
                label_examples="O algoritmo decide sem consultar o entregador, Aceitar qualquer pedido por medo de penalização, Os veteranos ensinam estratégias aos novatos",
                label_anti="Sem gerúndios forçados ou jargão",
                instruction=(
                    "Nomeie cada código com uma FRASE CURTA que descreva o conteúdo "
                    "do segmento com suas próprias palavras (não use gerúndios forçados). "
                    "A frase deve capturar a IDEIA CENTRAL em 3-8 palavras."
                ),
                rename_instruction=(
                    "Sugira renomeações como FRASES CURTAS descritivas. "
                    "Capture a ideia central expandida em linguagem natural."
                ),
            ),
        },
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
        i18n={
            "es": CodingStyleI18n(
                label_name="tema/subtema",
                label_format="TEMA → subtema",
                label_desc="Tema abstracto, opcionalmente con un subtema separado por →.",
                label_examples="Control algorítmico → Resistencia cotidiana, Supervivencia económica → Estrategias de corto plazo, Identidad profesional → Amenaza percibida",
                label_anti="Sin descripciones ni gerundios",
                instruction=(
                    "Nombra cada código con un TEMA principal y, si aplica, un SUBTEMA "
                    "separado por '→'. El tema debe ser un concepto abstracto, no una descripción."
                ),
                rename_instruction=(
                    "Sugiere renombres como TEMA → subtema. "
                    "Si la definición se expandió, el subtema puede refinarse o añadirse."
                ),
            ),
            "en": CodingStyleI18n(
                label_name="theme/subtheme",
                label_format="THEME → subtheme",
                label_desc="Abstract theme, optionally with a subtheme separated by →.",
                label_examples="Algorithmic control → Everyday resistance, Economic survival → Short-term strategies, Professional identity → Perceived threat",
                label_anti="No descriptions or gerunds",
                instruction=(
                    "Name each code with a main THEME and, if applicable, a SUBTHEME "
                    "separated by '→'. The theme should be an abstract concept, not a description."
                ),
                rename_instruction=(
                    "Suggest renames as THEME → subtheme. "
                    "If the definition expanded, the subtheme may be refined or added."
                ),
            ),
            "de": CodingStyleI18n(
                label_name="Thema/Unterthema",
                label_format="THEMA → Unterthema",
                label_desc="Abstraktes Thema, optional mit einem Unterthema getrennt durch →.",
                label_examples="Algorithmische Kontrolle → Alltäglicher Widerstand, Ökonomisches Überleben → Kurzfristige Strategien, Berufliche Identität → Wahrgenommene Bedrohung",
                label_anti="Keine Beschreibungen oder Gerundien",
                instruction=(
                    "Benenne jeden Code mit einem HAUPTTHEMA und, falls zutreffend, einem UNTERTHEMA, "
                    "getrennt durch '→'. Das Thema soll ein abstraktes Konzept sein, keine Beschreibung."
                ),
                rename_instruction=(
                    "Schlage Umbenennungen als THEMA → Unterthema vor. "
                    "Falls die Definition erweitert wurde, kann das Unterthema verfeinert oder hinzugefügt werden."
                ),
            ),
            "pt": CodingStyleI18n(
                label_name="tema/subtema",
                label_format="TEMA → subtema",
                label_desc="Tema abstrato, opcionalmente com um subtema separado por →.",
                label_examples="Controle algorítmico → Resistência cotidiana, Sobrevivência econômica → Estratégias de curto prazo, Identidade profissional → Ameaça percebida",
                label_anti="Sem descrições ou gerúndios",
                instruction=(
                    "Nomeie cada código com um TEMA principal e, se aplicável, um SUBTEMA "
                    "separado por '→'. O tema deve ser um conceito abstrato, não uma descrição."
                ),
                rename_instruction=(
                    "Sugira renomeações como TEMA → subtema. "
                    "Se a definição foi expandida, o subtema pode ser refinado ou adicionado."
                ),
            ),
        },
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
        i18n={
            "es": CodingStyleI18n(
                label_name="cadena causal",
                label_format="CAUSA → EFECTO",
                label_desc="Cadena causal usando → para indicar dirección.",
                label_examples="Falta de transparencia algorítmica → Desconfianza sistémica, Penalización por rechazo → Aceptación de pedidos no rentables, Experiencia acumulada → Sofisticación de estrategias de evasión",
                label_anti="Sin descripciones estáticas",
                instruction=(
                    "Nombra cada código como una CADENA CAUSAL usando '→' para indicar dirección. "
                    "El código debe expresar: CONDICIÓN o CAUSA → CONSECUENCIA o ESTRATEGIA."
                ),
                rename_instruction=(
                    "Sugiere renombres como CADENAS CAUSALES (A → B). "
                    "Si la definición se expandió, refina la causa o la consecuencia."
                ),
            ),
            "en": CodingStyleI18n(
                label_name="causal chain",
                label_format="CAUSE → EFFECT",
                label_desc="Causal chain using → to show direction.",
                label_examples="Lack of algorithmic transparency → Systemic distrust, Penalty for rejection → Acceptance of unprofitable orders, Accumulated experience → Sophistication of evasion strategies",
                label_anti="No static descriptions",
                instruction=(
                    "Name each code as a CAUSAL CHAIN using '→' to indicate direction. "
                    "The code should express: CONDITION or CAUSE → CONSEQUENCE or STRATEGY."
                ),
                rename_instruction=(
                    "Suggest renames as CAUSAL CHAINS (A → B). "
                    "If the definition expanded, refine the cause or the consequence."
                ),
            ),
            "de": CodingStyleI18n(
                label_name="Kausalkette",
                label_format="URSACHE → WIRKUNG",
                label_desc="Kausalkette mit → zur Angabe der Richtung.",
                label_examples="Mangelnde algorithmische Transparenz → Systemisches Misstrauen, Sanktionierung bei Ablehnung → Annahme unrentabler Aufträge, Akkumulierte Erfahrung → Verfeinerung von Umgehungsstrategien",
                label_anti="Keine statischen Beschreibungen",
                instruction=(
                    "Benenne jeden Code als KAUSALKETTE mit '→' zur Angabe der Richtung. "
                    "Der Code soll ausdrücken: BEDINGUNG oder URSACHE → KONSEQUENZ oder STRATEGIE."
                ),
                rename_instruction=(
                    "Schlage Umbenennungen als KAUSALKETTEN (A → B) vor. "
                    "Falls die Definition erweitert wurde, verfeinere die Ursache oder die Konsequenz."
                ),
            ),
            "pt": CodingStyleI18n(
                label_name="cadeia causal",
                label_format="CAUSA → EFEITO",
                label_desc="Cadeia causal usando → para indicar direção.",
                label_examples="Falta de transparência algorítmica → Desconfiança sistêmica, Penalização por rejeição → Aceitação de pedidos não rentáveis, Experiência acumulada → Sofisticação de estratégias de evasão",
                label_anti="Sem descrições estáticas",
                instruction=(
                    "Nomeie cada código como uma CADEIA CAUSAL usando '→' para indicar direção. "
                    "O código deve expressar: CONDIÇÃO ou CAUSA → CONSEQUÊNCIA ou ESTRATÉGIA."
                ),
                rename_instruction=(
                    "Sugira renomeações como CADEIAS CAUSAIS (A → B). "
                    "Se a definição foi expandida, refine a causa ou a consequência."
                ),
            ),
        },
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
        i18n={
            "es": CodingStyleI18n(
                label_name="cita in vivo",
                label_format='"cita del participante"',
                label_desc="Cita textual corta del participante, entre comillas.",
                label_examples='"la aplicación no te dice nada", "cada uno tiene su maña", "si no acepto, me quedo sin nada"',
                label_anti="Sin paráfrasis ni etiquetas inventadas",
                instruction=(
                    "Nombra cada código usando una CITA TEXTUAL CORTA del participante "
                    "(entre comillas). La cita debe capturar una expresión llamativa, "
                    "una metáfora nativa, o un término que el participante usa repetidamente."
                ),
                rename_instruction=(
                    "Sugiere renombres como CITAS TEXTUALES del participante. "
                    "Solo sugiere renombre si encontrás una cita MÁS PRECISA que la actual."
                ),
            ),
            "en": CodingStyleI18n(
                label_name="in vivo quote",
                label_format='"participant quote"',
                label_desc="Verbatim short quote from the participant in quotation marks.",
                label_examples='"the app doesn\'t tell you anything", "everyone has their own trick", "if I don\'t accept, I\'m left with nothing"',
                label_anti="No paraphrasing or invented labels",
                instruction=(
                    "Name each code using a SHORT VERBATIM QUOTE from the participant "
                    "(in quotation marks). The quote should capture a striking expression, "
                    "a native metaphor, or a term the participant uses repeatedly."
                ),
                rename_instruction=(
                    "Suggest renames as VERBATIM QUOTES from the participant. "
                    "Only suggest a rename if you find a MORE PRECISE quote than the current one."
                ),
            ),
            "de": CodingStyleI18n(
                label_name="In-vivo-Zitat",
                label_format='"Teilnehmerzitat"',
                label_desc="Wörtliches Kurzzitat des Teilnehmers in Anführungszeichen.",
                label_examples='"die App sagt dir gar nichts", "jeder hat so seine Tricks", "wenn ich nicht annehme, hab ich gar nichts"',
                label_anti="Kein Paraphrasieren oder erfundene Bezeichnungen",
                instruction=(
                    "Benenne jeden Code mit einem KURZEN WÖRTLICHEN ZITAT des Teilnehmers "
                    "(in Anführungszeichen). Das Zitat soll einen auffälligen Ausdruck, "
                    "eine native Metapher oder einen Begriff erfassen, den der Teilnehmer wiederholt verwendet."
                ),
                rename_instruction=(
                    "Schlage Umbenennungen als WÖRTLICHE ZITATE des Teilnehmers vor. "
                    "Schlage nur dann eine Umbenennung vor, wenn du ein PRÄZISERES Zitat als das aktuelle findest."
                ),
            ),
            "pt": CodingStyleI18n(
                label_name="citação in vivo",
                label_format='"citação do participante"',
                label_desc="Citação textual curta do participante, entre aspas.",
                label_examples='"o aplicativo não te diz nada", "cada um tem seu jeito", "se eu não aceitar, fico sem nada"',
                label_anti="Sem paráfrases ou rótulos inventados",
                instruction=(
                    "Nomeie cada código usando uma CITAÇÃO TEXTUAL CURTA do participante "
                    "(entre aspas). A citação deve capturar uma expressão chamativa, "
                    "uma metáfora nativa ou um termo que o participante usa repetidamente."
                ),
                rename_instruction=(
                    "Sugira renomeações como CITAÇÕES TEXTUAIS do participante. "
                    "Só sugira renomeação se encontrar uma citação MAIS PRECISA que a atual."
                ),
            ),
        },
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


# ═══════════════════════════════════════════════════════════════════════
# API i18n — tokens de estilo por idioma
# ═══════════════════════════════════════════════════════════════════════


def get_style_i18n(key: str, language: str) -> CodingStyleI18n:
    """Get i18n tokens for a coding style. Falls back to Spanish, then gerundio."""
    style = CODING_STYLES.get(key, CODING_STYLES["gerundio"])
    return (
        style.i18n.get(language) or style.i18n.get("es") or list(style.i18n.values())[0]
    )


def get_style_tokens(key: str, language: str) -> dict[str, str]:
    """Get all {label_*} tokens as a flat dict for prompt injection."""
    i18n = get_style_i18n(key, language)
    return {
        "label_name": i18n.label_name,
        "label_name_upper": i18n.label_name.upper(),
        "label_format": i18n.label_format,
        "label_format_upper": i18n.label_format.upper(),
        "label_desc": i18n.label_desc,
        "label_examples": i18n.label_examples,
        "label_anti": i18n.label_anti,
        "coding_style_instruction": i18n.instruction,
    }
