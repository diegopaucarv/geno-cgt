# 3. Cómo funciona por dentro

> No vamos a explicar cada línea de código. Vamos a contar qué hace el sistema cuando le das entrevistas, y por qué cada decisión de diseño existe. Para eso, vamos a seguir un solo ejemplo: **entrevistas con periodistas que cubren tecnología**. Diez entrevistas. El sistema no sabe nada de periodismo. Solo sabe lo que vos le dijiste: "buscá la preocupación recurrente de este grupo."

---

## 3.1 Antes de tocar los datos: lo que el sistema te pregunta

Antes de procesar una sola línea, el sistema necesita tres cosas. Solo tres:

**Primero: tu población.** *"Periodistas que cubren tecnología en medios digitales de habla hispana."* Eso es todo. El sistema no te pide hipótesis, no te pide marco teórico, no te pide variables. Solo quiere saber a quiénes estás estudiando. Con eso, un agente generaliza tu descripción para que la teoría resultante sea transferible — *"Profesionales de la información que operan en entornos mediáticos con alta mediación tecnológica"* — y te pregunta si estás de acuerdo. Si no, lo editás.

**Segundo: qué tipo de patrón buscás.** Hay cinco opciones: preocupación, emoción, conducta, discurso, identidad. Elegís *preocupación*. Esto le dice al sistema que su rol es "layman" — un observador sin preconceptos — y que sus códigos van en gerundio: "Negociando", "Evitando", "Escaneando". Si hubieras elegido *emoción*, codificaría con sustantivos: "Ansiedad", "Frustración", "Alivio".

**Tercero: si querés ayuda opcional.** Podés darle pistas sobre tu población, pero no es obligatorio. El sistema funciona igual sin ellas.

Estas tres preguntas no son un formulario administrativo. Son el ancla metodológica: definen el *lente* con el que el sistema va a mirar tus datos. Y una vez que las respondiste, el sistema **no te vuelve a preguntar nada hasta que tenga algo que mostrarte**. Ese silencio es deliberado. Glaser insistía en que el investigador no debe interferir durante la codificación abierta. El sistema se calla y trabaja.

---

## 3.2 El ritmo que se repite en todos lados

Antes de entrar en fases, necesitás entender un patrón. El sistema lo aplica en **cada** decisión teórica, desde la más chica (¿este incidente pertenece a esta categoría?) hasta la más grande (¿esta es la categoría central del estudio?). Es el *latido*:

```
Alguien PROPONE (sin ver lo que ya existe, para no sesgarse)
  → Alguien CRITICA (comparando contra los datos, no contra opiniones)
    → VOS DECIDÍS (confirmás, modificás o rechazás)
```

Tres roles, siempre separados. El que propone nunca es el que critica. El que critica nunca decide. La decisión es tuya.

¿Por qué existe este ritmo? Porque resuelve el problema más antiguo de la investigación cualitativa: **el sesgo de confirmación**. Un investigador humano, cuando ya tiene categorías provisionales en la cabeza, tiende a ver los nuevos datos a través de esas categorías. Es inevitable. Lo llamamos *forcing*: forzar lo nuevo a encajar en lo viejo.

El sistema lo resuelve con una regla brutal: **el que propone no ve lo que ya existe**. Punto.

En la práctica, esto significa que cuando el sistema va a extraer incidentes de una entrevista nueva, **no le muestra las categorías que ya descubrió en las entrevistas anteriores**. Ve la entrevista fresca, como si fuera la primera. Esto es contraintuitivo — ¿no sería más eficiente mostrarle todo? — pero es metodológicamente necesario. Si el extractor viera las categorías existentes, forzaría los nuevos incidentes a encajar en ellas. Es exactamente lo que haría un investigador humano sin darse cuenta.

---

## 3.3 Fase 1: Lo que pasa cuando el sistema lee una entrevista

Volvamos a los periodistas. Subiste diez transcripciones. El sistema empieza con la primera.

### Paso 1: Clasificar cada segmento

Lo primero que hace es leer la entrevista entera — no segmento por segmento, sino completa — y clasificar cada fragmento en cuatro categorías que vienen directo de Glaser:

- **Oro**: lo que el periodista dice espontáneamente. Su experiencia real. *"Todos los días entro y el algoritmo ya me asignó 40 notas. No puedo rechazarlas."*
- **Plata**: lo que cree que debe decir. Discurso normativo. *"Bueno, uno como periodista debe ser objetivo, ¿no?"*
- **Bronce**: opinión forzada por la pregunta del entrevistador. *"¿Qué opino de la IA? Es un tema complejo..."*
- **Anomalía**: evasión. *"No sé, la verdad no tengo una opinión formada."*

Solo el **oro** avanza. El resto se archiva. Esto no es un filtro de calidad — es una decisión metodológica. Si codificás *properline data* (plata) creyendo que es experiencia real, tu teoría va a describir normas sociales, no comportamiento. Y si codificás *interpreted data* (bronce), vas a describir lo que el entrevistador quiere oír.

### Paso 2: Extraer incidentes y detectar el patrón individual

Con los segmentos de oro identificados, el sistema hace una sola llamada al modelo PRO (el más potente). En esa llamada, **simultáneamente**:

1. **Extrae incidentes**: para cada segmento de oro, produce un *jot* — una anotación de una o dos palabras, un gerundio. "Evitando". "Negociando". "Resistiendo". Con su vínculo al segmento exacto de origen.
2. **Detecta el patrón individual**: identifica cuál parece ser el patrón recurrente de *este* periodista en particular, usando solo sus datos. Te dice: *"Para esta persona, el patrón recurrente parece ser Monitoreando la obsolescencia técnica"*, con citas y un nivel de confianza.

Antes, estos dos pasos estaban separados: un agente extraía incidentes, otro detectaba el patrón. El problema era que el segundo agente trabajaba con incidentes extraídos por el primero usando *otro* lente. Al unificarlos en una sola llamada, el mismo modelo que identifica los incidentes también detecta qué los une. Es más coherente, más rápido, y metodológicamente más sólido.

Todo esto pasa para **una** entrevista. El sistema repite el proceso para cada una de las diez, en paralelo donde puede. Al final de esta fase, tenés diez patrones individuales y cientos de incidentes. Pero todavía no hay categorías compartidas.

---

## 3.4 Fase 2: Cuando los incidentes se encuentran

Ahora el sistema pone todos los incidentes de las diez entrevistas sobre la mesa. Literalmente: los carga en una sola llamada al modelo PRO y le pide que los agrupe.

Este es quizás el momento más importante del pipeline, y donde el diseño actual difiere radicalmente de la versión anterior. La versión vieja hacía tres pasos: primero filtraba incidentes por similitud de embeddings, después comparaba pares con llamadas al LLM, y finalmente aplicaba un algoritmo de clustering (Union-Find). Tres pasos, cada uno acumulando error. El pre-filtro por embedding podía descartar incidentes conceptualmente idénticos solo porque usaban vocabulario distinto. El algoritmo de clustering imponía estructura matemática a algo que debía emerger.

La versión actual (`workers/heavy/comparator.py`) hace **una sola cosa**: manda todos los incidentes juntos al modelo PRO y le dice: *"Agrupalos por patrón de comportamiento. Dos incidentes con palabras distintas pueden evidenciar el mismo patrón. Dos incidentes con palabras parecidas pueden evidenciar patrones distintos."* Sin pre-filtro. Sin comparación de a pares. Sin algoritmo.

El modelo responde con grupos. Por ejemplo:

- Grupo A: "Escaneando el horizonte de amenazas" — 14 incidentes de 7 periodistas distintos
- Grupo B: "Negociando con el algoritmo" — 11 incidentes de 5 periodistas
- Grupo C: "Ocultando la dependencia técnica" — 8 incidentes de 4 periodistas

Y así.

**Esto no es un truco de eficiencia. Es una decisión metodológica.** Al darle todos los incidentes juntos, el modelo puede ver patrones *a través* de documentos — algo que el enfoque pairwise no permitía. Un incidente en la entrevista 3 puede iluminar un incidente en la entrevista 7 de una manera que la comparación de a pares nunca capturaría.

### La conversación que afina las etiquetas

Los grupos existen, pero necesitan nombres y definiciones. Entra el Etiquetador: un agente PRO que, grupo por grupo, propone una etiqueta en gerundio, escribe una definición inicial, e identifica las variaciones internas. "Este grupo parece tratar sobre cómo los periodistas monitorean cambios tecnológicos que amenazan sus habilidades. La etiqueta propuesta es 'Escaneando el horizonte de amenazas'. Las variaciones incluyen: amenazas a corto plazo vs. largo plazo, amenazas técnicas vs. amenazas profesionales."

Después entra el Crítico: un agente FLASH (más rápido, más barato) que evalúa la etiqueta. No emite un veredicto de "aprobado" o "rechazado". Solo da feedback: *"La etiqueta captura el monitoreo pero no la ansiedad que aparece en los incidentes 3, 7 y 9. ¿Podrías incorporar la dimensión emocional?"*

El Etiquetador recibe el feedback y refina. El Crítico evalúa de nuevo. Hasta tres rondas. Es una **conversación generativa**, no un tribunal. Y es importante notar que este crítico **no detiene el pipeline** — las etiquetas se guardan como están, con su historia de refinamiento, para que vos las revises después. El crítico sugiere, no decide.

### Lo que el agrupador y el etiquetador NO ven

Hay algo crucial que ni el Agrupador ni el Etiquetador reciben: las categorías que ya existen de lotes anteriores, las etiquetas que ya se pusieron, las preocupaciones que ya se confirmaron. **Están aislados.** Solo ven los incidentes del lote actual.

Si vieran lo que ya existe, forzarían los nuevos incidentes a encajar en moldes viejos. Es exactamente lo que haría un investigador humano. El aislamiento es la defensa del sistema contra su propio sesgo.

---

## 3.5 La pausa: cada tres documentos, el sistema te habla

El sistema no avanza de golpe. Cada tres documentos — aproximadamente, porque el último lote puede ser más chico — hace una pausa. No es un bug, es una fase.

En esa pausa, el sistema te muestra **cuatro cosas a la vez**:

1. **Categorías unificadas**: las que acaba de descubrir, comparadas con las que ya venían de lotes anteriores. Si dos categorías describen lo mismo con distinto nombre, se unifican. Si una es nueva, se incorpora.
2. **Hipótesis acumuladas**: todo lo que el sistema cree saber hasta ahora sobre cómo las categorías se relacionan. *"Escaneando el horizonte aparece siempre antes que Negociando con el algoritmo en 7 de 10 entrevistas."*
3. **Preocupaciones candidatas**: según los patrones que están emergiendo, ¿cuál parece ser la preocupación central de estos periodistas?
4. **Revisión de configuración**: ¿la población está bien definida? ¿Hay subgrupos? ¿El estilo de codificación está funcionando?

Y entonces el sistema **se calla y espera**. No avanza hasta que vos decidas. Podés aceptar, modificar, rechazar. Cuando decidís, el sistema continúa con el siguiente lote, ahora con tu feedback incorporado.

Esta pausa es deliberada. Es el primer momento en que el sistema te pide que intervengas, y no es casualidad que sea después de procesar varios documentos — hay suficiente material para que la intervención sea informada, pero no tanto como para que sea abrumadora.

---

## 3.6 Lo que pasa cuando modificás algo

Imaginá que en la pausa del lote 2, ves que el sistema fusionó "Escaneando el horizonte de amenazas" con "Monitoreando cambios técnicos", pero vos creés que son dos cosas distintas. Las separás. El sistema no solo guarda tu cambio. Hace algo más inteligente.

**Borra solo lo que depende de ese cambio.** Las categorías que no dependen de la fusión se mantienen intactas. Las hipótesis que no involucraban a esas categorías se mantienen intactas. Pero todo lo que estaba construido sobre la fusión — hipótesis que la mencionaban, relaciones conceptuales que la atravesaban — se borra y se recalcula.

Esto es el **cascade**. No es un recompute total. Es una propagación selectiva: el sistema sabe exactamente qué depende de qué, y solo toca lo necesario.

¿Por qué importa? Porque en la CGT manual, cuando cambiás de opinión sobre una categoría, tenés que re-codificar manualmente todo lo que tocaba esa categoría. Es tan costoso que los investigadores tienden a no hacerlo — aceptan categorías mediocres porque corregirlas implica rehacer semanas de trabajo. El cascade hace que corregir sea barato. Y cuando corregir es barato, **corregís más**. La teoría mejora.

---

## 3.7 La evidencia no se busca: se sigue

En muchas herramientas de análisis cualitativo asistido por IA, cuando querés ver "qué evidencia respalda esta categoría", el sistema hace una búsqueda por similitud semántica: encuentra los segmentos cuyo embedding es más parecido al embedding de la categoría. Es rápido, pero es frágil. Dos cosas pueden ser semánticamente similares sin ser conceptualmente equivalentes. Y dos cosas pueden ser conceptualmente equivalentes usando vocabulario completamente distinto.

Este sistema no busca evidencia. **La sigue.**

Cada incidente, desde el momento en que se extrajo, sabe exactamente de qué segmento de qué documento proviene. Es un vínculo de base de datos — una foreign key. Cuando necesitás evidencia para una categoría, el sistema recorre la cadena:

```
Categoría → Grupo de incidentes → Incidentes → Segmentos → Citas textuales
```

No hay similitud semántica. No hay embeddings. Hay **procedencia**. Podés trazar cualquier proposición teórica hasta la cita exacta que la originó. Esto es trazabilidad, no search. Y es una decisión de diseño que refleja un principio metodológico: la evidencia es el dato que generó el concepto, no el dato que se le parece.

---

## 3.8 Contratos entre fases: lo que cada agente promete entregar

El sistema tiene 96 agentes. Cada uno lee datos, piensa, y produce algo. Pero lo crucial no es cuántos son — es **cómo se pasan la información entre ellos**.

En la mayoría de los sistemas multi-agente, los agentes producen texto libre o JSON sin estructura fija. El agente que recibe ese output tiene que *interpretarlo*. Y en esa interpretación se pierde precisión.

Acá no. Cada agente tiene un **schema**: un contrato escrito en JSON Schema que declara exactamente qué campos va a producir, de qué tipo, y cuáles son obligatorios. El agente que consume ese output sabe exactamente qué esperar.

Por ejemplo, el agente que propone la preocupación central (`fc_main_concern_proposer`) tiene este schema:

```json
{
  "required": ["candidates", "rationale"],
  "properties": {
    "candidates": {
      "type": "array",
      "items": {
        "required": ["statement", "supporting_codes", "rationale"]
      }
    }
  }
}
```

El agente que critica esa propuesta (`fc_main_concern_critic`) recibe algo que **sabe** que tiene `candidates`, que es un array, que cada elemento tiene `statement` y `supporting_codes`. No hay ambigüedad. No hay interpretación. Hay un contrato.

Y como el sistema existe en cuatro idiomas, cada agente tiene su schema traducido: español, inglés, alemán, portugués. La estructura es idéntica; cambian las descripciones. Un periodista en Madrid y uno en Berlín pueden usar el mismo pipeline sin cambiar una línea de código — solo cambia el idioma del schema que se inyecta en el prompt.

---

## 3.9 PRO y FLASH: por qué el sistema usa dos modelos distintos

El sistema no usa un solo modelo de lenguaje. Usa dos, y no es por capricho.

**PRO** es el modelo pesado: DeepSeek V4 Pro. Genera 8192 tokens por llamada, con temperatura 0.3. Se usa cuando el agente tiene que **crear** algo nuevo: proponer una preocupación central, agrupar incidentes, escribir una sección de la teoría.

**FLASH** es el modelo liviano: Nemotron 550B. Genera 4096 tokens, con temperatura 0.1. Se usa cuando el agente tiene que **evaluar** algo que ya existe: ¿esta etiqueta es precisa? ¿esta expansión de categoría es genuina? ¿hay gaps en esta sección?

La diferencia de temperatura no es arbitraria. PRO necesita 0.3 porque la generación conceptual requiere cierta apertura — un poco de creatividad para ver patrones donde no los hay obvios. FLASH usa 0.1 porque la verificación requiere consistencia — ante la misma etiqueta, el crítico debería dar el mismo feedback.

Pero la razón real de tener dos tiers es **económica**. DeepSeek V4 Pro cuesta aproximadamente 10 veces más que Nemotron 550B por token. Si el sistema usara PRO para cada verificación — cada chequeo de etiqueta, cada evaluación de saturación — el costo sería prohibitivo. FLASH hace que el sistema sea viable.

El principio es: **el modelo caro genera, el modelo barato verifica**. Es un patrón de AI engineering, no de CGT, pero sin él el sistema no podría existir.

---

## 3.10 Lo que el sistema NO hace

Tan importante como lo que hace es lo que **no** hace.

**No busca literatura por vos durante el análisis.** La literatura entra al final, cuando tu teoría ya está escrita. En ese momento, el sistema trata los papers como si fueran nuevas entrevistas: extrae incidentes, los codifica con tus categorías, y evalúa si la literatura extiende, modifica, integra o trasciende tu teoría. Pero nunca te dice "esto ya lo dijo Foucault" mientras estás codificando. Eso sería tratar la literatura como autoridad, y en CGT la autoridad son los datos.

**No usa RAG durante el pipeline central.** Los endpoints de búsqueda semántica existen en el backend, pero el pipeline de codificación no los toca. La evidencia se sigue por foreign keys, no se busca por embeddings.

**No decide por vos.** En siete momentos del pipeline, el sistema se detiene y te muestra una propuesta y una crítica. Pero el botón de "aceptar" lo apretás vos. Esto no es una cortesía. Es un requisito metodológico. La CGT no puede ser automatizada porque el juicio teórico es humano. El sistema propone, critica, muestra evidencia. Pero la teoría es tuya.

---

| Sección | Lo que explica |
|---------|---------------|
| 3.1 | Las tres preguntas iniciales y por qué importan |
| 3.2 | El ritmo proposer→critic→HITL como defensa contra el sesgo |
| 3.3 | Fase 1: clasificación de segmentos + extracción unificada |
| 3.4 | Fase 2: agrupación cross-document + conversación etiquetador-crítico |
| 3.5 | La pausa cada 3 documentos con 4 decisiones simultáneas |
| 3.6 | El cascade: modificar sin rehacer todo |
| 3.7 | Evidencia por foreign keys, no por embeddings |
| 3.8 | Schemas tipados como contratos entre fases + i18n |
| 3.9 | PRO vs FLASH: dos modelos, dos trabajos |
| 3.10 | Lo que el sistema deliberadamente no hace |
