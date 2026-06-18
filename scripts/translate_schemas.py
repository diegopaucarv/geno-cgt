#!/usr/bin/env python3
"""
Translation engine for CGT agent JSON schemas.
Translates all schema.en.json → schema.{es,de,pt}.json
Only translates "description" field values. All else stays identical.

Some descriptions in schemas.py are already in Spanish — those are treated
as source-language-agnostic and get same translations in all three.
"""

import copy
import json
import os
import re

AGENTS_DIR = "/mnt/hdd/Program Files/Docker/gt/backend/app/prompts/agents"

# ── Translation map: English (or sometimes Spanish) description → {es, de, pt}
# For descriptions already in Spanish, DE/PT are still translated from English sense.
# Where descriptions are in Spanish originally, ES keeps them, DE/PT translate from the meaning.

TR = {
    # ── A1 / fa_population_context ──
    "Qué revela este documento sobre la población que no sabíamos. Integrar lo nuevo con lo existente.": {
        "es": "Qué revela este documento sobre la población que no sabíamos. Integrar lo nuevo con lo existente.",
        "de": "Was dieses Dokument über die Bevölkerung enthüllt, das wir noch nicht wussten. Das Neue mit dem Bestehenden integrieren.",
        "pt": "O que este documento revela sobre a população que não sabíamos. Integrar o novo com o existente.",
    },
    "Metáforas, eufemismos, estructuras discursivas, términos nativos.": {
        "es": "Metáforas, eufemismos, estructuras discursivas, términos nativos.",
        "de": "Metaphern, Euphemismen, diskursive Strukturen, native Begriffe.",
        "pt": "Metáforas, eufemismos, estruturas discursivas, termos nativos.",
    },
    "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.": {
        "es": "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.",
        "de": "Produktionsbedingungen der Daten: Interviewumgebung, Anzeichen sozialer Erwünschtheit, Ermüdung, Machtdynamiken.",
        "pt": "Condições de produção dos dados: ambiente de entrevista, sinais de desejabilidade social, fadiga, dinâmicas de poder.",
    },
    # ── A2 ──
    "Descripción en gerundio del proceso central que el entrevistado intenta resolver continuamente, con 2-3 oraciones de explicación.": {
        "es": "Descripción en gerundio del proceso central que el entrevistado intenta resolver continuamente, con 2-3 oraciones de explicación.",
        "de": "Beschreibung im Gerundium des zentralen Prozesses, den der Interviewte kontinuierlich zu lösen versucht, mit 2-3 erklärenden Sätzen.",
        "pt": "Descrição em gerúndio do processo central que o entrevistado tenta resolver continuamente, com 2-3 frases de explicação.",
    },
    "Descripción en gerundio del proceso central de ESTE entrevistado.": {
        "es": "Descripción en gerundio del proceso central de ESTE entrevistado.",
        "de": "Beschreibung im Gerundium des zentralen Prozesses DIESES Interviewten.",
        "pt": "Descrição em gerúndio do processo central DESTE entrevistado.",
    },
    "En qué se PARECE al proceso del entrevistado anterior.": {
        "es": "En qué se PARECE al proceso del entrevistado anterior.",
        "de": "Worin es dem Prozess des vorherigen Interviewten ÄHNELT.",
        "pt": "Em que se ASSEMELHA ao processo do entrevistado anterior.",
    },
    "En qué se DIFERENCIA del proceso del entrevistado anterior.": {
        "es": "En qué se DIFERENCIA del proceso del entrevistado anterior.",
        "de": "Worin es sich vom Prozess des vorherigen Interviewten UNTERSCHEIDET.",
        "pt": "Em que se DIFERENCIA do processo do entrevistado anterior.",
    },
    # ── A3 ──
    "Hipótesis completa.": {
        "es": "Hipótesis completa.",
        "de": "Vollständige Hypothese.",
        "pt": "Hipótese completa.",
    },
    "Evidencia concreta que la apoya.": {
        "es": "Evidencia concreta que la apoya.",
        "de": "Konkrete Belege, die sie stützen.",
        "pt": "Evidência concreta que a apoia.",
    },
    # ── B2 ──
    "Nombre en gerundio.": {
        "es": "Nombre en gerundio.",
        "de": "Name im Gerundium.",
        "pt": "Nome em gerúndio.",
    },
    # ── B2 Critic ──
    "Evaluations of each proposed code. Empty array if no codes to evaluate.": {
        "es": "Evaluaciones de cada código propuesto. Array vacío si no hay códigos que evaluar.",
        "de": "Bewertungen jedes vorgeschlagenen Codes. Leeres Array, wenn keine Codes zu bewerten sind.",
        "pt": "Avaliações de cada código proposto. Array vazio se não houver códigos para avaliar.",
    },
    "Name of the evaluated code (exact gerund)": {
        "es": "Nombre del código evaluado (gerundio exacto)",
        "de": "Name des bewerteten Codes (exaktes Gerundium)",
        "pt": "Nome do código avaliado (gerúndio exato)",
    },
    "SAT: correct and well defined. MOD: needs refinement. FORCED: no empirical basis.": {
        "es": "SAT: correcto y bien definido. MOD: necesita refinamiento. FORCED: sin base empírica.",
        "de": "SAT: korrekt und gut definiert. MOD: benötigt Verfeinerung. FORCED: keine empirische Grundlage.",
        "pt": "SAT: correto e bem definido. MOD: precisa de refinamento. FORCED: sem base empírica.",
    },
    "Detailed justification of the verdict, referencing specific segments.": {
        "es": "Justificación detallada del veredicto, referenciando segmentos específicos.",
        "de": "Detailierte Begründung des Urteils unter Bezugnahme auf bestimmte Segmente.",
        "pt": "Justificativa detalhada do veredito, referenciando segmentos específicos.",
    },
    "Are the incidents interchangeable? How do they differ if they are not? If not enough incidents to evaluate: 'Insufficient incidents to evaluate interchangeability.'": {
        "es": "¿Son los incidentes intercambiables? ¿En qué se diferencian si no lo son? Si no hay suficientes incidentes para evaluar: 'Incidentes insuficientes para evaluar intercambiabilidad.'",
        "de": "Sind die Vorfälle austauschbar? Wie unterscheiden sie sich, wenn nicht? Wenn nicht genügend Vorfälle zur Bewertung: 'Unzureichende Vorfälle zur Bewertung der Austauschbarkeit.'",
        "pt": "Os incidentes são intercambiáveis? Como diferem se não forem? Se não houver incidentes suficientes para avaliar: 'Incidentes insuficientes para avaliar intercambialidade.'",
    },
    "Only if MOD. Concrete action: new gerund, adjusted definition, or split into subcodes. If not applicable, leave empty string.": {
        "es": "Solo si MOD. Acción concreta: nuevo gerundio, definición ajustada, o división en subcódigos. Si no aplica, dejar string vacío.",
        "de": "Nur bei MOD. Konkrete Maßnahme: neues Gerundium, angepasste Definition oder Aufteilung in Subcodes. Falls nicht zutreffend, leeren String lassen.",
        "pt": "Apenas se MOD. Ação concreta: novo gerúndio, definição ajustada ou divisão em subcódigos. Se não aplicável, deixar string vazia.",
    },
    "Names of existing codes with which this one significantly overlaps. Empty array if no overlap.": {
        "es": "Nombres de códigos existentes con los que este se solapa significativamente. Array vacío si no hay solapamiento.",
        "de": "Namen bestehender Codes, mit denen dieser signifikant überlappt. Leeres Array, wenn keine Überlappung.",
        "pt": "Nomes de códigos existentes com os quais este se sobrepõe significativamente. Array vazio se não houver sobreposição.",
    },
    "Critic's confidence in this verdict. 0.0 = total doubt, 1.0 = absolute certainty.": {
        "es": "Confianza del crítico en este veredicto. 0.0 = duda total, 1.0 = certeza absoluta.",
        "de": "Vertrauen des Kritikers in dieses Urteil. 0.0 = völliger Zweifel, 1.0 = absolute Gewissheit.",
        "pt": "Confiança do crítico neste veredito. 0.0 = dúvida total, 1.0 = certeza absoluta.",
    },
    # ── f0_population_generalizer ──
    "Generalized population with theoretical scope. 1-2 sentences.": {
        "es": "Población generalizada con alcance teórico. 1-2 oraciones.",
        "de": "Generalisierte Bevölkerung mit theoretischem Geltungsbereich. 1-2 Sätze.",
        "pt": "População generalizada com escopo teórico. 1-2 frases.",
    },
    "Confidence in the generalization (0.0-1.0)": {
        "es": "Confianza en la generalización (0.0-1.0)",
        "de": "Vertrauen in die Generalisierung (0.0-1.0)",
        "pt": "Confiança na generalização (0.0-1.0)",
    },
    "Brief justification of the generalization (2-3 sentences)": {
        "es": "Justificación breve de la generalización (2-3 oraciones)",
        "de": "Kurze Begründung der Generalisierung (2-3 Sätze)",
        "pt": "Justificativa breve da generalização (2-3 frases)",
    },
    # ── f6a_final_report ──
    "Full report title: '{Core Pattern} — A Classic Grounded Theory of {Generalized Population}'": {
        "es": "Título completo del informe: '{Patrón Central} — Una Teoría Fundamentada Clásica de {Población Generalizada}'",
        "de": "Vollständiger Berichtstitel: '{Kernmuster} — Eine klassische Grounded Theory der {Generalisierten Bevölkerung}'",
        "pt": "Título completo do relatório: '{Padrão Central} — Uma Teoria Fundamentada Clássica de {População Generalizada}'",
    },
    "~200 word self-contained summary. Core pattern, core category, population, contribution, implications.": {
        "es": "Resumen autónomo de ~200 palabras. Patrón central, categoría central, población, contribución, implicaciones.",
        "de": "~200 Worte eigenständige Zusammenfassung. Kernmuster, Kernkategorie, Bevölkerung, Beitrag, Implikationen.",
        "pt": "Resumo autônomo de ~200 palavras. Padrão central, categoria central, população, contribuição, implicações.",
    },
    "Section heading adapted to object_of_study: 'Core Concern', 'Core Emotion', 'Core Behavior', etc.": {
        "es": "Encabezado de sección adaptado al objeto de estudio: 'Preocupación Central', 'Emoción Central', 'Comportamiento Central', etc.",
        "de": "Abschnittsüberschrift angepasst an den Untersuchungsgegenstand: 'Kernanliegen', 'Kernemotion', 'Kernverhalten' usw.",
        "pt": "Título da seção adaptado ao objeto de estudo: 'Preocupação Central', 'Emoção Central', 'Comportamento Central', etc.",
    },
    "The gerund that names the core pattern. Explanation of what the pattern IS and why this gerund captures it.": {
        "es": "El gerundio que nombra el patrón central. Explicación de qué ES el patrón y por qué este gerundio lo captura.",
        "de": "Das Gerundium, das das Kernmuster benennt. Erklärung, WAS das Muster ist und warum dieses Gerundium es erfasst.",
        "pt": "O gerúndio que nomeia o padrão central. Explicação do que o padrão É e por que este gerúndio o captura.",
    },
    "How the pattern emerged from the data. Convergence across documents, key discovery moments, evolution of understanding.": {
        "es": "Cómo emergió el patrón de los datos. Convergencia entre documentos, momentos clave de descubrimiento, evolución de la comprensión.",
        "de": "Wie das Muster aus den Daten entstand. Konvergenz über Dokumente hinweg, Schlüsselmomente der Entdeckung, Entwicklung des Verständnisses.",
        "pt": "Como o padrão emergiu dos dados. Convergência entre documentos, momentos-chave de descoberta, evolução da compreensão.",
    },
    "Strongest data incidents and codes supporting the pattern. Variation in how participants experience it. Trace to specific nodes/incidents.": {
        "es": "Incidentes de datos y códigos más sólidos que respaldan el patrón. Variación en cómo los participantes lo experimentan. Trazabilidad a nodos/incidentes específicos.",
        "de": "Stärkste Datenvorfälle und Codes, die das Muster stützen. Variation darin, wie Teilnehmer es erleben. Rückverfolgung zu bestimmten Knoten/Vorfällen.",
        "pt": "Incidentes de dados e códigos mais fortes que sustentam o padrão. Variação em como os participantes o experienciam. Rastreabilidade a nós/incidentes específicos.",
    },
    "Always 'Core Category' — this is a formal CGT construct, not adapted to object_of_study.": {
        "es": "Siempre 'Categoría Central' — es un constructo formal de CGT, no adaptado al objeto de estudio.",
        "de": "Immer 'Kernkategorie' — dies ist ein formales CGT-Konstrukt, nicht an den Untersuchungsgegenstand angepasst.",
        "pt": "Sempre 'Categoria Central' — é um construto formal da CGT, não adaptado ao objeto de estudo.",
    },
    "Precise conceptual definition of the core category. What it IS, not what it does (that goes in the model).": {
        "es": "Definición conceptual precisa de la categoría central. Lo que ES, no lo que hace (eso va en el modelo).",
        "de": "Präzise konzeptuelle Definition der Kernkategorie. Was sie IST, nicht was sie tut (das gehört ins Modell).",
        "pt": "Definição conceitual precisa da categoria central. O que ela É, não o que faz (isso vai no modelo).",
    },
    "Properties of the core category, each with its dimensional range.": {
        "es": "Propiedades de la categoría central, cada una con su rango dimensional.",
        "de": "Eigenschaften der Kernkategorie, jede mit ihrem dimensionalen Bereich.",
        "pt": "Propriedades da categoria central, cada uma com seu alcance dimensional.",
    },
    "Property name.": {
        "es": "Nombre de la propiedad.",
        "de": "Name der Eigenschaft.",
        "pt": "Nome da propriedade.",
    },
    "What this property captures about the core category.": {
        "es": "Lo que esta propiedad captura sobre la categoría central.",
        "de": "Was diese Eigenschaft über die Kernkategorie erfasst.",
        "pt": "O que esta propriedade captura sobre a categoria central.",
    },
    "The range of variation observed for this property (e.g., 'low to high intensity', 'narrow to broad scope').": {
        "es": "El rango de variación observado para esta propiedad (ej., 'intensidad baja a alta', 'alcance estrecho a amplio').",
        "de": "Der beobachtete Variationsbereich dieser Eigenschaft (z.B. 'niedrige bis hohe Intensität', 'enger bis breiter Umfang').",
        "pt": "A faixa de variação observada para esta propriedade (ex., 'intensidade baixa a alta', 'escopo estreito a amplo').",
    },
    "How this category processes, resolves, or addresses the core pattern. The explanatory link between Sections 2 and 3.": {
        "es": "Cómo esta categoría procesa, resuelve o aborda el patrón central. El vínculo explicativo entre las Secciones 2 y 3.",
        "de": "Wie diese Kategorie das Kernmuster verarbeitet, auflöst oder adressiert. Die erklärende Verbindung zwischen Abschnitten 2 und 3.",
        "pt": "Como esta categoria processa, resolve ou aborda o padrão central. O vínculo explicativo entre as Seções 2 e 3.",
    },
    "Always 'Theoretical Model'.": {
        "es": "Siempre 'Modelo Teórico'.",
        "de": "Immer 'Theoretisches Modell'.",
        "pt": "Sempre 'Modelo Teórico'.",
    },
    "Narrative summary of the full theoretical model. How conditions, strategies, and consequences interconnect through the core category.": {
        "es": "Resumen narrativo del modelo teórico completo. Cómo condiciones, estrategias y consecuencias se interconectan a través de la categoría central.",
        "de": "Narrative Zusammenfassung des vollständigen theoretischen Modells. Wie Bedingungen, Strategien und Konsequenzen durch die Kernkategorie miteinander verbunden sind.",
        "pt": "Resumo narrativo do modelo teórico completo. Como condições, estratégias e consequências se interconectam através da categoria central.",
    },
    "Antecedent and structural conditions that shape how the core category operates. Causal and contextual conditions from nodes with entity_type 'condition'.": {
        "es": "Condiciones antecedentes y estructurales que moldean cómo opera la categoría central. Condiciones causales y contextuales de nodos con entity_type 'condition'.",
        "de": "Vorgelagerte und strukturelle Bedingungen, die prägen, wie die Kernkategorie operiert. Kausale und kontextuelle Bedingungen von Knoten mit entity_type 'condition'.",
        "pt": "Condições antecedentes e estruturais que moldam como a categoria central opera. Condições causais e contextuais de nós com entity_type 'condition'.",
    },
    "The central PROCESSES edge: how the core category processes/resolves the core pattern. This is the obligatory spine of the model. Must be derived from the PROCESSES edge in the input.": {
        "es": "La arista PROCESSES central: cómo la categoría central procesa/resuelve el patrón central. Es la columna vertebral obligatoria del modelo. Debe derivarse de la arista PROCESSES en la entrada.",
        "de": "Die zentrale PROCESSES-Kante: wie die Kernkategorie das Kernmuster verarbeitet/auflöst. Dies ist das obligatorische Rückgrat des Modells. Muss aus der PROCESSES-Kante in der Eingabe abgeleitet werden.",
        "pt": "A aresta PROCESSES central: como a categoria central processa/resolve o padrão central. Esta é a espinha dorsal obrigatória do modelo. Deve ser derivada da aresta PROCESSES na entrada.",
    },
    "Behavioral and cognitive strategies participants employ. Derived from nodes with entity_type 'strategy' and IS_A_STRATEGY_FOR edges.": {
        "es": "Estrategias conductuales y cognitivas que emplean los participantes. Derivadas de nodos con entity_type 'strategy' y aristas IS_A_STRATEGY_FOR.",
        "de": "Verhaltens- und kognitive Strategien, die Teilnehmer anwenden. Abgeleitet von Knoten mit entity_type 'strategy' und IS_A_STRATEGY_FOR-Kanten.",
        "pt": "Estratégias comportamentais e cognitivas que os participantes empregam. Derivadas de nós com entity_type 'strategy' e arestas IS_A_STRATEGY_FOR.",
    },
    "Outcomes and results, both intended and unintended. Derived from nodes with entity_type 'consequence' and IS_A_CONSEQUENCE_OF edges.": {
        "es": "Resultados y consecuencias, tanto intencionadas como no intencionadas. Derivadas de nodos con entity_type 'consequence' y aristas IS_A_CONSEQUENCE_OF.",
        "de": "Ergebnisse und Resultate, sowohl beabsichtigt als auch unbeabsichtigt. Abgeleitet von Knoten mit entity_type 'consequence' und IS_A_CONSEQUENCE_OF-Kanten.",
        "pt": "Resultados e consequências, tanto intencionais quanto não intencionais. Derivados de nós com entity_type 'consequence' e arestas IS_A_CONSEQUENCE_OF.",
    },
    "Structured listing of all theoretical relationships (edges). PROCESSES edge MUST be first. Organized by relationship type.": {
        "es": "Listado estructurado de todas las relaciones teóricas (aristas). La arista PROCESSES DEBE ser la primera. Organizado por tipo de relación.",
        "de": "Strukturierte Auflistung aller theoretischen Beziehungen (Kanten). Die PROCESSES-Kante MUSS zuerst sein. Organisiert nach Beziehungstyp.",
        "pt": "Listagem estruturada de todas as relações teóricas (arestas). A aresta PROCESSES DEVE ser a primeira. Organizado por tipo de relação.",
    },
    "Canonical CGT relationship type.": {
        "es": "Tipo de relación canónica de CGT.",
        "de": "Kanonischer CGT-Beziehungstyp.",
        "pt": "Tipo de relação canônica da CGT.",
    },
    "Source node label.": {
        "es": "Etiqueta del nodo fuente.",
        "de": "Bezeichnung des Quellknotens.",
        "pt": "Rótulo do nó fonte.",
    },
    "Target node label.": {
        "es": "Etiqueta del nodo destino.",
        "de": "Bezeichnung des Zielknotens.",
        "pt": "Rótulo do nó destino.",
    },
    "One-sentence narrative of the relationship in conceptual present tense.": {
        "es": "Narrativa de una oración de la relación en presente conceptual.",
        "de": "Ein-Satz-Erzählung der Beziehung in konzeptueller Gegenwartsform.",
        "pt": "Narrativa de uma frase da relação no presente conceitual.",
    },
    "Always 'Population Dimensions'.": {
        "es": "Siempre 'Dimensiones Poblacionales'.",
        "de": "Immer 'Bevölkerungsdimensionen'.",
        "pt": "Sempre 'Dimensões Populacionais'.",
    },
    "The generalized population to which the theory applies. Abstract enough for transferability, specific enough to be meaningful.": {
        "es": "La población generalizada a la que se aplica la teoría. Suficientemente abstracta para transferibilidad, suficientemente específica para ser significativa.",
        "de": "Die generalisierte Bevölkerung, auf die die Theorie zutrifft. Abstrakt genug für Übertragbarkeit, spezifisch genug, um bedeutsam zu sein.",
        "pt": "A população generalizada à qual a teoria se aplica. Abstrata o suficiente para transferibilidade, específica o suficiente para ser significativa.",
    },
    "How the core pattern and core category manifest differently across population dimensions. Document the range of variation, not just central tendency.": {
        "es": "Cómo el patrón central y la categoría central se manifiestan de manera diferente a través de las dimensiones poblacionales. Documentar el rango de variación, no solo la tendencia central.",
        "de": "Wie sich das Kernmuster und die Kernkategorie über Bevölkerungsdimensionen hinweg unterschiedlich manifestieren. Die Variationsbreite dokumentieren, nicht nur die zentrale Tendenz.",
        "pt": "Como o padrão central e a categoria central se manifestam diferentemente através das dimensões populacionais. Documentar a faixa de variação, não apenas a tendência central.",
    },
    "Where the theory does NOT apply. Populations, contexts, or conditions excluded. Honest scope assessment.": {
        "es": "Dónde NO se aplica la teoría. Poblaciones, contextos o condiciones excluidas. Evaluación honesta del alcance.",
        "de": "Wo die Theorie NICHT zutrifft. Ausgeschlossene Bevölkerungen, Kontexte oder Bedingungen. Ehrliche Einschätzung des Geltungsbereichs.",
        "pt": "Onde a teoria NÃO se aplica. Populações, contextos ou condições excluídas. Avaliação honesta do escopo.",
    },
    "Always 'Literature Dialogue'.": {
        "es": "Siempre 'Diálogo con la Literatura'.",
        "de": "Immer 'Literaturdialog'.",
        "pt": "Sempre 'Diálogo com a Literatura'.",
    },
    "Global evaluation: does the theory genuinely dialogue with literature, or is it forced to fit? Candid assessment.": {
        "es": "Evaluación global: ¿la teoría dialoga genuinamente con la literatura o se fuerza a encajar? Evaluación sincera.",
        "de": "Globale Bewertung: Dialogisiert die Theorie tatsächlich mit der Literatur oder wird sie gewaltsam angepasst? Ehrliche Einschätzung.",
        "pt": "Avaliação global: a teoria dialoga genuinamente com a literatura ou é forçada a se encaixar? Avaliação sincera.",
    },
    "Where the literature confirms and the theory extends existing knowledge with new properties, dimensions, or relationships.": {
        "es": "Donde la literatura confirma y la teoría extiende el conocimiento existente con nuevas propiedades, dimensiones o relaciones.",
        "de": "Wo die Literatur bestätigt und die Theorie bestehendes Wissen mit neuen Eigenschaften, Dimensionen oder Beziehungen erweitert.",
        "pt": "Onde a literatura confirma e a teoria estende o conhecimento existente com novas propriedades, dimensões ou relações.",
    },
    "Where the literature suggests modifications to received concepts, and how the emergent theory revises them.": {
        "es": "Donde la literatura sugiere modificaciones a conceptos recibidos, y cómo la teoría emergente los revisa.",
        "de": "Wo die Literatur Modifikationen an übernommenen Konzepten vorschlägt und wie die emergente Theorie sie revidiert.",
        "pt": "Onde a literatura sugere modificações a conceitos recebidos, e como a teoria emergente os revisa.",
    },
    "Where the theory unifies scattered concepts from the literature into a coherent explanatory framework.": {
        "es": "Donde la teoría unifica conceptos dispersos de la literatura en un marco explicativo coherente.",
        "de": "Wo die Theorie verstreute Konzepte aus der Literatur in einen kohärenten Erklärungsrahmen vereint.",
        "pt": "Onde a teoria unifica conceitos dispersos da literatura em um quadro explicativo coerente.",
    },
    "What the theory reveals that the literature had not captured. The novel contribution of this grounded theory.": {
        "es": "Lo que la teoría revela que la literatura no había capturado. La contribución novedosa de esta teoría fundamentada.",
        "de": "Was die Theorie offenbart, das die Literatur nicht erfasst hatte. Der neuartige Beitrag dieser Grounded Theory.",
        "pt": "O que a teoria revela que a literatura não havia capturado. A contribuição inovadora desta teoria fundamentada.",
    },
    "Always 'Applicability'.": {
        "es": "Siempre 'Aplicabilidad'.",
        "de": "Immer 'Anwendbarkeit'.",
        "pt": "Sempre 'Aplicabilidade'.",
    },
    "Aspects of the phenomenon that can be modified in practice. Each traces to a theoretical property.": {
        "es": "Aspectos del fenómeno que pueden modificarse en la práctica. Cada uno se remonta a una propiedad teórica.",
        "de": "Aspekte des Phänomens, die in der Praxis verändert werden können. Jeder geht auf eine theoretische Eigenschaft zurück.",
        "pt": "Aspectos do fenômeno que podem ser modificados na prática. Cada um remonta a uma propriedade teórica.",
    },
    "Control variable name.": {
        "es": "Nombre de la variable de control.",
        "de": "Name der Kontrollvariable.",
        "pt": "Nome da variável de controle.",
    },
    "What can be modified and how.": {
        "es": "Qué se puede modificar y cómo.",
        "de": "Was verändert werden kann und wie.",
        "pt": "O que pode ser modificado e como.",
    },
    "Which theoretical property or relationship justifies this as modifiable.": {
        "es": "Qué propiedad o relación teórica justifica que esto sea modificable.",
        "de": "Welche theoretische Eigenschaft oder Beziehung dies als veränderbar rechtfertigt.",
        "pt": "Qual propriedade ou relação teórica justifica que isto seja modificável.",
    },
    "Conditions that enable or constrain intervention.": {
        "es": "Condiciones que habilitan o restringen la intervención.",
        "de": "Bedingungen, die Intervention ermöglichen oder einschränken.",
        "pt": "Condições que habilitam ou restringem a intervenção.",
    },
    "Access variable name.": {
        "es": "Nombre de la variable de acceso.",
        "de": "Name der Zugangsvariable.",
        "pt": "Nome da variável de acesso.",
    },
    "What this variable conditions.": {
        "es": "Lo que esta variable condiciona.",
        "de": "Was diese Variable bedingt.",
        "pt": "O que esta variável condiciona.",
    },
    "How this variable enables or constrains access to the control variables.": {
        "es": "Cómo esta variable habilita o restringe el acceso a las variables de control.",
        "de": "Wie diese Variable den Zugang zu den Kontrollvariablen ermöglicht oder einschränkt.",
        "pt": "Como esta variável habilita ou restringe o acesso às variáveis de controle.",
    },
    "Concrete recommendations for practitioners.": {
        "es": "Recomendaciones concretas para profesionales.",
        "de": "Konkrete Empfehlungen für Praktiker.",
        "pt": "Recomendações concretas para profissionais.",
    },
    "The actionable recommendation.": {
        "es": "La recomendación accionable.",
        "de": "Die umsetzbare Empfehlung.",
        "pt": "A recomendação acionável.",
    },
    "Who acts on this guideline (e.g., practitioner, organization, participant).": {
        "es": "Quién actúa sobre esta directriz (ej., profesional, organización, participante).",
        "de": "Wer nach dieser Richtlinie handelt (z.B. Praktiker, Organisation, Teilnehmer).",
        "pt": "Quem age sobre esta diretriz (ex., profissional, organização, participante).",
    },
    "How the guideline produces change, traced to a theoretical mechanism.": {
        "es": "Cómo la directriz produce cambio, trazado a un mecanismo teórico.",
        "de": "Wie die Richtlinie Veränderung bewirkt, zurückgeführt auf einen theoretischen Mechanismus.",
        "pt": "Como a diretriz produz mudança, rastreada a um mecanismo teórico.",
    },
    "What the theory does NOT support in terms of intervention. Guard against over-application.": {
        "es": "Lo que la teoría NO respalda en términos de intervención. Proteger contra la sobre-aplicación.",
        "de": "Was die Theorie in Bezug auf Intervention NICHT unterstützt. Schutz vor Überanwendung.",
        "pt": "O que a teoria NÃO apoia em termos de intervenção. Proteger contra a superaplicação.",
    },
    "Always 'Research Trajectory'.": {
        "es": "Siempre 'Trayectoria de Investigación'.",
        "de": "Immer 'Forschungsverlauf'.",
        "pt": "Sempre 'Trajetória de Pesquisa'.",
    },
    "Theoretical questions the current data cannot answer. Properties needing further dimensionalization.": {
        "es": "Preguntas teóricas que los datos actuales no pueden responder. Propiedades que necesitan mayor dimensionalización.",
        "de": "Theoretische Fragen, die die aktuellen Daten nicht beantworten können. Eigenschaften, die weiterer Dimensionalisierung bedürfen.",
        "pt": "Perguntas teóricas que os dados atuais não podem responder. Propriedades que precisam de maior dimensionalização.",
    },
    "The open theoretical question.": {
        "es": "La pregunta teórica abierta.",
        "de": "Die offene theoretische Frage.",
        "pt": "A pergunta teórica aberta.",
    },
    "Why current data cannot resolve this question (insufficient variation, undersampled dimension, etc.).": {
        "es": "Por qué los datos actuales no pueden resolver esta pregunta (variación insuficiente, dimensión submuestreada, etc.).",
        "de": "Warum aktuelle Daten diese Frage nicht lösen können (unzureichende Variation, untererfasste Dimension usw.).",
        "pt": "Por que os dados atuais não podem resolver esta pergunta (variação insuficiente, dimensão subamostrada, etc.).",
    },
    "Limitations inherent to study design, sampling, or analytical choices. Candid self-assessment.": {
        "es": "Limitaciones inherentes al diseño del estudio, muestreo o decisiones analíticas. Autoevaluación sincera.",
        "de": "Einschränkungen, die dem Studiendesign, der Stichprobe oder analytischen Entscheidungen innewohnen. Ehrliche Selbsteinschätzung.",
        "pt": "Limitações inerentes ao desenho do estudo, amostragem ou decisões analíticas. Autoavaliação sincera.",
    },
    "Concrete next studies, populations to sample, comparisons to pursue.": {
        "es": "Próximos estudios concretos, poblaciones a muestrear, comparaciones a realizar.",
        "de": "Konkrete nächste Studien, zu untersuchende Bevölkerungen, zu verfolgende Vergleiche.",
        "pt": "Próximos estudos concretos, populações a amostrar, comparações a realizar.",
    },
    "Proposed future research direction.": {
        "es": "Dirección propuesta para investigación futura.",
        "de": "Vorgeschlagene zukünftige Forschungsrichtung.",
        "pt": "Direção proposta para pesquisa futura.",
    },
    "Why this direction emerges from the theory's current gaps or open questions.": {
        "es": "Por qué esta dirección emerge de los vacíos o preguntas abiertas actuales de la teoría.",
        "de": "Warum diese Richtung aus den aktuellen Lücken oder offenen Fragen der Theorie entsteht.",
        "pt": "Por que esta direção emerge das lacunas ou perguntas abertas atuais da teoria.",
    },
    # ── f6a_gap_feeler ──
    "Detected theoretical gaps. May be empty if the draft is structurally sound.": {
        "es": "Vacíos teóricos detectados. Puede estar vacío si el borrador es estructuralmente sólido.",
        "de": "Erkannte theoretische Lücken. Kann leer sein, wenn der Entwurf strukturell solide ist.",
        "pt": "Lacunas teóricas detectadas. Pode estar vazio se o rascunho for estruturalmente sólido.",
    },
    "Gap classification from the five canonical types.": {
        "es": "Clasificación de vacío de los cinco tipos canónicos.",
        "de": "Lückenklassifikation aus den fünf kanonischen Typen.",
        "pt": "Classificação de lacuna dos cinco tipos canônicos.",
    },
    "One-sentence description of the gap: what is missing or weakened.": {
        "es": "Descripción de una oración del vacío: qué falta o está debilitado.",
        "de": "Ein-Satz-Beschreibung der Lücke: was fehlt oder geschwächt ist.",
        "pt": "Descrição de uma frase da lacuna: o que está faltando ou enfraquecido.",
    },
    "Severity after context-aware scaling. HIGH=blocks publication, MEDIUM=needs expansion, LOW=cosmetic.": {
        "es": "Severidad tras escalado contextual. HIGH=bloquea publicación, MEDIUM=necesita expansión, LOW=cosmético.",
        "de": "Schweregrad nach kontextbewusster Skalierung. HIGH=blockiert Veröffentlichung, MEDIUM=benötigt Erweiterung, LOW=kosmetisch.",
        "pt": "Severidade após escalonamento contextual. HIGH=bloqueia publicação, MEDIUM=precisa de expansão, LOW=cosmético.",
    },
    "Specific location: section name, paragraph number, or quoted sentence fragment.": {
        "es": "Ubicación específica: nombre de sección, número de párrafo o fragmento de oración citado.",
        "de": "Spezifischer Ort: Abschnittsname, Absatznummer oder zitiertes Satzfragment.",
        "pt": "Localização específica: nome da seção, número do parágrafo ou fragmento de frase citado.",
    },
    "true if the gap is in or near a paragraph referencing the core concern.": {
        "es": "true si el vacío está en o cerca de un párrafo que referencia la preocupación central.",
        "de": "true, wenn die Lücke in oder nahe einem Absatz liegt, der das Kernanliegen referenziert.",
        "pt": "true se a lacuna estiver em ou perto de um parágrafo referenciando a preocupação central.",
    },
    "Total number of gaps detected.": {
        "es": "Número total de vacíos detectados.",
        "de": "Gesamtzahl der erkannten Lücken.",
        "pt": "Número total de lacunas detectadas.",
    },
    "One-sentence diagnostic summary, e.g. '3 gaps: 1 HIGH (missing evidence on core claim), 1 MEDIUM, 1 LOW'.": {
        "es": "Resumen diagnóstico de una oración, ej. '3 vacíos: 1 HIGH (falta evidencia en afirmación central), 1 MEDIUM, 1 LOW'.",
        "de": "Ein-Satz-Diagnosezusammenfassung, z.B. '3 Lücken: 1 HIGH (fehlende Belege für Kernbehauptung), 1 MEDIUM, 1 LOW'.",
        "pt": "Resumo diagnóstico de uma frase, ex. '3 lacunas: 1 HIGH (falta evidência na afirmação central), 1 MEDIUM, 1 LOW'.",
    },
    # ── f6a_natural_writer ──
    "Complete draft in academic prose": {
        "es": "Borrador completo en prosa académica",
        "de": "Vollständiger Entwurf in akademischer Prosa",
        "pt": "Rascunho completo em prosa acadêmica",
    },
    "UUIDs of memos that did not integrate naturally into the draft": {
        "es": "UUIDs de memos que no se integraron naturalmente en el borrador",
        "de": "UUIDs von Memos, die sich nicht natürlich in den Entwurf integriert haben",
        "pt": "UUIDs de memos que não se integraram naturalmente ao rascunho",
    },
    # ── f6a_writing_critic ──
    "Type of infraction: tense | subject | citation | fidelity | intro | abstraction": {
        "es": "Tipo de infracción: tiempo | sujeto | cita | fidelidad | intro | abstracción",
        "de": "Art des Verstoßes: Tempus | Subjekt | Zitat | Genauigkeit | Einleitung | Abstraktion",
        "pt": "Tipo de infração: tempo | sujeito | citação | fidelidade | intro | abstração",
    },
    "Text fragment where the infraction occurs": {
        "es": "Fragmento de texto donde ocurre la infracción",
        "de": "Textfragment, in dem der Verstoß auftritt",
        "pt": "Fragmento de texto onde a infração ocorre",
    },
    "Suggested correction": {
        "es": "Corrección sugerida",
        "de": "Vorgeschlagene Korrektur",
        "pt": "Correção sugerida",
    },
    "Summary of 2-3 sentences of the global evaluation": {
        "es": "Resumen de 2-3 oraciones de la evaluación global",
        "de": "Zusammenfassung von 2-3 Sätzen der globalen Bewertung",
        "pt": "Resumo de 2-3 frases da avaliação global",
    },
    # ── Common short descriptions ──
    "Codes generated from the indicators.": {
        "es": "Códigos generados a partir de los indicadores.",
        "de": "Aus den Indikatoren generierte Codes.",
        "pt": "Códigos gerados a partir dos indicadores.",
    },
    "Gerund of the code.": {
        "es": "Gerundio del código.",
        "de": "Gerundium des Codes.",
        "pt": "Gerúndio do código.",
    },
    "Definition: what behavioral pattern it captures, in 1-2 sentences.": {
        "es": "Definición: qué patrón de comportamiento captura, en 1-2 oraciones.",
        "de": "Definition: welches Verhaltensmuster es erfasst, in 1-2 Sätzen.",
        "pt": "Definição: qual padrão de comportamento captura, em 1-2 frases.",
    },
    "Indicators that support this code.": {
        "es": "Indicadores que respaldan este código.",
        "de": "Indikatoren, die diesen Code stützen.",
        "pt": "Indicadores que sustentam este código.",
    },
    "Internal variations observed (degrees, nuances, contexts).": {
        "es": "Variaciones internas observadas (grados, matices, contextos).",
        "de": "Beobachtete interne Variationen (Grade, Nuancen, Kontexte).",
        "pt": "Variações internas observadas (graus, nuances, contextos).",
    },
    "Relationship to existing codes: 'New', 'Subcode of X', 'Overlaps with Y'.": {
        "es": "Relación con códigos existentes: 'Nuevo', 'Subcódigo de X', 'Se solapa con Y'.",
        "de": "Beziehung zu bestehenden Codes: 'Neu', 'Subcode von X', 'Überlappt mit Y'.",
        "pt": "Relação com códigos existentes: 'Novo', 'Subcódigo de X', 'Sobrepõe-se a Y'.",
    },
    "true if all codes pass review.": {
        "es": "true si todos los códigos pasan la revisión.",
        "de": "true, wenn alle Codes die Prüfung bestehen.",
        "pt": "true se todos os códigos passarem na revisão.",
    },
    "Name of the code with problems.": {
        "es": "Nombre del código con problemas.",
        "de": "Name des Codes mit Problemen.",
        "pt": "Nome do código com problemas.",
    },
    "Type of problem.": {
        "es": "Tipo de problema.",
        "de": "Art des Problems.",
        "pt": "Tipo de problema.",
    },
    "How to fix it. One concrete sentence.": {
        "es": "Cómo corregirlo. Una oración concreta.",
        "de": "Wie es zu beheben ist. Ein konkreter Satz.",
        "pt": "Como corrigi-lo. Uma frase concreta.",
    },
    "Core concern candidates extracted from the synthesis. Between 2 and 4.": {
        "es": "Candidatos a preocupación central extraídos de la síntesis. Entre 2 y 4.",
        "de": "Kernanliegen-Kandidaten aus der Synthese extrahiert. Zwischen 2 und 4.",
        "pt": "Candidatos a preocupação central extraídos da síntese. Entre 2 e 4.",
    },
}

print(f"Translation map has {len(TR)} entries")


# ── Translate a schema recursively ──
def translate_schema(schema, lang):
    """Deep copy the schema, translating only description values."""
    if isinstance(schema, dict):
        result = {}
        for k, v in schema.items():
            if k == "description" and isinstance(v, str):
                if v in TR:
                    result[k] = TR[v].get(lang, v)
                else:
                    # Fallback: keep original but log
                    result[k] = v
                    print(f"  ⚠ NO TRANSLATION [{lang}]: {v[:80]}...")
            else:
                result[k] = translate_schema(v, lang)
        return result
    elif isinstance(schema, list):
        return [translate_schema(item, lang) for item in schema]
    else:
        return schema


# ── Main ──
agents = sorted(
    d for d in os.listdir(AGENTS_DIR) if os.path.isdir(os.path.join(AGENTS_DIR, d))
)
total = len(agents)
missing = 0

for i, agent_id in enumerate(agents):
    agent_dir = os.path.join(AGENTS_DIR, agent_id)
    en_path = os.path.join(agent_dir, "schema.en.json")
    if not os.path.exists(en_path):
        continue

    with open(en_path, encoding="utf-8") as f:
        schema = json.load(f)

    for lang_code, lang_name in [
        ("es", "Spanish"),
        ("de", "German"),
        ("pt", "Portuguese"),
    ]:
        out_path = os.path.join(agent_dir, f"schema.{lang_code}.json")
        translated = translate_schema(schema, lang_code)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(translated, f, indent=2, ensure_ascii=False)

print(f"\nProcessed {total} agents. Missing translations: {missing}")
