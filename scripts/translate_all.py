#!/usr/bin/env python3
"""
Complete translation engine for CGT agent JSON schemas.
Translates all schema.en.json → schema.{es,de,pt}.json
Only "description" values are translated. All else stays identical.
Handles both flat schemas and json_schema wrapper format.
"""

import copy
import json
import os

AGENTS_DIR = "/mnt/hdd/Program Files/Docker/gt/backend/app/prompts/agents"

# ── COMPLETE Translation Map ──────────────────────────────────────
# Every unique description string mapped to {es, de, pt}

TR = {}


def add(en, es, de, pt):
    TR[en] = {"es": es, "de": de, "pt": pt}


# ── Already-in-Spanish descriptions (from schemas.py) ──
add(
    "Qué revela este documento sobre la población que no sabíamos. Integrar lo nuevo con lo existente.",
    "Qué revela este documento sobre la población que no sabíamos. Integrar lo nuevo con lo existente.",
    "Was dieses Dokument über die Bevölkerung enthüllt, das wir noch nicht wussten. Das Neue mit dem Bestehenden integrieren.",
    "O que este documento revela sobre a população que não sabíamos. Integrar o novo com o existente.",
)
add(
    "Metáforas, eufemismos, estructuras discursivas, términos nativos.",
    "Metáforas, eufemismos, estructuras discursivas, términos nativos.",
    "Metaphern, Euphemismen, diskursive Strukturen, native Begriffe.",
    "Metáforas, eufemismos, estruturas discursivas, termos nativos.",
)
add(
    "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.",
    "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.",
    "Produktionsbedingungen der Daten: Interviewumgebung, Anzeichen sozialer Erwünschtheit, Ermüdung, Machtdynamiken.",
    "Condições de produção dos dados: ambiente de entrevista, sinais de desejabilidade social, fadiga, dinâmicas de poder.",
)
add(
    "Descripción en gerundio del proceso central que el entrevistado intenta resolver continuamente, con 2-3 oraciones de explicación.",
    "Descripción en gerundio del proceso central que el entrevistado intenta resolver continuamente, con 2-3 oraciones de explicación.",
    "Beschreibung im Gerundium des zentralen Prozesses, den der Interviewte kontinuierlich zu lösen versucht, mit 2-3 erklärenden Sätzen.",
    "Descrição em gerúndio do processo central que o entrevistado tenta resolver continuamente, com 2-3 frases de explicação.",
)
add(
    "Descripción en gerundio del proceso central de ESTE entrevistado.",
    "Descripción en gerundio del proceso central de ESTE entrevistado.",
    "Beschreibung im Gerundium des zentralen Prozesses DIESES Interviewten.",
    "Descrição em gerúndio do processo central DESTE entrevistado.",
)
add(
    "En qué se PARECE al proceso del entrevistado anterior.",
    "En qué se PARECE al proceso del entrevistado anterior.",
    "Worin es dem Prozess des vorherigen Interviewten ÄHNELT.",
    "Em que se ASSEMELHA ao processo do entrevistado anterior.",
)
add(
    "En qué se DIFERENCIA del proceso del entrevistado anterior.",
    "En qué se DIFERENCIA del proceso del entrevistado anterior.",
    "Worin es sich vom Prozess des vorherigen Interviewten UNTERSCHEIDET.",
    "Em que se DIFERENCIA do processo do entrevistado anterior.",
)
add(
    "Hipótesis completa.",
    "Hipótesis completa.",
    "Vollständige Hypothese.",
    "Hipótese completa.",
)
add(
    "Evidencia concreta que la apoya.",
    "Evidencia concreta que la apoya.",
    "Konkrete Belege, die sie stützen.",
    "Evidência concreta que a apoia.",
)
add(
    "Nombre en gerundio.",
    "Nombre en gerundio.",
    "Name im Gerundium.",
    "Nome em gerúndio.",
)

# ── All English descriptions ──────────────────────────────────────
# Short/atomic:
add(
    "0-based index of the segment in the input array.",
    "Índice basado en 0 del segmento en el array de entrada.",
    "0-basierter Index des Segments im Eingabearray.",
    "Índice baseado em 0 do segmento no array de entrada.",
)
add(
    "0-based indices of incidents that support this dimension.",
    "Índices basados en 0 de incidentes que respaldan esta dimensión.",
    "0-basierte Indizes der Vorfälle, die diese Dimension stützen.",
    "Índices baseados em 0 de incidentes que sustentam esta dimensão.",
)
add(
    "0.0-1.0 score of pattern similarity",
    "Puntuación 0.0-1.0 de similitud de patrón",
    "0.0-1.0 Punktzahl der Musterähnlichkeit",
    "Pontuação 0.0-1.0 de similaridade de padrão",
)
add(
    "1-2 sentence justification",
    "Justificación de 1-2 oraciones",
    "1-2 Sätze Begründung",
    "Justificativa de 1-2 frases",
)
add(
    "1-3 sentence definition. What behavioral pattern it captures, not what topic.",
    "Definición de 1-3 oraciones. Qué patrón de comportamiento captura, no qué tema.",
    "1-3 Sätze Definition. Welches Verhaltensmuster es erfasst, nicht welches Thema.",
    "Definição de 1-3 frases. Qual padrão de comportamento captura, não qual tópico.",
)
add(
    "3-6 topic labels",
    "3-6 etiquetas temáticas",
    "3-6 Themenbezeichnungen",
    "3-6 rótulos de tópico",
)
add(
    "A 3–5 sentence narrative of the integrated model: what processes what, under what conditions, via what strategies, producing what consequences.",
    "Narrativa de 3-5 oraciones del modelo integrado: qué procesa qué, bajo qué condiciones, mediante qué estrategias, produciendo qué consecuencias.",
    "Eine 3–5 Sätze umfassende Erzählung des integrierten Modells: was verarbeitet was, unter welchen Bedingungen, über welche Strategien, mit welchen Konsequenzen.",
    "Narrativa de 3-5 frases do modelo integrado: o que processa o quê, sob quais condições, via quais estratégias, produzindo quais consequências.",
)
add(
    "A 3–5 sentence narrative summary of the theoretical model: what the core category processes, under what conditions, using what strategies, producing what consequences, varying along what dimensions.",
    "Resumen narrativo de 3-5 oraciones del modelo teórico: qué procesa la categoría central, bajo qué condiciones, usando qué estrategias, produciendo qué consecuencias, variando en qué dimensiones.",
    "Eine 3–5 Sätze umfassende narrative Zusammenfassung des theoretischen Modells: was die Kernkategorie verarbeitet, unter welchen Bedingungen, mit welchen Strategien, mit welchen Konsequenzen, variierend entlang welcher Dimensionen.",
    "Resumo narrativo de 3-5 frases do modelo teórico: o que a categoria central processa, sob quais condições, usando quais estratégias, produzindo quais consequências, variando ao longo de quais dimensões.",
)
add(
    "Abstraction level of the rename.",
    "Nivel de abstracción del renombre.",
    "Abstraktionsebene der Umbenennung.",
    "Nível de abstração da renomeação.",
)
add(
    "Access variable name.",
    "Nombre de la variable de acceso.",
    "Name der Zugangsvariable.",
    "Nome da variável de acesso.",
)
add(
    "Action decided according to the 3-step protocol.",
    "Acción decidida según el protocolo de 3 pasos.",
    "Aktion gemäß dem 3-stufigen Protokoll entschieden.",
    "Ação decidida de acordo com o protocolo de 3 passos.",
)
add(
    "Affinity score. Only families ≥ 0.3 are included.",
    "Puntuación de afinidad. Solo se incluyen familias ≥ 0.3.",
    "Affinitätswert. Nur Familien ≥ 0.3 werden einbezogen.",
    "Pontuação de afinidade. Apenas famílias ≥ 0.3 são incluídas.",
)
add(
    "All properties inherited from the source category.",
    "Todas las propiedades heredadas de la categoría fuente.",
    "Alle von der Quellkategorie geerbten Eigenschaften.",
    "Todas as propriedades herdadas da categoria fonte.",
)
add(
    "All proposed edges. PROCESSES edge MUST be first in the array.",
    "Todas las aristas propuestas. La arista PROCESSES DEBE ser la primera en el array.",
    "Alle vorgeschlagenen Kanten. Die PROCESSES-Kante MUSS die erste im Array sein.",
    "Todas as arestas propostas. A aresta PROCESSES DEVE ser a primeira no array.",
)
add(
    "Alternative concern.",
    "Preocupación alternativa.",
    "Alternatives Anliegen.",
    "Preocupação alternativa.",
)
add(
    "Alternative gerund pattern name.",
    "Nombre alternativo del patrón en gerundio.",
    "Alternativer Gerundium-Mustername.",
    "Nome alternativo do padrão em gerúndio.",
)
add(
    "Always 'Applicability'.",
    "Siempre 'Aplicabilidad'.",
    "Immer 'Anwendbarkeit'.",
    "Sempre 'Aplicabilidade'.",
)
add(
    "Always 'Core Category' — this is a formal CGT construct, not adapted to object_of_study.",
    "Siempre 'Categoría Central' — es un constructo formal de CGT, no adaptado al objeto de estudio.",
    "Immer 'Kernkategorie' — dies ist ein formales CGT-Konstrukt, nicht an den Untersuchungsgegenstand angepasst.",
    "Sempre 'Categoria Central' — é um construto formal da CGT, não adaptado ao objeto de estudo.",
)
add(
    "Always 'Literature Dialogue'.",
    "Siempre 'Diálogo con la Literatura'.",
    "Immer 'Literaturdialog'.",
    "Sempre 'Diálogo com a Literatura'.",
)
add(
    "Always 'Population Dimensions'.",
    "Siempre 'Dimensiones Poblacionales'.",
    "Immer 'Bevölkerungsdimensionen'.",
    "Sempre 'Dimensões Populacionais'.",
)
add(
    "Always 'Research Trajectory'.",
    "Siempre 'Trayectoria de Investigación'.",
    "Immer 'Forschungsverlauf'.",
    "Sempre 'Trajetória de Pesquisa'.",
)
add(
    "Always 'Theoretical Model'.",
    "Siempre 'Modelo Teórico'.",
    "Immer 'Theoretisches Modell'.",
    "Sempre 'Modelo Teórico'.",
)
add(
    "Antecedent and structural conditions that shape how the core category operates. Causal and contextual conditions from nodes with entity_type 'condition'.",
    "Condiciones antecedentes y estructurales que moldean cómo opera la categoría central. Condiciones causales y contextuales de nodos con entity_type 'condition'.",
    "Vorgelagerte und strukturelle Bedingungen, die prägen, wie die Kernkategorie operiert. Kausale und kontextuelle Bedingungen von Knoten mit entity_type 'condition'.",
    "Condições antecedentes e estruturais que moldam como a categoria central opera. Condições causais e contextuais de nós com entity_type 'condition'.",
)
add(
    "Any problems with the PROCESSES edge.",
    "Cualquier problema con la arista PROCESSES.",
    "Etwaige Probleme mit der PROCESSES-Kante.",
    "Quaisquer problemas com a aresta PROCESSES.",
)
add(
    "Are the incidents interchangeable? How do they differ if they are not? If not enough incidents to evaluate: 'Insufficient incidents to evaluate interchangeability.'",
    "¿Son los incidentes intercambiables? ¿En qué se diferencian si no lo son? Si no hay suficientes incidentes para evaluar: 'Incidentes insuficientes para evaluar intercambiabilidad.'",
    "Sind die Vorfälle austauschbar? Wie unterscheiden sie sich, wenn nicht? Wenn nicht genügend Vorfälle zur Bewertung: 'Unzureichende Vorfälle zur Bewertung der Austauschbarkeit.'",
    "Os incidentes são intercambiáveis? Como diferem se não forem? Se não houver incidentes suficientes para avaliar: 'Incidentes insuficientes para avaliar intercambialidade.'",
)
add(
    "Are they interchangeable?",
    "¿Son intercambiables?",
    "Sind sie austauschbar?",
    "São intercambiáveis?",
)
add(
    "Aspects of the phenomenon that can be modified in practice. Each traces to a theoretical property.",
    "Aspectos del fenómeno que pueden modificarse en la práctica. Cada uno se remonta a una propiedad teórica.",
    "Aspekte des Phänomens, die in der Praxis verändert werden können. Jeder geht auf eine theoretische Eigenschaft zurück.",
    "Aspectos do fenômeno que podem ser modificados na prática. Cada um remonta a uma propriedade teórica.",
)
add(
    "Assessment of each criterion.",
    "Evaluación de cada criterio.",
    "Bewertung jedes Kriteriums.",
    "Avaliação de cada critério.",
)
add(
    "Behavioral and cognitive strategies participants employ. Derived from nodes with entity_type 'strategy' and IS_A_STRATEGY_FOR edges.",
    "Estrategias conductuales y cognitivas que emplean los participantes. Derivadas de nodos con entity_type 'strategy' y aristas IS_A_STRATEGY_FOR.",
    "Verhaltens- und kognitive Strategien, die Teilnehmer anwenden. Abgeleitet von Knoten mit entity_type 'strategy' und IS_A_STRATEGY_FOR-Kanten.",
    "Estratégias comportamentais e cognitivas que os participantes empregam. Derivadas de nós com entity_type 'strategy' e arestas IS_A_STRATEGY_FOR.",
)
add(
    "Behavioral indicators extracted from the segments.",
    "Indicadores de comportamiento extraídos de los segmentos.",
    "Aus den Segmenten extrahierte Verhaltensindikatoren.",
    "Indicadores comportamentais extraídos dos segmentos.",
)
add(
    "Brief description of the common behavioral pattern shared by these incidents (1-2 sentences)",
    "Breve descripción del patrón de comportamiento común compartido por estos incidentes (1-2 oraciones)",
    "Kurze Beschreibung des gemeinsamen Verhaltensmusters dieser Vorfälle (1-2 Sätze)",
    "Breve descrição do padrão de comportamento comum compartilhado por estes incidentes (1-2 frases)",
)
add(
    "Brief justification based on the text",
    "Justificación breve basada en el texto",
    "Kurze Begründung basierend auf dem Text",
    "Justificativa breve baseada no texto",
)
add(
    "Brief justification of the generalization (2-3 sentences)",
    "Justificación breve de la generalización (2-3 oraciones)",
    "Kurze Begründung der Generalisierung (2-3 Sätze)",
    "Justificativa breve da generalização (2-3 frases)",
)
add(
    "CGT paradigm element: dimension (varying property), condition (circumstance), consequence (outcome), strategy (action).",
    "Elemento del paradigma CGT: dimensión (propiedad variable), condición (circunstancia), consecuencia (resultado), estrategia (acción).",
    "CGT-Paradigmaelement: Dimension (variierende Eigenschaft), Bedingung (Umstand), Konsequenz (Ergebnis), Strategie (Handlung).",
    "Elemento do paradigma CGT: dimensão (propriedade variável), condição (circunstância), consequência (resultado), estratégia (ação).",
)
add(
    "Candidate name.",
    "Nombre del candidato.",
    "Name des Kandidaten.",
    "Nome do candidato.",
)
add(
    "Canonical CGT relationship type.",
    "Tipo de relación canónica de CGT.",
    "Kanonischer CGT-Beziehungstyp.",
    "Tipo de relação canônica da CGT.",
)
add(
    "Canonical entity type. Exactly one node must be core_category.",
    "Tipo de entidad canónica. Exactamente un nodo debe ser core_category.",
    "Kanonischer Entitätstyp. Genau ein Knoten muss core_category sein.",
    "Tipo de entidade canônica. Exatamente um nó deve ser core_category.",
)
add(
    "Canonical relationship type from the 7 Glaserian families.",
    "Tipo de relación canónica de las 7 familias glaserianas.",
    "Kanonischer Beziehungstyp aus den 7 Glaser'schen Familien.",
    "Tipo de relação canônica das 7 famílias glaserianas.",
)
add(
    "Category property this incident reveals (e.g., 'high intensity', 'work context').",
    "Propiedad de la categoría que este incidente revela (ej., 'alta intensidad', 'contexto laboral').",
    "Kategorieeigenschaft, die dieser Vorfall offenbart (z.B. 'hohe Intensität', 'Arbeitskontext').",
    "Propriedade da categoria que este incidente revela (ex., 'alta intensidade', 'contexto de trabalho').",
)
add(
    "Circumstances under which the category manifests. Empty array if no conditions are identified.",
    "Circunstancias bajo las cuales se manifiesta la categoría. Array vacío si no se identifican condiciones.",
    "Umstände, unter denen sich die Kategorie manifestiert. Leeres Array, wenn keine Bedingungen identifiziert werden.",
    "Circunstâncias sob as quais a categoria se manifesta. Array vazio se nenhuma condição for identificada.",
)
add("Code label", "Etiqueta del código", "Code-Bezeichnung", "Rótulo do código")
add(
    "Codes generated from the indicators.",
    "Códigos generados a partir de los indicadores.",
    "Aus den Indikatoren generierte Codes.",
    "Códigos gerados a partir dos indicadores.",
)
add(
    "Codes or mechanisms that resolve the problems (Question 2). Empty array if none identified.",
    "Códigos o mecanismos que resuelven los problemas (Pregunta 2). Array vacío si no se identifica ninguno.",
    "Codes oder Mechanismen, die die Probleme lösen (Frage 2). Leeres Array, wenn keine identifiziert.",
    "Códigos ou mecanismos que resolvem os problemas (Questão 2). Array vazio se nenhum identificado.",
)
add(
    "Codes with highest centrality and explanatory power (Question 3). Empty array if none identified.",
    "Códigos con mayor centralidad y poder explicativo (Pregunta 3). Array vacío si no se identifica ninguno.",
    "Codes mit höchster Zentralität und Erklärungskraft (Frage 3). Leeres Array, wenn keine identifiziert.",
    "Códigos com maior centralidade e poder explicativo (Questão 3). Array vazio se nenhum identificado.",
)
add(
    "Complete draft in academic prose",
    "Borrador completo en prosa académica",
    "Vollständiger Entwurf in akademischer Prosa",
    "Rascunho completo em prosa acadêmica",
)
add(
    "Concrete action. E.g.: 'Change OQ from plural to singular: use their concern instead of their concerns', 'Replace population unit classroom with human actors: teachers and students', 'The verb negotiate fits identity type — keep it.'",
    "Acción concreta. Ej.: 'Cambiar OQ de plural a singular: usar su preocupación en lugar de sus preocupaciones', 'Reemplazar unidad poblacional aula por actores humanos: profesores y estudiantes', 'El verbo negociar encaja con el tipo identidad — consérvalo.'",
    "Konkrete Maßnahme. Z.B.: 'OQ von Plural zu Singular ändern: their concern statt their concerns', 'Bevölkerungseinheit Klassenzimmer durch menschliche Akteure ersetzen: Lehrer und Schüler', 'Das Verb negotiate passt zum Identitätstyp — beibehalten.'",
    "Ação concreta. Ex.: 'Mudar OQ de plural para singular: usar sua preocupação em vez de suas preocupações', 'Substituir unidade populacional sala de aula por atores humanos: professores e alunos', 'O verbo negociar se encaixa no tipo identidade — mantê-lo.'",
)
add(
    "Concrete action: refine definition, split into subcodes, or seek more data?",
    "Acción concreta: ¿refinar definición, dividir en subcódigos o buscar más datos?",
    "Konkrete Maßnahme: Definition verfeinern, in Subcodes aufteilen oder mehr Daten suchen?",
    "Ação concreta: refinar definição, dividir em subcódigos ou buscar mais dados?",
)
add(
    "Concrete evidence citing interviewees.",
    "Evidencia concreta citando entrevistados.",
    "Konkrete Belege unter Nennung von Interviewten.",
    "Evidência concreta citando entrevistados.",
)
add(
    "Concrete evidence. Without evidence: do not include.",
    "Evidencia concreta. Sin evidencia: no incluir.",
    "Konkrete Belege. Ohne Belege: nicht aufnehmen.",
    "Evidência concreta. Sem evidência: não incluir.",
)
add(
    "Concrete next studies, populations to sample, comparisons to pursue.",
    "Próximos estudios concretos, poblaciones a muestrear, comparaciones a realizar.",
    "Konkrete nächste Studien, zu untersuchende Bevölkerungen, zu verfolgende Vergleiche.",
    "Próximos estudos concretos, populações a amostrar, comparações a realizar.",
)
add(
    "Concrete question for a theoretical sampling interview.",
    "Pregunta concreta para una entrevista de muestreo teórico.",
    "Konkrete Frage für ein theoretisches Sampling-Interview.",
    "Pergunta concreta para uma entrevista de amostragem teórica.",
)
add(
    "Concrete recommendations for practitioners.",
    "Recomendaciones concretas para profesionales.",
    "Konkrete Empfehlungen für Praktiker.",
    "Recomendações concretas para profissionais.",
)
add(
    "Concrete, actionable suggestions for improvement. Empty array if verdict is SAT. Each suggestion must reference the specific criterion it addresses.",
    "Sugerencias concretas y accionables de mejora. Array vacío si el veredicto es SAT. Cada sugerencia debe referenciar el criterio específico que aborda.",
    "Konkrete, umsetzbare Verbesserungsvorschläge. Leeres Array, wenn das Urteil SAT ist. Jeder Vorschlag muss das spezifische Kriterium nennen, das er adressiert.",
    "Sugestões concretas e acionáveis de melhoria. Array vazio se o veredito for SAT. Cada sugestão deve referenciar o critério específico que aborda.",
)
add(
    "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.",
    "Condiciones de producción de los datos: entorno de entrevista, señales de deseabilidad social, fatiga, dinámicas de poder.",
    "Produktionsbedingungen der Daten: Interviewumgebung, Anzeichen sozialer Erwünschtheit, Ermüdung, Machtdynamiken.",
    "Condições de produção dos dados: ambiente de entrevista, sinais de desejabilidade social, fadiga, dinâmicas de poder.",
)
add(
    "Conditions that enable or constrain intervention.",
    "Condiciones que habilitan o restringen la intervención.",
    "Bedingungen, die Intervention ermöglichen oder einschränken.",
    "Condições que habilitam ou restringem a intervenção.",
)
add(
    "Confidence based on quantity and quality of evidence.",
    "Confianza basada en cantidad y calidad de evidencia.",
    "Vertrauen basierend auf Menge und Qualität der Belege.",
    "Confiança baseada em quantidade e qualidade de evidência.",
)
add(
    "Confidence in the decision",
    "Confianza en la decisión",
    "Vertrauen in die Entscheidung",
    "Confiança na decisão",
)
add(
    "Confidence in the extracted pattern. HIGH: pattern is clear, multiple incidents strongly converge. MEDIUM: pattern is discernible but with notable variation or missing dimensions. LOW: pattern is tentative, few supporting incidents, or contradictory signals.",
    "Confianza en el patrón extraído. HIGH: patrón claro, múltiples incidentes convergen fuertemente. MEDIUM: patrón discernible pero con variación notable o dimensiones faltantes. LOW: patrón tentativo, pocos incidentes de apoyo o señales contradictorias.",
    "Vertrauen in das extrahierte Muster. HIGH: Muster ist klar, mehrere Vorfälle konvergieren stark. MEDIUM: Muster ist erkennbar, aber mit deutlicher Variation oder fehlenden Dimensionen. LOW: Muster ist vorläufig, wenige stützende Vorfälle oder widersprüchliche Signale.",
    "Confiança no padrão extraído. HIGH: padrão claro, múltiplos incidentes convergem fortemente. MEDIUM: padrão discernível mas com variação notável ou dimensões ausentes. LOW: padrão tentativo, poucos incidentes de apoio ou sinais contraditórios.",
)
add(
    "Confidence in the extraction.",
    "Confianza en la extracción.",
    "Vertrauen in die Extraktion.",
    "Confiança na extração.",
)
add(
    "Confidence in the generalization (0.0-1.0)",
    "Confianza en la generalización (0.0-1.0)",
    "Vertrauen in die Generalisierung (0.0-1.0)",
    "Confiança na generalização (0.0-1.0)",
)
add(
    "Confidence in the identified {object_of_study}.",
    "Confianza en el {object_of_study} identificado.",
    "Vertrauen in das identifizierte {object_of_study}.",
    "Confiança no {object_of_study} identificado.",
)
add(
    "Confidence level in the classification.",
    "Nivel de confianza en la clasificación.",
    "Vertrauensniveau in die Klassifikation.",
    "Nível de confiança na classificação.",
)
add(
    "Consolidated categories after clustering. Empty array if no changes are required.",
    "Categorías consolidadas después del agrupamiento. Array vacío si no se requieren cambios.",
    "Konsolidierte Kategorien nach Clustering. Leeres Array, wenn keine Änderungen erforderlich sind.",
    "Categorias consolidadas após agrupamento. Array vazio se nenhuma alteração for necessária.",
)
add(
    "Consolidated definition of the category (Step 3).",
    "Definición consolidada de la categoría (Paso 3).",
    "Konsolidierte Definition der Kategorie (Schritt 3).",
    "Definição consolidada da categoria (Passo 3).",
)
add(
    "Consolidated definition of the code across all documents. More abstract than individual summaries but anchored in the data.",
    "Definición consolidada del código en todos los documentos. Más abstracta que los resúmenes individuales pero anclada en los datos.",
    "Konsolidierte Definition des Codes über alle Dokumente hinweg. Abstrakter als einzelne Zusammenfassungen, aber in den Daten verankert.",
    "Definição consolidada do código em todos os documentos. Mais abstrata que os resumos individuais, mas ancorada nos dados.",
)
add(
    "Control variable name.",
    "Nombre de la variable de control.",
    "Name der Kontrollvariable.",
    "Nome da variável de controle.",
)
add(
    "Core category candidates, ordered by decreasing theoretical_grab",
    "Candidatos a categoría central, ordenados por theoretical_grab decreciente",
    "Kernkategorie-Kandidaten, absteigend nach theoretical_grab geordnet",
    "Candidatos a categoria central, ordenados por theoretical_grab decrescente",
)
add(
    "Core pattern expressed as a gerund.",
    "Patrón central expresado como gerundio.",
    "Kernmuster als Gerundium ausgedrückt.",
    "Padrão central expresso como gerúndio.",
)
add(
    "Core {object_of_study} expressed as a gerund or verb phrase.",
    "{object_of_study} central expresado como gerundio o frase verbal.",
    "Kern-{object_of_study} als Gerundium oder Verbalphrase ausgedrückt.",
    "{object_of_study} central expresso como gerúndio ou frase verbal.",
)
add("Corrected text.", "Texto corregido.", "Korrigierter Text.", "Texto corrigido.")
add(
    "Count per entity_type.",
    "Conteo por entity_type.",
    "Anzahl pro entity_type.",
    "Contagem por entity_type.",
)
add(
    "Count per relationship_type.",
    "Conteo por relationship_type.",
    "Anzahl pro relationship_type.",
    "Contagem por relationship_type.",
)
add(
    "Critic's confidence in this verdict (0.0–1.0).",
    "Confianza del crítico en este veredicto (0.0–1.0).",
    "Vertrauen des Kritikers in dieses Urteil (0.0–1.0).",
    "Confiança do crítico neste veredito (0.0–1.0).",
)
add(
    "Critic's confidence in this verdict. 0.0 = total doubt, 1.0 = absolute certainty.",
    "Confianza del crítico en este veredicto. 0.0 = duda total, 1.0 = certeza absoluta.",
    "Vertrauen des Kritikers in dieses Urteil. 0.0 = völliger Zweifel, 1.0 = absolute Gewissheit.",
    "Confiança do crítico neste veredito. 0.0 = dúvida total, 1.0 = certeza absoluta.",
)
add(
    "Current label of the code",
    "Etiqueta actual del código",
    "Aktuelle Bezeichnung des Codes",
    "Rótulo atual do código",
)
add(
    "Definition of the new category.",
    "Definición de la nueva categoría.",
    "Definition der neuen Kategorie.",
    "Definição da nova categoria.",
)
add(
    "Definition: what behavioral pattern it captures, in 1-2 sentences.",
    "Definición: qué patrón de comportamiento captura, en 1-2 oraciones.",
    "Definition: welches Verhaltensmuster es erfasst, in 1-2 Sätzen.",
    "Definição: qual padrão de comportamento captura, em 1-2 frases.",
)
add(
    "Definition: what behavioral pattern it captures. 2-4 sentences.",
    "Definición: qué patrón de comportamiento captura. 2-4 oraciones.",
    "Definition: welches Verhaltensmuster es erfasst. 2-4 Sätze.",
    "Definição: qual padrão de comportamento captura. 2-4 frases.",
)
add(
    "Description of the circumstance.",
    "Descripción de la circunstancia.",
    "Beschreibung des Umstands.",
    "Descrição da circunstância.",
)
add(
    "Description of the expansion: what it adds to the current paradigm_state",
    "Descripción de la expansión: qué añade al paradigm_state actual",
    "Beschreibung der Erweiterung: was sie zum aktuellen paradigm_state hinzufügt",
    "Descrição da expansão: o que adiciona ao paradigm_state atual",
)
add(
    "Description of the issue. If MOD, include a concrete suggestion.",
    "Descripción del problema. Si MOD, incluir una sugerencia concreta.",
    "Beschreibung des Problems. Bei MOD einen konkreten Vorschlag einfügen.",
    "Descrição do problema. Se MOD, incluir uma sugestão concreta.",
)
add(
    "Description of the observed action pattern. No gerund. No theoretical jargon.",
    "Descripción del patrón de acción observado. Sin gerundio. Sin jerga teórica.",
    "Beschreibung des beobachteten Handlungsmusters. Kein Gerundium. Kein theoretischer Jargon.",
    "Descrição do padrão de ação observado. Sem gerúndio. Sem jargão teórico.",
)
add(
    "Description of the population concern (e.g., 'Pattern suggests two distinct sub-populations with different processing strategies', 'Assumed population too broad — patterns diverge along age/experience axis').",
    "Descripción de la preocupación poblacional (ej., 'El patrón sugiere dos subpoblaciones distintas con diferentes estrategias de procesamiento', 'Población asumida demasiado amplia — los patrones divergen según el eje edad/experiencia').",
    "Beschreibung des Bevölkerungsanliegens (z.B. 'Muster deutet auf zwei unterschiedliche Subpopulationen mit verschiedenen Verarbeitungsstrategien hin', 'Angenommene Bevölkerung zu breit — Muster divergieren entlang der Achse Alter/Erfahrung').",
    "Descrição da preocupação populacional (ex., 'Padrão sugere duas subpopulações distintas com diferentes estratégias de processamento', 'População assumida muito ampla — padrões divergem ao longo do eixo idade/experiência').",
)
add(
    "Description of the variation.",
    "Descripción de la variación.",
    "Beschreibung der Variation.",
    "Descrição da variação.",
)
add(
    "Detail of the suggested action: what to split, how to refine, or why to keep. Empty string if not applicable.",
    "Detalle de la acción sugerida: qué dividir, cómo refinar o por qué conservar. String vacío si no aplica.",
    "Detail der vorgeschlagenen Maßnahme: was aufteilen, wie verfeinern oder warum beibehalten. Leerer String, falls nicht zutreffend.",
    "Detalhe da ação sugerida: o que dividir, como refinar ou por que manter. String vazia se não aplicável.",
)
add(
    "Detailed explanation of HOW this element diverges and WHY it is classified as surface/contextual/fundamental. Reference specific patterns.",
    "Explicación detallada de CÓMO este elemento diverge y POR QUÉ se clasifica como superficial/contextual/fundamental. Referenciar patrones específicos.",
    "Detaillierte Erklärung, WIE dieses Element divergiert und WARUM es als oberflächlich/kontextuell/grundlegend klassifiziert wird. Auf spezifische Muster verweisen.",
    "Explicação detalhada de COMO este elemento diverge e POR QUE é classificado como superficial/contextual/fundamental. Referenciar padrões específicos.",
)
add(
    "Detailed justification of the verdict, citing specific codes and memos.",
    "Justificación detallada del veredicto, citando códigos y memos específicos.",
    "Detaillierte Begründung des Urteils unter Nennung spezifischer Codes und Memos.",
    "Justificativa detalhada do veredito, citando códigos e memos específicos.",
)
add(
    "Detailed justification of the verdict, referencing specific segments.",
    "Justificación detallada del veredicto, referenciando segmentos específicos.",
    "Detaillierte Begründung des Urteils unter Bezugnahme auf bestimmte Segmente.",
    "Justificativa detalhada do veredito, referenciando segmentos específicos.",
)
add(
    "Detailed rationale for the recommendation. Explain why this recommendation follows from the convergence/divergence analysis. If READY_FOR_CROSS_DOC, explain what makes the convergence strong enough. If NEEDS_DIFFERENT_POPULATION, explain what sampling changes would help.",
    "Justificación detallada de la recomendación. Explicar por qué esta recomendación se deriva del análisis de convergencia/divergencia. Si READY_FOR_CROSS_DOC, explicar qué hace que la convergencia sea suficientemente fuerte. Si NEEDS_DIFFERENT_POPULATION, explicar qué cambios de muestreo ayudarían.",
    "Detaillierte Begründung der Empfehlung. Erklären, warum diese Empfehlung aus der Konvergenz/Divergenz-Analyse folgt. Bei READY_FOR_CROSS_DOC: erklären, was die Konvergenz stark genug macht. Bei NEEDS_DIFFERENT_POPULATION: erklären, welche Stichprobenänderungen helfen würden.",
    "Justificativa detalhada da recomendação. Explicar por que esta recomendação decorre da análise de convergência/divergência. Se READY_FOR_CROSS_DOC, explicar o que torna a convergência forte o suficiente. Se NEEDS_DIFFERENT_POPULATION, explicar quais mudanças de amostragem ajudariam.",
)
add(
    "Detailed reasoning: essences extracted from each incident, comparison, and justification of the verdict.",
    "Razonamiento detallado: esencias extraídas de cada incidente, comparación y justificación del veredicto.",
    "Detaillierte Begründung: aus jedem Vorfall extrahierte Essenzen, Vergleich und Begründung des Urteils.",
    "Raciocínio detalhado: essências extraídas de cada incidente, comparação e justificativa do veredito.",
)
add(
    "Detected theoretical gaps. May be empty if the draft is structurally sound.",
    "Vacíos teóricos detectados. Puede estar vacío si el borrador es estructuralmente sólido.",
    "Erkannte theoretische Lücken. Kann leer sein, wenn der Entwurf strukturell solide ist.",
    "Lacunas teóricas detectadas. Pode estar vazio se o rascunho for estruturalmente sólido.",
)
add(
    "Dimensions of variation (how the phenomenon changes according to context, intensity, etc.).",
    "Dimensiones de variación (cómo cambia el fenómeno según contexto, intensidad, etc.).",
    "Variationsdimensionen (wie sich das Phänomen je nach Kontext, Intensität usw. verändert).",
    "Dimensões de variação (como o fenômeno muda de acordo com contexto, intensidade, etc.).",
)
add(
    "Dimensions of variation supported by the data.",
    "Dimensiones de variación respaldadas por los datos.",
    "Durch die Daten gestützte Variationsdimensionen.",
    "Dimensões de variação sustentadas pelos dados.",
)
add(
    "Direction of the relationship. 'conceptual' only for PROCESSES edge.",
    "Dirección de la relación. 'conceptual' solo para la arista PROCESSES.",
    "Richtung der Beziehung. 'conceptual' nur für PROCESSES-Kante.",
    "Direção da relação. 'conceptual' apenas para a aresta PROCESSES.",
)
add(
    "Discard category",
    "Categoría de descarte",
    "Verwerfungskategorie",
    "Categoria de descarte",
)
add(
    "Do the supporting_codes actually support this candidate? Evaluate each cited code.",
    "¿Los supporting_codes realmente respaldan a este candidato? Evaluar cada código citado.",
    "Stützen die supporting_codes diesen Kandidaten tatsächlich? Jeden zitierten Code bewerten.",
    "Os supporting_codes realmente sustentam este candidato? Avaliar cada código citado.",
)
add(
    "Documented internal variations. Empty array if the category is uniform.",
    "Variaciones internas documentadas. Array vacío si la categoría es uniforme.",
    "Dokumentierte interne Variationen. Leeres Array, wenn die Kategorie einheitlich ist.",
    "Variações internas documentadas. Array vazio se a categoria for uniforme.",
)
add(
    "Documents with both categories but without clear evidence.",
    "Documentos con ambas categorías pero sin evidencia clara.",
    "Dokumente mit beiden Kategorien, aber ohne klare Belege.",
    "Documentos com ambas as categorias mas sem evidência clara.",
)
add(
    "Does a PROCESSES edge exist?",
    "¿Existe una arista PROCESSES?",
    "Existiert eine PROCESSES-Kante?",
    "Existe uma aresta PROCESSES?",
)
add(
    "Does the rationale convincingly explain why this is the central mechanism?",
    "¿La justificación explica convincentemente por qué este es el mecanismo central?",
    "Erklärt die Begründung überzeugend, warum dies der zentrale Mechanismus ist?",
    "A justificativa explica convincentemente por que este é o mecanismo central?",
)
add(
    "Does the target correctly describe the {object_of_study}?",
    "¿El objetivo describe correctamente el {object_of_study}?",
    "Beschreibt das Ziel das {object_of_study} korrekt?",
    "O alvo descreve corretamente o {object_of_study}?",
)
add(
    "Does this incident confirm the known extreme, push it further, or reveal a new extreme?",
    "¿Este incidente confirma el extremo conocido, lo empuja más allá o revela un nuevo extremo?",
    "Bestätigt dieser Vorfall das bekannte Extrem, treibt er es weiter oder offenbart er ein neues Extrem?",
    "Este incidente confirma o extremo conhecido, o empurra além ou revela um novo extremo?",
)
add(
    "Elements that diverge across the 3 patterns. What differs, conflicts, or pulls in different directions?",
    "Elementos que divergen entre los 3 patrones. ¿Qué difiere, conflictúa o tira en direcciones diferentes?",
    "Elemente, die über die 3 Muster hinweg divergieren. Was unterscheidet sich, steht im Konflikt oder zieht in verschiedene Richtungen?",
    "Elementos que divergem entre os 3 padrões. O que difere, conflita ou puxa em direções diferentes?",
)
add(
    "Elements that show convergence across the 3 patterns. What is consistent, shared, or mutually reinforcing?",
    "Elementos que muestran convergencia entre los 3 patrones. ¿Qué es consistente, compartido o mutuamente reforzante?",
    "Elemente, die Konvergenz über die 3 Muster hinweg zeigen. Was ist konsistent, gemeinsam oder sich gegenseitig verstärkend?",
    "Elementos que mostram convergência entre os 3 padrões. O que é consistente, compartilhado ou mutuamente reforçador?",
)
add(
    "Emergent properties of the pattern with their dimensions",
    "Propiedades emergentes del patrón con sus dimensiones",
    "Emergente Eigenschaften des Musters mit ihren Dimensionen",
    "Propriedades emergentes do padrão com suas dimensões",
)
add(
    "En qué se DIFERENCIA del proceso del entrevistado anterior.",
    "En qué se DIFERENCIA del proceso del entrevistado anterior.",
    "Worin es sich vom Prozess des vorherigen Interviewten UNTERSCHEIDET.",
    "Em que se DIFERENCIA do processo do entrevistado anterior.",
)
add(
    "En qué se PARECE al proceso del entrevistado anterior.",
    "En qué se PARECE al proceso del entrevistado anterior.",
    "Worin es dem Prozess des vorherigen Interviewten ÄHNELT.",
    "Em que se ASSEMELHA ao processo do entrevistado anterior.",
)
add(
    "Essence of incident 1: behavioral pattern abstracted from its specific context.",
    "Esencia del incidente 1: patrón de comportamiento abstraído de su contexto específico.",
    "Essenz von Vorfall 1: aus seinem spezifischen Kontext abstrahiertes Verhaltensmuster.",
    "Essência do incidente 1: padrão de comportamento abstraído de seu contexto específico.",
)
add(
    "Essence of incident 2.",
    "Esencia del incidente 2.",
    "Essenz von Vorfall 2.",
    "Essência do incidente 2.",
)
add(
    "Essence of incident 3. Empty string if no third incident was provided.",
    "Esencia del incidente 3. String vacío si no se proporcionó un tercer incidente.",
    "Essenz von Vorfall 3. Leerer String, wenn kein dritter Vorfall bereitgestellt wurde.",
    "Essência do incidente 3. String vazia se nenhum terceiro incidente foi fornecido.",
)
add(
    "Evaluation for each proposed edge.",
    "Evaluación para cada arista propuesta.",
    "Bewertung für jede vorgeschlagene Kante.",
    "Avaliação para cada aresta proposta.",
)
add(
    "Evaluation for each proposed node.",
    "Evaluación para cada nodo propuesto.",
    "Bewertung für jeden vorgeschlagenen Knoten.",
    "Avaliação para cada nó proposto.",
)
add(
    "Evaluation of the abstraction level.",
    "Evaluación del nivel de abstracción.",
    "Bewertung des Abstraktionsniveaus.",
    "Avaliação do nível de abstração.",
)
add(
    "Evaluations of each proposed code. Empty array if no codes to evaluate.",
    "Evaluaciones de cada código propuesto. Array vacío si no hay códigos que evaluar.",
    "Bewertungen jedes vorgeschlagenen Codes. Leeres Array, wenn keine Codes zu bewerten sind.",
    "Avaliações de cada código proposto. Array vazio se não houver códigos para avaliar.",
)
add(
    "Evidence quality: strong (multiple converging sources), moderate (one solid source), weak (suggestive).",
    "Calidad de evidencia: fuerte (múltiples fuentes convergentes), moderada (una fuente sólida), débil (sugestiva).",
    "Belegqualität: stark (mehrere konvergierende Quellen), mäßig (eine solide Quelle), schwach (andeutend).",
    "Qualidade da evidência: forte (múltiplas fontes convergentes), moderada (uma fonte sólida), fraca (sugestiva).",
)
add(
    "Evidencia concreta que la apoya.",
    "Evidencia concreta que la apoya.",
    "Konkrete Belege, die sie stützen.",
    "Evidência concreta que a apoia.",
)
add(
    "Exact name of the source entity",
    "Nombre exacto de la entidad fuente",
    "Exakter Name der Quellentität",
    "Nome exato da entidade fonte",
)
add(
    "Exact name of the target entity",
    "Nombre exacto de la entidad destino",
    "Exakter Name der Zielentität",
    "Nome exato da entidade destino",
)
add(
    "Exact textual quote from the incident supporting this expansion",
    "Cita textual exacta del incidente que respalda esta expansión",
    "Exaktes Textzitat aus dem Vorfall, das diese Erweiterung stützt",
    "Citação textual exata do incidente que sustenta esta expansão",
)
add(
    "Exact verbatim phrases that reveal the behavior.",
    "Frases textuales exactas que revelan el comportamiento.",
    "Exakte wörtliche Phrasen, die das Verhalten offenbaren.",
    "Frases textuais exatas que revelam o comportamento.",
)
add(
    "Exact verbatim quote from the document. Do not paraphrase. Between 10 and 300 words.",
    "Cita textual exacta del documento. No parafrasear. Entre 10 y 300 palabras.",
    "Exaktes wörtliches Zitat aus dem Dokument. Nicht paraphrasieren. Zwischen 10 und 300 Wörtern.",
    "Citação textual exata do documento. Não parafrasear. Entre 10 e 300 palavras.",
)
add(
    "Exact verbatim quote from the segment. Do not paraphrase.",
    "Cita textual exacta del segmento. No parafrasear.",
    "Exaktes wörtliches Zitat aus dem Segment. Nicht paraphrasieren.",
    "Citação textual exata do segmento. Não parafrasear.",
)
add(
    "Exact verbatim quote.",
    "Cita textual exacta.",
    "Exaktes wörtliches Zitat.",
    "Citação textual exata.",
)
add(
    "Exact verbatim quotes from the incidents that best support the pattern. Minimum 2, maximum 5. Each quote MUST come from a DISTINCT incident.",
    "Citas textuales exactas de los incidentes que mejor respaldan el patrón. Mínimo 2, máximo 5. Cada cita DEBE provenir de un incidente DISTINTO.",
    "Exakte wörtliche Zitate aus den Vorfällen, die das Muster am besten stützen. Mindestens 2, maximal 5. Jedes Zitat MUSS aus einem EINDEUTIGEN Vorfall stammen.",
    "Citações textuais exatas dos incidentes que melhor sustentam o padrão. Mínimo 2, máximo 5. Cada citação DEVE vir de um incidente DISTINTO.",
)
add(
    "Exclusion criteria.",
    "Criterios de exclusión.",
    "Ausschlusskriterien.",
    "Critérios de exclusão.",
)
add(
    "Executive summary of 3-5 sentences",
    "Resumen ejecutivo de 3-5 oraciones",
    "Zusammenfassung von 3-5 Sätzen",
    "Resumo executivo de 3-5 frases",
)
add(
    "Explanation in 1-2 sentences",
    "Explicación en 1-2 oraciones",
    "Erklärung in 1-2 Sätzen",
    "Explicação em 1-2 frases",
)
add(
    "Explanation in 2-3 sentences",
    "Explicación en 2-3 oraciones",
    "Erklärung in 2-3 Sätzen",
    "Explicação em 2-3 frases",
)
add(
    "Explanatory and unifying power of the candidate",
    "Poder explicativo y unificador del candidato",
    "Erklärungs- und Vereinheitlichungskraft des Kandidaten",
    "Poder explicativo e unificador do candidato",
)
add(
    "Families with score ≥ 0.3, ordered by score descending.",
    "Familias con puntuación ≥ 0.3, ordenadas por puntuación descendente.",
    "Familien mit Punktzahl ≥ 0.3, absteigend nach Punktzahl geordnet.",
    "Famílias com pontuação ≥ 0.3, ordenadas por pontuação decrescente.",
)
add(
    "Family with the highest affinity score.",
    "Familia con la puntuación de afinidad más alta.",
    "Familie mit der höchsten Affinitätspunktzahl.",
    "Família com a pontuação de afinidade mais alta.",
)
add(
    "Family with the second-highest affinity score. Only present if that score ≥ 0.3.",
    "Familia con la segunda puntuación de afinidad más alta. Solo presente si esa puntuación ≥ 0.3.",
    "Familie mit der zweithöchsten Affinitätspunktzahl. Nur vorhanden, wenn diese Punktzahl ≥ 0.3.",
    "Família com a segunda pontuação de afinidade mais alta. Apenas presente se essa pontuação ≥ 0.3.",
)
add(
    "Final name of the code.",
    "Nombre final del código.",
    "Endgültiger Name des Codes.",
    "Nome final do código.",
)
add(
    "Final recommendation: which {object_of_study} candidate do you recommend to the researcher and why? If none is SAT, explain what is missing.",
    "Recomendación final: ¿qué candidato a {object_of_study} recomiendas al investigador y por qué? Si ninguno es SAT, explicar qué falta.",
    "Abschließende Empfehlung: Welchen {object_of_study}-Kandidaten empfehlen Sie dem Forscher und warum? Wenn keiner SAT ist, erklären, was fehlt.",
    "Recomendação final: qual candidato a {object_of_study} você recomenda ao pesquisador e por quê? Se nenhum for SAT, explicar o que está faltando.",
)
add(
    "First 200 words of the segment, verbatim.",
    "Primeras 200 palabras del segmento, textuales.",
    "Erste 200 Wörter des Segments, wörtlich.",
    "Primeiras 200 palavras do segmento, textuais.",
)
add(
    "Flat list of all theoretical nodes. Exactly one node has is_core=true.",
    "Lista plana de todos los nodos teóricos. Exactamente un nodo tiene is_core=true.",
    "Flache Liste aller theoretischen Knoten. Genau ein Knoten hat is_core=true.",
    "Lista plana de todos os nós teóricos. Exatamente um nó tem is_core=true.",
)
add(
    "Formal CGT research question for the human investigator. Follows the structure: 'What is the [pattern] of [population] and how do they continuously [processing_verb] it?' Singular, formal, process-oriented, references spatial and temporal frames.",
    "Pregunta de investigación CGT formal para el investigador humano. Sigue la estructura: '¿Cuál es el [patrón] de [población] y cómo lo [verbo de procesamiento] continuamente?' Singular, formal, orientada al proceso, referencia marcos espaciales y temporales.",
    "Formale CGT-Forschungsfrage für den menschlichen Forscher. Folgt der Struktur: 'Was ist das [Muster] der [Bevölkerung] und wie [Verarbeitungsverb] sie es kontinuierlich?' Singular, formal, prozessorientiert, verweist auf räumliche und zeitliche Rahmen.",
    "Pergunta de pesquisa CGT formal para o investigador humano. Segue a estrutura: 'Qual é o [padrão] da [população] e como eles continuamente o [verbo de processamento]?' Singular, formal, orientada ao processo, referencia quadros espaciais e temporais.",
)
add(
    "Free note from the elaborator: what does this incident reveal about the category? What questions remain open?",
    "Nota libre del elaborador: ¿qué revela este incidente sobre la categoría? ¿Qué preguntas quedan abiertas?",
    "Freie Notiz des Elaborators: Was offenbart dieser Vorfall über die Kategorie? Welche Fragen bleiben offen?",
    "Nota livre do elaborador: o que este incidente revela sobre a categoria? Que perguntas permanecem abertas?",
)
add(
    "Free note: what insight emerged? What remains to be explored?",
    "Nota libre: ¿qué insight emergió? ¿Qué queda por explorar?",
    "Freie Notiz: Welche Einsicht entstand? Was bleibt zu erforschen?",
    "Nota livre: que insight emergiu? O que resta explorar?",
)
add(
    "Full report title: '{Core Pattern} — A Classic Grounded Theory of {Generalized Population}'",
    "Título completo del informe: '{Patrón Central} — Una Teoría Fundamentada Clásica de {Población Generalizada}'",
    "Vollständiger Berichtstitel: '{Kernmuster} — Eine klassische Grounded Theory der {Generalisierten Bevölkerung}'",
    "Título completo do relatório: '{Padrão Central} — Uma Teoria Fundamentada Clássica de {População Generalizada}'",
)
add(
    "Gap classification from the five canonical types.",
    "Clasificación de vacío de los cinco tipos canónicos.",
    "Lückenklassifikation aus den fünf kanonischen Typen.",
    "Classificação de lacuna dos cinco tipos canônicos.",
)
add(
    "Generalized population with theoretical scope. 1-2 sentences.",
    "Población generalizada con alcance teórico. 1-2 oraciones.",
    "Generalisierte Bevölkerung mit theoretischem Geltungsbereich. 1-2 Sätze.",
    "População generalizada com escopo teórico. 1-2 frases.",
)
add(
    "Gerund (verb phrase ending in -ing, 2-6 words) that names the single core pattern synthesizing all incidents in this document. Must capture the essence of what the participant is repeatedly {processing_gerund}. Examples: 'Negotiating permanence on the platform', 'Balancing risk and visibility', 'Defending professional status'.",
    "Gerundio (frase verbal terminada en -ando/-iendo, 2-6 palabras) que nombra el único patrón central que sintetiza todos los incidentes de este documento. Debe capturar la esencia de lo que el participante está {processing_gerund} repetidamente. Ejemplos: 'Negociando permanencia en la plataforma', 'Equilibrando riesgo y visibilidad', 'Defendiendo estatus profesional'.",
    "Gerundium (Verbphrase mit -end, 2-6 Wörter), das das einzige Kernmuster benennt, das alle Vorfälle in diesem Dokument synthetisiert. Muss die Essenz dessen erfassen, was der Teilnehmer wiederholt {processing_gerund}. Beispiele: 'Verhandeln von Beständigkeit auf der Plattform', 'Abwägen von Risiko und Sichtbarkeit', 'Verteidigen des beruflichen Status'.",
    "Gerúndio (frase verbal de 2-6 palavras) que nomeia o único padrão central sintetizando todos os incidentes neste documento. Deve capturar a essência do que o participante está repetidamente {processing_gerund}. Exemplos: 'Negociando permanência na plataforma', 'Equilibrando risco e visibilidade', 'Defendendo status profissional'.",
)
add(
    "Gerund naming the behavioral pattern",
    "Gerundio que nombra el patrón de comportamiento",
    "Gerundium, das das Verhaltensmuster benennt",
    "Gerúndio que nomeia o padrão de comportamento",
)
add(
    "Gerund of the code.",
    "Gerundio del código.",
    "Gerundium des Codes.",
    "Gerúndio do código.",
)
add(
    "Gerund of the consolidated group.",
    "Gerundio del grupo consolidado.",
    "Gerundium der konsolidierten Gruppe.",
    "Gerúndio do grupo consolidado.",
)
add(
    "Gerund of the grouped construct.",
    "Gerundio del constructo agrupado.",
    "Gerundium des gruppierten Konstrukts.",
    "Gerúndio do construto agrupado.",
)
add(
    "Gerund of the higher-order concept (if merger) or original label (if kept alone)",
    "Gerundio del concepto de orden superior (si fusión) o etiqueta original (si se mantiene solo)",
    "Gerundium des übergeordneten Konzepts (bei Fusion) oder ursprüngliche Bezeichnung (wenn allein behalten)",
    "Gerúndio do conceito de ordem superior (se fusão) ou rótulo original (se mantido sozinho)",
)
add(
    "Gerund of the new category.",
    "Gerundio de la nueva categoría.",
    "Gerundium der neuen Kategorie.",
    "Gerúndio da nova categoria.",
)
add(
    "Gerund or conceptual noun. The formal name of this theoretical node.",
    "Gerundio o sustantivo conceptual. El nombre formal de este nodo teórico.",
    "Gerundium oder konzeptuelles Nomen. Der formale Name dieses theoretischen Knotens.",
    "Gerúndio ou substantivo conceitual. O nome formal deste nó teórico.",
)
add(
    "Global assessment of the reduced system: is it methodologically sound? What is missing?",
    "Evaluación global del sistema reducido: ¿es metodológicamente sólido? ¿Qué falta?",
    "Globale Bewertung des reduzierten Systems: Ist es methodisch solide? Was fehlt?",
    "Avaliação global do sistema reduzido: é metodologicamente sólido? O que está faltando?",
)
add(
    "Global assessment: does the theory dialogue with the literature or is it forced to fit?",
    "Evaluación global: ¿la teoría dialoga con la literatura o se fuerza a encajar?",
    "Globale Bewertung: Dialogisiert die Theorie mit der Literatur oder wird sie gewaltsam angepasst?",
    "Avaliação global: a teoria dialoga com a literatura ou é forçada a se encaixar?",
)
add(
    "Global assessment: what is solid? What needs attention? Is the integrated model coherent?",
    "Evaluación global: ¿qué es sólido? ¿Qué necesita atención? ¿Es coherente el modelo integrado?",
    "Globale Bewertung: Was ist solide? Was braucht Aufmerksamkeit? Ist das integrierte Modell kohärent?",
    "Avaliação global: o que é sólido? O que precisa de atenção? O modelo integrado é coerente?",
)
add(
    "Global assessment: what is solid? What needs attention? Is the system ready for edge modeling?",
    "Evaluación global: ¿qué es sólido? ¿Qué necesita atención? ¿Está el sistema listo para el modelado de aristas?",
    "Globale Bewertung: Was ist solide? Was braucht Aufmerksamkeit? Ist das System bereit für die Kantenmodellierung?",
    "Avaliação global: o que é sólido? O que precisa de atenção? O sistema está pronto para modelagem de arestas?",
)
add(
    "Global evaluation: does the theory genuinely dialogue with literature, or is it forced to fit? Candid assessment.",
    "Evaluación global: ¿la teoría dialoga genuinamente con la literatura o se fuerza a encajar? Evaluación sincera.",
    "Globale Bewertung: Dialogisiert die Theorie tatsächlich mit der Literatur oder wird sie gewaltsam angepasst? Ehrliche Einschätzung.",
    "Avaliação global: a teoria dialoga genuinamente com a literatura ou é forçada a se encaixar? Avaliação sincera.",
)
add(
    "Group index (0-based) in the input array",
    "Índice del grupo (basado en 0) en el array de entrada",
    "Gruppenindex (0-basiert) im Eingabearray",
    "Índice do grupo (baseado em 0) no array de entrada",
)
add(
    "Groups of interchangeable incidents. Each group contains incidents that measure the same phenomenon.",
    "Grupos de incidentes intercambiables. Cada grupo contiene incidentes que miden el mismo fenómeno.",
    "Gruppen austauschbarer Vorfälle. Jede Gruppe enthält Vorfälle, die dasselbe Phänomen messen.",
    "Grupos de incidentes intercambiáveis. Cada grupo contém incidentes que medem o mesmo fenômeno.",
)
add(
    "Groups where the pattern is unclear or labeling would be forced.",
    "Grupos donde el patrón no es claro o el etiquetado sería forzado.",
    "Gruppen, bei denen das Muster unklar ist oder die Bezeichnung erzwungen wäre.",
    "Grupos onde o padrão não é claro ou a rotulagem seria forçada.",
)
add(
    "Higher-order constructs resulting from the grouping.",
    "Constructos de orden superior resultantes del agrupamiento.",
    "Übergeordnete Konstrukte, die aus der Gruppierung resultieren.",
    "Construtos de ordem superior resultantes do agrupamento.",
)
add(
    "Hipótesis completa.",
    "Hipótesis completa.",
    "Vollständige Hypothese.",
    "Hipótese completa.",
)
add(
    "How I will know this step found what it was looking for",
    "Cómo sabré que este paso encontró lo que buscaba",
    "Wie ich erkennen werde, dass dieser Schritt gefunden hat, wonach er suchte",
    "Como saberei que este passo encontrou o que procurava",
)
add(
    "How clearly it manifests the property at the sought extreme. 0=none, 1=unequivocally.",
    "Con qué claridad manifiesta la propiedad en el extremo buscado. 0=ninguna, 1=inequívocamente.",
    "Wie deutlich es die Eigenschaft am gesuchten Extrem manifestiert. 0=keine, 1=eindeutig.",
    "Com que clareza manifesta a propriedade no extremo buscado. 0=nenhuma, 1=inequivocamente.",
)
add(
    "How it DIFFERS from the previous one. If it is the first interviewee: 'N/A — first interviewee'.",
    "En qué se DIFERENCIA del anterior. Si es el primer entrevistado: 'N/A — primer entrevistado'.",
    "Worin es sich vom vorherigen UNTERSCHEIDET. Beim ersten Interviewten: 'N/A — erster Interviewter'.",
    "Em que DIFERE do anterior. Se for o primeiro entrevistado: 'N/A — primeiro entrevistado'.",
)
add(
    "How it is SIMILAR to the previous one. If it is the first interviewee: 'N/A — first interviewee'.",
    "En qué es SIMILAR al anterior. Si es el primer entrevistado: 'N/A — primer entrevistado'.",
    "Worin es dem vorherigen ÄHNLICH ist. Beim ersten Interviewten: 'N/A — erster Interviewter'.",
    "Em que é SEMELHANTE ao anterior. Se for o primeiro entrevistado: 'N/A — primeiro entrevistado'.",
)
add(
    "How many expansions were FORCED (already covered — confirming saturation)",
    "Cuántas expansiones fueron FORCED (ya cubiertas — confirmando saturación)",
    "Wie viele Erweiterungen FORCED waren (bereits abgedeckt — Sättigung bestätigend)",
    "Quantas expansões foram FORCED (já cobertas — confirmando saturação)",
)
add(
    "How many expansions were SAT (genuinely new)",
    "Cuántas expansiones fueron SAT (genuinamente nuevas)",
    "Wie viele Erweiterungen SAT waren (wirklich neu)",
    "Quantas expansões foram SAT (genuinamente novas)",
)
add(
    "How many nodes have at least one edge.",
    "Cuántos nodos tienen al menos una arista.",
    "Wie viele Knoten mindestens eine Kante haben.",
    "Quantos nós têm pelo menos uma aresta.",
)
add(
    "How strongly this element converges. STRONG: all 3 patterns align. MODERATE: 2 of 3 align. WEAK: only 1 pattern shows this element but it is notable.",
    "Con qué fuerza converge este elemento. STRONG: los 3 patrones se alinean. MODERATE: 2 de 3 se alinean. WEAK: solo 1 patrón muestra este elemento pero es notable.",
    "Wie stark dieses Element konvergiert. STRONG: alle 3 Muster stimmen überein. MODERATE: 2 von 3 stimmen überein. WEAK: nur 1 Muster zeigt dieses Element, aber es ist bemerkenswert.",
    "Com que força este elemento converge. STRONG: todos os 3 padrões se alinham. MODERATE: 2 de 3 se alinham. WEAK: apenas 1 padrão mostra este elemento, mas é notável.",
)
add(
    "How the core pattern and core category manifest differently across population dimensions. Document the range of variation, not just central tendency.",
    "Cómo el patrón central y la categoría central se manifiestan de manera diferente a través de las dimensiones poblacionales. Documentar el rango de variación, no solo la tendencia central.",
    "Wie sich das Kernmuster und die Kernkategorie über Bevölkerungsdimensionen hinweg unterschiedlich manifestieren. Die Variationsbreite dokumentieren, nicht nur die zentrale Tendenz.",
    "Como o padrão central e a categoria central se manifestam diferentemente através das dimensões populacionais. Documentar a faixa de variação, não apenas a tendência central.",
)
add(
    "How the guideline produces change, traced to a theoretical mechanism.",
    "Cómo la directriz produce cambio, trazado a un mecanismo teórico.",
    "Wie die Richtlinie Veränderung bewirkt, zurückgeführt auf einen theoretischen Mechanismus.",
    "Como a diretriz produz mudança, rastreada a um mecanismo teórico.",
)
add(
    "How the pattern emerged from the data. Convergence across documents, key discovery moments, evolution of understanding.",
    "Cómo emergió el patrón de los datos. Convergencia entre documentos, momentos clave de descubrimiento, evolución de la comprensión.",
    "Wie das Muster aus den Daten entstand. Konvergenz über Dokumente hinweg, Schlüsselmomente der Entdeckung, Entwicklung des Verständnisses.",
    "Como o padrão emergiu dos dados. Convergência entre documentos, momentos-chave de descoberta, evolução da compreensão.",
)
add(
    "How this alternative interpretation differs from the main core_pattern and which incidents would support it.",
    "Cómo esta interpretación alternativa difiere del core_pattern principal y qué incidentes la respaldarían.",
    "Wie sich diese alternative Interpretation vom Haupt-core_pattern unterscheidet und welche Vorfälle sie stützen würden.",
    "Como esta interpretação alternativa difere do core_pattern principal e quais incidentes a sustentariam.",
)
add(
    "How this category processes, resolves, or addresses the core pattern. The explanatory link between Sections 2 and 3.",
    "Cómo esta categoría procesa, resuelve o aborda el patrón central. El vínculo explicativo entre las Secciones 2 y 3.",
    "Wie diese Kategorie das Kernmuster verarbeitet, auflöst oder adressiert. Die erklärende Verbindung zwischen Abschnitten 2 und 3.",
    "Como esta categoria processa, resolve ou aborda o padrão central. O vínculo explicativo entre as Seções 2 e 3.",
)
add(
    "How this expansion relates to the core {object_of_study}",
    "Cómo se relaciona esta expansión con el {object_of_study} central",
    "Wie diese Erweiterung mit dem Kern-{object_of_study} zusammenhängt",
    "Como esta expansão se relaciona com o {object_of_study} central",
)
add(
    "How this interviewee speaks: metaphors used, euphemisms, filler words, repeated words, invented terms. Compare with the documented general pattern. If no difference: 'No changes from the previous version.' If insufficient text to evaluate: 'Insufficient evidence in this document.'",
    "Cómo habla este entrevistado: metáforas usadas, eufemismos, muletillas, palabras repetidas, términos inventados. Comparar con el patrón general documentado. Si no hay diferencia: 'Sin cambios respecto a la versión anterior.' Si el texto es insuficiente para evaluar: 'Evidencia insuficiente en este documento.'",
    "Wie dieser Interviewte spricht: verwendete Metaphern, Euphemismen, Füllwörter, wiederholte Wörter, erfundene Begriffe. Mit dem dokumentierten allgemeinen Muster vergleichen. Wenn kein Unterschied: 'Keine Änderungen gegenüber der vorherigen Version.' Wenn Text für Bewertung unzureichend: 'Unzureichende Belege in diesem Dokument.'",
    "Como este entrevistado fala: metáforas usadas, eufemismos, palavras de preenchimento, palavras repetidas, termos inventados. Comparar com o padrão geral documentado. Se não houver diferença: 'Sem alterações em relação à versão anterior.' Se texto insuficiente para avaliar: 'Evidência insuficiente neste documento.'",
)
add(
    "How this variable enables or constrains access to the control variables.",
    "Cómo esta variable habilita o restringe el acceso a las variables de control.",
    "Wie diese Variable den Zugang zu den Kontrollvariablen ermöglicht oder einschränkt.",
    "Como esta variável habilita ou restringe o acesso às variáveis de controle.",
)
add(
    "How to expand the relationship to accommodate this diverging data (condition, subtype, context, alternative path).",
    "Cómo expandir la relación para acomodar estos datos divergentes (condición, subtipo, contexto, camino alternativo).",
    "Wie die Beziehung erweitert werden kann, um diese abweichenden Daten aufzunehmen (Bedingung, Subtyp, Kontext, alternativer Pfad).",
    "Como expandir a relação para acomodar estes dados divergentes (condição, subtipo, contexto, caminho alternativo).",
)
add(
    "How to fix it. One concrete sentence.",
    "Cómo corregirlo. Una oración concreta.",
    "Wie es zu beheben ist. Ein konkreter Satz.",
    "Como corrigi-lo. Uma frase concreta.",
)
add(
    "How to resolve the contradiction.",
    "Cómo resolver la contradicción.",
    "Wie der Widerspruch aufzulösen ist.",
    "Como resolver a contradição.",
)
add(
    "How well this relationship explains the participants' behavior.",
    "Qué tan bien explica esta relación el comportamiento de los participantes.",
    "Wie gut diese Beziehung das Verhalten der Teilnehmer erklärt.",
    "Quão bem esta relação explica o comportamento dos participantes.",
)
add(
    "Hypotheses anchored in evidence. Empty array if no support.",
    "Hipótesis ancladas en evidencia. Array vacío si no hay respaldo.",
    "In Belegen verankerte Hypothesen. Leeres Array, wenn keine Unterstützung.",
    "Hipóteses ancoradas em evidência. Array vazio se não houver suporte.",
)
add(
    "Hypotheses that emerge from this group (Step 4). Empty array if no clear hypotheses emerge.",
    "Hipótesis que emergen de este grupo (Paso 4). Array vacío si no emergen hipótesis claras.",
    "Hypothesen, die aus dieser Gruppe entstehen (Schritt 4). Leeres Array, wenn keine klaren Hypothesen entstehen.",
    "Hipóteses que emergem deste grupo (Passo 4). Array vazio se nenhuma hipótese clara emergir.",
)
add(
    "Hypothesis as a testable statement.",
    "Hipótesis como declaración comprobable.",
    "Hypothese als überprüfbare Aussage.",
    "Hipótese como declaração testável.",
)
add(
    "Hypothesis in 1-2 sentences.",
    "Hipótesis en 1-2 oraciones.",
    "Hypothese in 1-2 Sätzen.",
    "Hipótese em 1-2 frases.",
)
add(
    "IDs of assigned incidents.",
    "IDs de incidentes asignados.",
    "IDs der zugewiesenen Vorfälle.",
    "IDs dos incidentes atribuídos.",
)
add(
    "IDs of categories involved.",
    "IDs de categorías involucradas.",
    "IDs der beteiligten Kategorien.",
    "IDs das categorias envolvidas.",
)
add(
    "IDs of categories to densify. Empty if disposition != densify_existing.",
    "IDs de categorías a densificar. Vacío si disposition != densify_existing.",
    "IDs der zu verdichtenden Kategorien. Leer, wenn disposition != densify_existing.",
    "IDs das categorias a densificar. Vazio se disposition != densify_existing.",
)
add(
    "IDs of segments that support the hypothesis.",
    "IDs de segmentos que respaldan la hipótesis.",
    "IDs der Segmente, die die Hypothese stützen.",
    "IDs dos segmentos que sustentam a hipótese.",
)
add(
    "INTERCAMBIABLES: same pattern. NO_INTERCAMBIABLES: distinct patterns. INSUFICIENTES_INCIDENTES: fewer than 2 incidents to compare.",
    "INTERCAMBIABLES: mismo patrón. NO_INTERCAMBIABLES: patrones distintos. INSUFICIENTES_INCIDENTES: menos de 2 incidentes para comparar.",
    "INTERCAMBIABLES: gleiches Muster. NO_INTERCAMBIABLES: unterschiedliche Muster. INSUFICIENTES_INCIDENTES: weniger als 2 Vorfälle zum Vergleichen.",
    "INTERCAMBIABLES: mesmo padrão. NO_INTERCAMBIABLES: padrões distintos. INSUFICIENTES_INCIDENTES: menos de 2 incidentes para comparar.",
)
add(
    "If FORCED: name of the paradigm_state property that already covers this incident",
    "Si FORCED: nombre de la propiedad paradigm_state que ya cubre este incidente",
    "Bei FORCED: Name der paradigm_state-Eigenschaft, die diesen Vorfall bereits abdeckt",
    "Se FORCED: nome da propriedade paradigm_state que já cobre este incidente",
)
add(
    "If MOD or FORCED: concrete action",
    "Si MOD o FORCED: acción concreta",
    "Bei MOD oder FORCED: konkrete Maßnahme",
    "Se MOD ou FORCED: ação concreta",
)
add(
    "If MOD or FORCED: concrete, actionable fix. What to change and how.",
    "Si MOD o FORCED: solución concreta y accionable. Qué cambiar y cómo.",
    "Bei MOD oder FORCED: konkrete, umsetzbare Korrektur. Was zu ändern ist und wie.",
    "Se MOD ou FORCED: correção concreta e acionável. O que mudar e como.",
)
add(
    "If MOD or FORCED: recover, re-evaluate, or seek more data?",
    "Si MOD o FORCED: ¿recuperar, re-evaluar o buscar más datos?",
    "Bei MOD oder FORCED: wiederherstellen, neu bewerten oder mehr Daten suchen?",
    "Se MOD ou FORCED: recuperar, reavaliar ou buscar mais dados?",
)
add(
    "If MOD: UUIDs of codes that should NOT be in this merger",
    "Si MOD: UUIDs de códigos que NO deberían estar en esta fusión",
    "Bei MOD: UUIDs von Codes, die NICHT in dieser Fusion sein sollten",
    "Se MOD: UUIDs de códigos que NÃO deveriam estar nesta fusão",
)
add(
    "If MOD: concrete adjustment suggestion",
    "Si MOD: sugerencia concreta de ajuste",
    "Bei MOD: konkreter Anpassungsvorschlag",
    "Se MOD: sugestão concreta de ajuste",
)
add(
    "If MOD: concrete fix (change type to X, reverse direction, strengthen evidence with Y). If FORCED: why this edge should be removed.",
    "Si MOD: solución concreta (cambiar tipo a X, invertir dirección, fortalecer evidencia con Y). Si FORCED: por qué esta arista debe eliminarse.",
    "Bei MOD: konkrete Korrektur (Typ zu X ändern, Richtung umkehren, Belege mit Y stärken). Bei FORCED: warum diese Kante entfernt werden sollte.",
    "Se MOD: correção concreta (mudar tipo para X, inverter direção, fortalecer evidência com Y). Se FORCED: por que esta aresta deve ser removida.",
)

# ── Continue with remaining ~350 descriptions ──
# (This script will be extended by the next write)

print(f"Translation map size so far: {len(TR)}")
