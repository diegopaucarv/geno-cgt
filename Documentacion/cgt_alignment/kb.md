# Classic Grounded Theory — La travesía del investigador

> **Una guía narrativa del proceso CGT glaseriano, tal como lo vive el investigador dentro del sistema GT.**
>
> Este documento describe QUÉ hace el sistema en cada fase. El CÓMO técnico
> (transiciones, tracking, cancelabilidad, checkpoints) está en
> [`4-Patrones_de_desarrollo.md`](./4-Patrones_de_desarrollo.md).
>
> **Arquitectura:** El Orchestrator es DELGADO — despacha tareas Celery, nunca
> llama LLMs directamente. Los workers (NLP, Heavy, Fast) ejecutan. Cada tarea
> tiene tracking (`pipeline_tasks`), es cancelable (`AbortableTask`), y si es
> multi-step, tiene checkpoints para resume. Al terminar, cada worker llama
> `transitions.transition()` que actualiza el estado y despacha la siguiente tarea.

---

## 1. El punto de partida — qué es la CGT y por qué hacemos esto

Imaginá que tenés entrevistas con personas que comparten una experiencia. No sabés exactamente qué buscás. Tenés una intuición: algo pasa ahí, algo recurre, algo estructura sus vidas. Pero no querés imponer tus categorías. Querés que los datos hablen.

Eso es la Classic Grounded Theory de Barney Glaser. No es un método para verificar lo que ya creés saber. Es un método para **descubrir** lo que no sabés que está ahí.

### Lo que la CGT no es

No es un análisis temático — no buscamos "temas" que se repiten. No es una verificación de hipótesis — no tenemos hipótesis previas. No es codificación axial — eso es Strauss y Corbin, que te piden buscar causas, contextos y consecuencias antes de que los datos te los muestren. En CGT, nada se impone. Todo emerge.

### Lo que la CGT es

Es **comparación constante**: cada incidente se compara con cada otro incidente, una y otra vez, hasta que los patrones se revelan solos. Es **emergencia**: las categorías, propiedades y relaciones surgen de los datos, no de tu cabeza. Es **abstracción creciente**: empezás con incidentes concretos ("el periodista dice que primero analiza la herramienta y luego decide si usarla") y terminás con conceptos abstractos ("escaneando el horizonte de amenazas"). Y es un proceso **guiado por vos**: el sistema propone, critica, muestra evidencia — pero la decisión final siempre es tuya.

### La pregunta que guía todo

Toda investigación CGT gira alrededor de una pregunta, pero esa pregunta no es fija. Depende de qué tipo de patrón humano estás buscando:

- Si buscás **preocupaciones**: *"¿Cuál es la principal preocupación de este grupo y cómo la procesan continuamente?"*
- Si buscás **emociones**: *"¿Cuál es la emoción recurrente que estructura su experiencia?"*
- Si buscás **conductas**: *"¿Qué hacen una y otra vez, y por qué?"*
- Si buscás **discursos**: *"¿Cómo construyen su narrativa?"*
- Si buscás **identidad**: *"¿Cómo negocian quiénes son?"*

El método es el mismo. Lo que cambia es el lente. Y el lente lo elegís vos al inicio, aunque puede cambiar durante el camino.

### El patrón que se repite en todo el proceso

En cada nivel de abstracción — de incidentes a categorías, de categorías al patrón de interés, del patrón de interés a la categoría central, de las relaciones a la teoría integrada — el sistema aplica el mismo ritmo:

```
Alguien PROPONE (sin ver lo que ya existe, para no sesgarse)
  → Alguien CRITICA (comparando contra los datos)
    → Alguien SINTETIZA (integrando propuesta + crítica)
      → Se vuelve a CRITICAR (segunda pasada, más fina)
        → VOS DECIDÍS (HITL: confirmás, modificás o rechazás)
```

Este ritmo — proponer, criticar, sintetizar, volver a criticar, decidir — es el latido del sistema. Lo vas a ver repetirse una y otra vez.

---

## 2. Antes de empezar — lo que el sistema necesita saber de vos

No necesitás definir un marco teórico. No necesitás hipótesis. Solo dos cosas.

### Tu población — ¿a quiénes estás estudiando?

Describila en lenguaje natural, como le contarías a un colega. Podés ser específico: *"los pobladores del asentamiento humano 7 de Octubre"*. El sistema se encarga del resto.

Un agente rápido (FLASH) toma tu descripción y la transforma en una **población con alcance teórico**: *"habitantes de asentamientos humanos marginales de Lima Metropolitana en situación de pobreza urbana"*. Esto es crucial: sin generalización, tus hallazgos solo aplicarían a un caso. Con generalización, tu teoría puede ser transferible.

Tu descripción original se **preserva** — el sistema siempre te muestra de dónde viene la versión generalizada, y podés editarla cuando quieras. De la población, el sistema infiere automáticamente qué tan dispersa está (¿es un solo grupo que convive? ¿varios grupos en una región? ¿múltiples países?) y en qué momento temporal se encuentran (¿es su presente? ¿su pasado? ¿un proceso de cambio?). Esto afecta cuánta variación esperar y cuándo considerar que una categoría está saturada.

### Tu objeto de estudio — ¿qué tipo de patrón buscás?

El default es **preocupación central** (main concern), que es el objeto clásico de la CGT. Pero podés elegir otro. Esta elección determina:

- **El lente** con el que el sistema mira los datos. Si elegiste "emotion", busca patrones emocionales, no preocupaciones.
- **El estilo de codificación**. Si elegiste "concern", el sistema espera gerundios de procesamiento ("negociando", "evitando"). Si elegiste "behavior", espera gerundios de acción.
- **El rol** que asume el sistema. Para "concern", el rol es "layman" — sin preconcepciones, máxima apertura inductiva. Para otros, el sistema sugiere un rol apropiado ("investigador de patrones emocionales") que podés editar.

También podés configurar el **estilo de codificación** independientemente: gerundios (el clásico de Glaser), citas textuales del participante (in-vivo), nominalizaciones, frases descriptivas, o combinaciones. El sistema soporta seis estilos y podés usar varios a la vez.

### Ayuda opcional

Si no estás seguro de cómo configurar algo, el sistema te ofrece dos asistentes que podés invocar cuando quieras: uno que analiza tu población inicial y te sugiere ajustes ("parece haber dos grupos diferenciados, ¿querés enfocarte en uno?"), y otro que lee tus primeros datos y te recomienda configuraciones ("por el tipo de entrevistas, te sugeriría object_of_study='concern'").

---

## 3. El patrón de interés — lo que antes llamábamos "main concern"

El "main concern" de Glaser es solo el caso más famoso. En realidad, lo que buscamos es un **patrón de interés**: el patrón recurrente que estructura la experiencia de tus participantes, sea cual sea su naturaleza.

### Qué es y qué no es

No es lo que los participantes **dicen** que les preocupa. Cuando un periodista te dice "bueno, uno como periodista debe ser objetivo", eso no es su preocupación real — es lo que cree que debe decir (los metodólogos lo llaman "properline data"). El patrón de interés está en lo que hacen, en lo que sienten, en cómo actúan cuando no están performando para el entrevistador.

No es un tema descriptivo. "La inteligencia artificial en el periodismo" es un tema. "Manteniendo relevancia profesional ante la amenaza de obsolescencia" es un patrón de interés.

Y no es algo que **encontrás** de una sola vez. Emerge. Se refina. A veces cambia.

### Cómo emerge

El patrón de interés se **descubre progresivamente**, a medida que los datos se acumulan. No se fuerza al inicio ni se asume desde el primer documento — se deja que los propios datos revelen qué es lo que realmente estructura la experiencia de esta población.

Cada tres documentos, el sistema hace una pausa deliberada y te propone posibles preocupaciones subyacentes — expresadas como gerundios, con evidencia de los segmentos que las sugieren. Estas propuestas no son definitivas. Son hipótesis, y son **tuyas** para evaluar.

Una población puede tener **múltiples preocupaciones coexistiendo**. Los periodistas pueden estar simultáneamente "manteniendo relevancia profesional" Y "negociando autonomía editorial". Durante la fase de open coding, podés seleccionar varias. El sistema no te obliga a elegir una sola todavía — sería prematuro. Pero al final del recorrido, cuando toda la evidencia está sobre la mesa, **elegís UNA**. Una sola preocupación será el ancla del resto del análisis.

Cada categoría que el sistema produce está siempre vinculada a una preocupación específica y a una población concreta. Esto es fundamental: una misma conducta puede significar cosas distintas en poblaciones distintas. "Evitando" en profesores veteranos no es lo mismo que "evitando" en profesores recién egresados. La CGT compara unidades conceptuales, no unidades demográficas estrictas.

---

## 4. Open Coding — la fase de descubrimiento

Esta es la fase más artesanal. Vas documento por documento, dejando que los patrones emerjan — pero ahora con un flujo simplificado y unificado.

### Lo que pasa antes de codificar

Antes de extraer cualquier patrón, el sistema clasifica cada segmento de la entrevista según su **tipo de dato**. Esto es fundamental y viene directo de Glaser:

- **Oro** — `baseline_data`: lo que el participante describe espontáneamente, sin filtro. Su experiencia real. *"Todos los días entro y el algoritmo ya me asignó 40 pedidos. No puedo rechazarlos."*
- **Plata** — `properline_data`: lo que cree que debe decir. Discurso normativo. *"Bueno, uno como periodista debe ser objetivo, ¿no?"*
- **Bronce** — `interpreted_data`: opinión forzada por la pregunta del entrevistador. *"¿Qué opino de la IA? Es un tema complejo..."*
- **Anomalía** — `vague_data`: evasión. *"No sé, la verdad no tengo una opinión formada."*

Esta clasificación corre en agente **PRO**, pero no se hace segmento por segmento como antes. El sistema procesa el documento completo en un solo llamado, clasificando todos los segmentos juntos. Esto le da al modelo contexto suficiente para distinguir baseline de properline con precisión — no es lo mismo un segmento aislado que uno leído en el flujo completo de la entrevista.

Solo el **oro** avanza. Lo demás se archiva como contexto. Esto no es un capricho metodológico: si codificás properline data creyendo que es experiencia real, tu teoría va a describir normas sociales, no comportamiento real.

### La extracción unificada de incidentes y patrones

En la versión anterior del sistema, la extracción de incidentes y la identificación del patrón individual corrían como pasos separados. En la arquitectura rediseñada, **se unifican en un solo llamado PRO por documento**.

El agente recibe el documento completo con sus segmentos de oro ya clasificados. En una sola pasada, produce:

1. **Incidentes extraídos**: para cada segmento de oro, un jot — una anotación rápida de una o dos palabras, un gerundio. "Evitando". "Negociando". "Resistiendo". Con su vínculo al segmento de origen. No es una categoría todavía — es una semilla.
2. **El patrón individual (prime_mover)**: el patrón de interés de **ese** entrevistado. Usa solo sus datos de oro. No compara con otros. Te dice: *"Para esta persona, el patrón recurrente parece ser X"*, con citas que lo respaldan y un nivel de confianza.

Esta unificación no es un capricho de eficiencia. Es una decisión metodológica: el mismo agente que extrae los incidentes está en la mejor posición para detectar el patrón que los une. Separarlos introducía una brecha artificial donde el patrón individual se infería de incidentes que otro agente había extraído con otro lente.

El extractor está **aislado**. No ve otros documentos. No ve categorías existentes. No ve patrones previos. Solo ve los segmentos de oro del documento actual, tu objeto de estudio, y tu estilo de codificación. Si viera categorías existentes, forzaría el incidente nuevo a encajar en moldes viejos. Es el equivalente a que un investigador lea una transcripción fresca sin tener sus notas anteriores a la vista.

> **Implementación:** Para detalles técnicos (tier del modelo, AbortableTask, checkpoints), ver `4-Patrones_de_desarrollo.md` §2.1 y `5-Adaptacion_Sistema_Agencial.md` §2.3.

Y aquí hay una regla crucial que Glaser insistía en enseñar: **Keep Moving**. No te detengas a sobre-analizar un incidente. Si es ambiguo, anotalo y avanza. Confiá en que el patrón se revelará cuando tengas docenas de incidentes, no cuando le des cien vueltas a uno solo. El sistema te ayuda con esto: si un incidente es ambiguo, lo marca como `keep_moving=true` y sigue.

---

### 4.5 La pausa por lotes — el sistema respira cada pocos documentos

El sistema no avanza de golpe. Cada vez que un lote de documentos completa su síntesis — normalmente cada 3 documentos, aunque el último lote puede ser más chico — el sistema hace una pausa deliberada. Esta pausa tiene tres momentos:

1. **Unificación de categorías**: las categorías recién descubiertas en este lote se comparan con las que ya venían de lotes anteriores. Si dos categorías describen el mismo patrón con distinto nombre, se unifican. Si una es nueva, se incorpora. El resultado es un conjunto limpio, sin duplicados.

2. **Hipótesis acumuladas**: el sistema revisa todo lo que sabe hasta ahora y actualiza sus hipótesis sobre cómo las categorías se relacionan entre sí. Cada hipótesis es específica y trazable: "La categoría A aparece siempre antes que la B en los documentos 1, 3 y 5". Estas hipótesis son el insumo principal para encontrar la categoría central más adelante.

3. **Revisión de configuración**: un agente crítico revisa el panorama completo y te pregunta: ¿las preocupaciones que están emergiendo son las correctas? ¿La población está bien definida o hay subgrupos que deberían separarse? ¿El estilo de codificación está capturando lo importante? El sistema te muestra sus hallazgos y **no avanza sin tu decisión**.

En esta pausa ves todo junto: categorías unificadas, hipótesis actualizadas, posibles preocupaciones, variantes de población, y recomendaciones de estilo. Podés aceptar, modificar o rechazar. Y cuando decidís, el sistema continúa con el siguiente lote, ahora con tu feedback incorporado.

---

## 5. Síntesis Cross-Document — cuando los patrones individuales se encuentran

Hasta ahora, cada documento se procesó por separado. Pero la CGT no es sobre individuos — es sobre **patrones compartidos**. La Fase B es donde los incidentes de todos los documentos del batch actual se ponen sobre la mesa y se comparan entre sí.

### Tres agentes, tres roles

Esta fase implementa una separación fundamental que evita el sesgo más común en la codificación cualitativa: forzar incidentes nuevos a encajar en categorías viejas. **Ni B1 ni B2 ven categorías previas ni preocupaciones confirmadas.** Solo ven los incidentes del batch actual. El aislamiento es total.

> **Implementación:** Para detalles de la arquitectura Celery, checkpoints y tracking de esta fase, ver `4-Patrones_de_desarrollo.md` §2.1 y `5-Adaptacion_Sistema_Agencial.md` §2.1.

**El Agrupador** (B1) recibe todos los incidentes extraídos de los documentos del batch actual — y **solo** esos incidentes. No ve categorías existentes. No ve etiquetas previas. No ve preocupaciones confirmadas. Su trabajo es puramente agrupacional: un agente PRO que, en una sola pasada, organiza los incidentes en grupos por patrón subyacente compartido. No hay pre-filtro por embedding, no hay comparación pairwise, no hay Union-Find. Es una agrupación conceptual directa, como si imprimieras todas las tarjetas de incidentes y las ordenaras sobre una mesa — solo ves las tarjetas, no las etiquetas que les pusiste antes.

**El Etiquetador** (B2) recibe los grupos del Agrupador. Pero a diferencia de la versión anterior que procesaba todos los grupos en batch, ahora itera **un grupo por vez** — un concepto a la vez. Para cada grupo, propone una etiqueta en gerundio (o en el formato que hayas elegido), escribe una definición inicial, e identifica las variaciones internas. Procesar grupo por grupo le da al modelo el contexto completo de ese grupo sin diluirse entre decenas de conceptos simultáneos.

**El Crítico** (B3) evalúa cada etiqueta del Etiquetador. Su rol ahora es **solo feedback**: ¿la etiqueta captura el patrón de todos los incidentes del grupo? ¿Es suficientemente abstracta? ¿Hay incidentes que no encajan? Si encuentra problemas, le devuelve la etiqueta al Etiquetador con sugerencias — pero **no emite veredictos SAT/MOD/FORCED**. Es una conversación generativa, no un tribunal. El Etiquetador mejora la etiqueta y la reenvía. Este bucle generativo-crítico se repite hasta tres veces.

Este diálogo entre el Etiquetador y el Crítico es el corazón de la síntesis. No es un pipeline lineal — es una conversación.

### Evidencia textual para cada categoría (B2.5 — Grounding)

Después de que el Crítico da su feedback final sobre una etiqueta, el sistema hace algo importante: busca en el corpus segmentos que respalden esa categoría. Pero a diferencia de la versión anterior que usaba similitud de embeddings, ahora el grounding usa **los vínculos incidente→segmento** que ya existen desde la fase de extracción. Cada incidente sabe exactamente de qué segmento de qué documento proviene. El sistema simplemente recorre esos vínculos y recolecta las citas textuales. Esto es más preciso, más rápido, y no introduce falsos positivos por similitud semántica superficial.

Esto te permite ver, para cada categoría, qué entrevistados la manifiestan y con qué palabras exactas.

---

## 6. Selective Coding — cuando las categorías maduran

Con las categorías ya formadas, empieza la fase de **delimitación y saturación**. Ya no se trata de crear nuevas categorías — se trata de densificar las que tenés. Pero antes de densificar, hay que decidir **cuáles merecen seguir siendo elaboradas**. Esta fase tiene cinco actos, y en cada uno el sistema te propone, te critica, y te pregunta.

---

### 6.1 Primer acto — confirmación formal del patrón de interés

Durante el open coding, el patrón de interés fue una hipótesis de trabajo que exploraste cada tres documentos, seleccionando múltiples preocupaciones posibles. Ahora, **después de que todos los batches están completos**, el sistema hace una pausa formal para la confirmación definitiva. Este es el momento de elegir UNA.

**Precondiciones.** El sistema verifica dos cosas antes de ejecutar este acto: (1) hay **exactamente UNA** preocupación confirmada — si todavía tenés varias seleccionadas, el sistema te pide que elijas una; (2) **todas las categorías** tienen un `concern_label` que las vincula a una preocupación — si hay categorías huérfanas, el sistema te pide que las asignes o las descartes.

**Proposer** (`main_concern_proposer`, agente PRO): recibe la preocupación confirmada, **todas las categorías** del sistema unificado, y **todas las hipótesis acumuladas** de los Synthesizers. Con este contexto completo, sensa el patrón de interés formal. No puntúa. Busca tensiones latentes — no lo que los participantes dicen que les preocupa, sino lo que sus comportamientos revelan que intentan resolver. Propone de 2 a 4 candidatos de patrón de interés, cada uno expresado como gerundio, con razonamiento cualitativo, categorías que lo respaldan, y — esto es crucial — las categorías que quedarían **huérfanas** si ese candidato fuera el patrón definitivo.

**Critic** (`main_concern_critic`, agente PRO): evalúa cada candidato con criterios CGT. ¿El grounding empírico es sólido o son conexiones superficiales? ¿La cobertura es aceptable (<30% de categorías huérfanas)? ¿Es una preocupación latente o solo un tema descriptivo disfrazado? Emite SAT, MOD o FORCED para cada uno.

**Vos**: ves los candidatos, los veredictos del critic, y decidís. Podés aceptar uno, pedir que se refine, o rechazar todos y pedir una nueva ronda. El patrón de interés que elijas ahora será el ancla de todo lo que sigue.

---

### 6.2 Segundo acto — la reducción selectiva

Este paso no existía en versiones anteriores del sistema, y es quizás el más importante de la codificación selectiva. Una vez que sabés cuál es el patrón de interés, **deliberadamente dejás ir** lo que no se relaciona con él.

No es un filtro automático. Es una decisión teórica.

**Proposer** (`selective_reduction_proposer`, agente PRO): para cada código abierto, evalúa si describe un comportamiento que PROCESA el patrón de interés, una CONDICIÓN que lo posibilita, una CONSECUENCIA de actuar sobre él, o una ESTRATEGIA para resolverlo. Si no cumple ninguno → propone descartarlo, con justificación metodológica y categoría de descarte (unrelated_to_core, descriptive_not_behavioral, single_occurrence, superseded_by_fusion). Los códigos descartados no se eliminan — se archivan con su rationale.

Pero también busca **uniformidades subyacentes**. Si dos o más códigos capturan el mismo patrón con distintos nombres o en distintos contextos, propone fusionarlos en un concepto de orden superior. El criterio es la intercambiabilidad de indicadores, no la similitud temática. Para cada fusión, propone un nuevo gerundio, una definición integrada, y las propiedades heredadas.

**Critic** (`selective_reduction_critic`, agente PRO): evalúa cada descarte y cada fusión. ¿El código descartado realmente no se relaciona? ¿Los códigos fusionados son genuinamente intercambiables? Busca falsos positivos (códigos descartados que deberían recuperarse) y falsos negativos (códigos sobrevivientes que deberían descartarse).

**Vos**: ves el sistema reducido — qué sobrevivió, qué se fusionó, qué se descartó. Podés recuperar un código que el sistema descartó por error. Podés rechazar una fusión que no te convence. El output es un **sistema de códigos reducido**: menos conceptos, mayor abstracción, todo anclado al patrón de interés.

---

### 6.3 Tercer acto — el loop de saturación

Ahora sí, con el sistema reducido, empieza la elaboración densa. Solo las categorías con puntaje ≥4 (las que sobrevivieron la reducción) entran en este ciclo.

El loop itera sobre cada categoría × cada documento. Para cada iteración:

**Proposer** (`core_saturation_proposer`, agente PRO): recibe la categoría, su `paradigm_state` actual (todas las propiedades, dimensiones, condiciones, consecuencias y estrategias documentadas hasta ahora), y los nuevos incidentes extraídos de un documento. Compara cada incidente contra el paradigm_state. Si el incidente revela una propiedad no documentada → propone expansión. Si expande el gradiente de una propiedad existente → propone expansión dimensional. Si revela una nueva condición o consecuencia → propone expansión. Si solo confirma lo que ya sabemos → no propone nada (eso es valioso, pero no es su tarea).

**Critic** (`core_saturation_critic`, agente **FLASH**): esta es una de las pocas tareas de codificación selectiva que corre en modelo rápido. ¿Por qué? Porque es un diff estructurado: compara cada expansión propuesta contra el paradigm_state actual y determina si es genuinamente nueva o si ya está cubierta (con otro nombre, otra descripción equivalente). Emite SAT (expansión genuina, `did_state_expand = true`), MOD (la expansión es imprecisa, ajustar), o FORCED (no hay novedad, `did_state_expand = false`). Corre frecuentemente — potencialmente cientos de veces — así que usar FLASH aquí es una decisión de costo significativa.

**El criterio de saturación**: si una categoría pasa **3 iteraciones consecutivas sin `did_state_expand = true`**, el sistema te la presenta como candidata a saturada. Ves las propiedades documentadas, los gradientes cubiertos, los extremos que tienen evidencia. Y decidís: ¿está saturada? ¿O necesita más datos?

Si decidís que **no está saturada** y ya no hay más documentos en el corpus, el **TheoSampler** se activa — pero solo ahora, bajo demanda, no antes. Busca en el corpus incidentes que podrían llenar los extremos vacíos. Si no encuentra, te sugiere qué tipo de caso recolectar y te redacta una pregunta de entrevista. Los nuevos documentos entran al loop y el ciclo continúa.

**MemoMaker integrado**: cuando una categoría se satura, el sistema ejecuta tres pasos de síntesis:
1. **Generate**: integra los 4 análisis paralelos (patrones de comportamiento, propiedades, causas, consecuencias) en un memo unificado.
2. **Simplificación de variaciones**: produce tablas de doble entrada para dimensiones correlacionadas.
3. **Búsqueda de correlaciones**: cruza las tablas y construye matrices 2×2 con tipologías basadas en evidencia, citando identificadores de entrevistados dentro de las celdas.

---

### 6.4 El panel de saturación — cuatro señales, no una

Mientras el loop corre, el sistema mantiene un panel con cuatro señales. No dependemos de una sola métrica:

1. **La señal matemática** (barata, rápida): ¿los nuevos incidentes todavía están cambiando el perfil de embedding de la categoría? Si la varianza inter-incidente es alta, ni siquiera gastamos en verificación cualitativa — claramente no está saturada.
2. **La señal cualitativa** (cara, solo si la matemática sugiere estabilidad): el `did_state_expand` del critic FLASH. Tres iteraciones consecutivas sin expansión = señal verde.
3. **La cobertura**: ¿todos los extremos de cada propiedad documentada en el paradigm_state tienen al menos un caso? Si tu propiedad "Profundidad" tiene 8 casos en el extremo "profundo" y 0 en "superficial", no está saturada — necesitás muestrear el extremo faltante.
4. **La integración**: ¿la categoría está conectada a otras categorías del sistema reducido? Una categoría aislada, por más densa que sea, no puede estar saturada porque no sabemos cómo se relaciona con el resto del modelo.

Solo cuando las cuatro señales están en verde, la categoría está saturada.

Cuando pedís "Sync gaps", el SaturationGapAnalyzer corre 4 chequeos en paralelo: rolling_std sobre embeddings de incidentes (señal matemática), ventana de 5 iteraciones sobre paradigm_state (señal cualitativa), COUNT de segmentos por extremo de cada propiedad (cobertura), y categorías sin conceptual_relationships (integración).

---

### 6.5 Cuarto acto — Database A y Database B

Cuando todas las categorías con puntaje ≥4 están saturadas, el sistema construye dos bases de datos relacionales que son el output concreto de la codificación selectiva:

**Database A — Nodos planos**: cada constructo del sistema reducido se aplana en un nodo con `entity_type` (core_category, related_category, secondary_code), definición integrada, propiedades documentadas, y una nota de muestreo teórico que registra qué extremos fueron muestreados y cuáles quedaron pendientes.

**Database B — Edges**: se establecen relaciones entre los nodos de Database A, priorizando las que conectan códigos secundarios al core concern. Cada edge tiene un `relationship_type` (is_a_strategy_for, is_a_condition_of, is_a_consequence_of, co-occurs_with) y una `provisional_rationale` que cita la evidencia.

Ambas bases pasan por su propio ciclo proposer→critic, y vos confirmás cada una.

---

### 6.6 Muestreo teórico guiado por propiedades

Cuando una propiedad tiene un extremo vacío, el TheoSampler no te dice "buscá más documentos con tal metadata". Te dice: *"Tu propiedad 'Profundidad' tiene el extremo 'superficial' vacío. ¿Querés que busque en el corpus segmentos que muestren integración superficial de IA?"*. Si encuentra, te los muestra para codificar. Si no encuentra, te sugiere qué tipo de caso recolectar y te redacta una pregunta de entrevista.

Y aquí hay un detalle importante: el TheoSampler **no corre al inicio** de la codificación selectiva. Corre **bajo demanda**, solo cuando una categoría no satura con los datos existentes y el sistema reducido indica que el vacío es teóricamente relevante. Esto es muestreo teórico glaseriano genuino: dirigido por la teoría emergente, no por un plan pre-establecido.

---

### 6.7 Resumen del flujo de codificación selectiva

```
Fase A: Confirmación del Patrón de Interés y Categoría Central
  [Guardrails: 1 concern confirmado + todas las categorías con concern_label]
  A1. main_concern_proposer (PRO) → A2. main_concern_critic (PRO) → 🛑 HITL
  [Maturity gate: 3 saturadas + 2 relaciones + 3 vinculadas al patrón]
  A3. core_emergence_proposer (PRO) → A4. core_emergence_critic (FLASH) → 🛑 HITL

Fase B: Selective Reduction
  B1. selective_reduction_proposer (PRO) → B2. selective_reduction_critic (PRO) → 🛑 HITL

Fase C: Core Saturation Loop (por categoría ≥4 × documento)
  C1. core_saturation_proposer (PRO) → C2. core_saturation_critic (FLASH)
  → loop hasta 3 its sin did_state_expand → 🛑 HITL
  → [si no satura] TheoSampler (bajo demanda) → nuevos docs → repetir

Fase D: Database A/B
  D1. database_a_proposer (PRO) → D2. database_a_critic (PRO) → 🛑 HITL
  D3. database_b_proposer (PRO) → D4. database_b_critic (PRO) → 🛑 HITL

Fase E: Global Saturation Check → 🛑 HITL final
```

---

## 7. La categoría central — cuando todo empieza a tener sentido

Hay una distinción importante que el sistema hace y que vale la pena entender: **el patrón de interés y la categoría central no son lo mismo**.

El **patrón de interés** (main concern) es la tensión recurrente que los participantes intentan resolver. Es un gerundio: "Manteniendo relevancia profesional", "Negociando visibilidad algorítmica". Responde a la pregunta: *¿qué es lo que esta gente está tratando de resolver continuamente?*

La **categoría central** (core category) es el concepto del sistema de códigos que mejor explica **cómo** los participantes procesan ese patrón de interés. También es un gerundio, pero viene del sistema de categorías existente — no se inventa de cero. Responde a: *¿cuál de nuestras categorías captura la forma principal en que procesan esa preocupación?*

En la práctica: el patrón de interés podría ser "Manteniendo relevancia profesional ante la amenaza de obsolescencia". La categoría central podría ser "Escaneando el horizonte de amenazas" — porque es la categoría que mejor explica cómo los periodistas procesan esa preocupación. El patrón de interés es el PROBLEMA. La categoría central es la RESPUESTA.

El primer acto de la codificación selectiva (6.1) ya confirmó formalmente el patrón de interés. Ahora necesitamos encontrar, entre nuestras categorías, cuál es la central.

### 7.1 No se "detecta" — emerge de las hipótesis acumuladas

La categoría central no es la que aparece más veces. No es la que tiene más incidentes. Es la que **conecta** con todas las demás, la que **explica** la mayor variación, la que **procesa** el patrón de interés de una manera que ninguna otra categoría logra.

Y no se "detecta" con un algoritmo. **Emerge.** Pero no emerge del vacío — emerge de las **hipótesis acumuladas** que los Synthesizers fueron construyendo batch a batch durante las pausas de cada tres documentos (§4.5). Cada hipótesis documenta una relación observada entre categorías. La categoría con más conexiones en ese grafo de hipótesis — la que aparece como nodo central una y otra vez — es la candidata más fuerte. No porque "aparezca más", sino porque **el sistema ya documentó, incidente por incidente, que otras categorías giran a su alrededor**.

Pero solo puede emerger cuando hay suficiente masa crítica.

### 7.2 Dos guardrails antes de empezar

Antes de siquiera proponer candidatos a categoría central, el sistema verifica dos condiciones de forma **determinística** (sin LLM, consultando la DB):

1. **¿Hay exactamente UNA preocupación confirmada?** Si el investigador todavía tiene múltiples preocupaciones seleccionadas del open coding, el sistema no avanza. La categoría central necesita un único patrón de interés como ancla.
2. **¿Todas las categorías tienen `concern_label`?** Si hay categorías sin vincular a una preocupación, el sistema te pide que las asignes o las descartes. Una categoría sin preocupación es una categoría sin propósito teórico.

Estos dos guardrails son binarios. Si alguno falla, el sistema te lo dice con precisión y no avanza hasta que lo resuelvas.

### 7.3 ¿Hay suficiente masa crítica?

Superados los guardrails, el sistema verifica que el proceso haya avanzado lo suficiente para que la categoría central pueda emerger con sentido. No se trata de thresholds numéricos fijos — se trata de condiciones cualitativas:

- Completaste al menos un lote de síntesis cross-document (las categorías ya pasaron por el proceso de unificación).
- Existen hipótesis que conectan categorías entre sí — sin conexiones no hay grafo, y sin grafo la centralidad no significa nada.
- El patrón de interés está confirmado (elegiste UNA preocupación como ancla).

Si falta algo, el sistema te lo dice y te sugiere qué hacer: seguir recolectando datos, ejecutar otra ronda de síntesis, o refinar tus hipótesis. No hay números mágicos — hay criterios que vos evaluás.

**Implementación:** chequeo SQL determinístico, sin LLM, que verifica condiciones mínimas de progreso.

### 7.4 El flujo de emergencia — proposer → critic → HITL

Cuando los guardrails pasan y el gate se abre, el sistema aplica el mismo ritmo de siempre, pero con una variación importante: el critic de esta etapa evalúa **intercambiabilidad**, y por eso corre en FLASH.

**Proposer** (`core_emergence_proposer`, agente PRO): recibe el patrón de interés confirmado, todas las categorías del sistema reducido, y — esto es lo nuevo — **el grafo completo de hipótesis acumuladas**. Usa ese grafo para rankear candidatos: la categoría con más conexiones entrantes y salientes en las hipótesis es la candidata más fuerte. Evalúa cada candidata con criterios glaserianos: centralidad (¿cuántas otras categorías conectan con esta según las hipótesis?), poder unificador (¿explica por qué los participantes hacen lo que hacen?), frecuencia con variación (¿aparece en múltiples documentos con matices?), y grab teórico (¿genera "aha moments" al conectarla con otras?). Propone una lista priorizada de candidatos. Solo puede proponer categorías que YA EXISTEN en el sistema — no inventa nuevas.

**Critic** (`core_emergence_critic`, agente **FLASH**): aquí está la novedad. El critic no evalúa grounding abstracto — evalúa **intercambiabilidad de incidentes**. Para cada candidato, toma sus incidentes en diferentes documentos y pregunta: ¿son intercambiables? ¿El incidente en el documento A y el incidente en el documento B cuentan la misma historia de comportamiento? Si son intercambiables, la categoría es sólida (verdict: valid). Si hay variaciones importantes que la definición no captura (refine). Si revelan patrones distintos (split — esta categoría debería dividirse).

Esta es una tarea estructurada con criterios claros, por eso corre en FLASH. Comparar incidentes para ver si son intercambiables es más parecido a un diff que a una generación teórica.

**Vos**: ves los candidatos rankeados por fuerza en el grafo de hipótesis, sus puntajes de intercambiabilidad, el theoretical grab de cada uno. Y **seleccionás UNA**. Una sola. Esa decisión **desbloquea** el resto de la codificación selectiva: el sistema reducido, el loop de saturación, las Databases A y B — todo se organiza alrededor de la categoría que elegiste.

### 7.5 La categoría central puede cambiar

Más adelante, en el Theoretical Playground, mientras elaborás relaciones y absorbés ghosts, puede pasar que un blob crezca tanto que supere al core actual. El sistema te lo sugiere: *"Este blob tiene 7 conexiones, el core actual tiene 5. ¿Promover?"*. El core anterior no se pierde — queda registrado en el historial como lo que fue.

---

## 8. Theoretical Coding — cuando las piezas se integran

Llegaste hasta acá. Tenés categorías saturadas, una categoría central, relaciones documentadas, memos de hipótesis, propiedades emergentes. Ahora toca la parte más creativa: **integrar todo en un modelo teórico coherente**.

En la tradición de Glaser, esto se hacía imprimiendo los memos, desparramándolos sobre una mesa grande, y moviéndolos de un lado a otro hasta que una estructura emergía. Nuestro sistema te da un **ecosistema conceptual vivo** — un lienzo oscuro donde tus categorías son manchas orgánicas (blobs) que respiran, tus relaciones son tendriles que se engrosan con la evidencia, y tus hipótesis no conectadas son fantasmas translúcidos que flotan en los márgenes esperando ser absorbidos.

### Tus herramientas: los códigos teóricos

Tenés 12 lentes analíticos para organizar los memos. No son configuraciones del sistema — son **tus herramientas**. Cada una tiene una lógica de evaluación que podés **inspeccionar** (un botón que dice "▶ VER LÓGICA") y **ajustar** ("para este test quiero ≥5 documentos, no ≥3"). Y podés crear nuevas.

Los 12 lentes son: Proceso (¿en qué orden ocurren?), Causal (¿qué causa qué?), Oposición (¿son polos opuestos?), Tipología (¿qué tipos emergen?), Jerarquía (¿qué es más central?), Matriz 2×2 (¿qué dos dimensiones organizan todo?), Consecuencias (¿qué produce actuar?), Estrategias (¿qué estrategias comparten?), Condición estructural (¿qué condiciones estables moldean el fenómeno?), Contingencia (¿qué condiciones variables lo modifican?), Covarianza (¿qué varía junto?), e Intercambiabilidad (¿son la misma categoría?).

### Cómo funciona

Arrastrás dos blobs juntos. El sistema te pregunta: *"¿Qué tipo de relación sentís que hay?"* — y te muestra los 12 lentes. Elegís uno. El sistema busca en todo el corpus evidencia que apoye (convergencia) y que desafíe (divergencia) esa relación. Un tendril aparece entre los blobs.

Si hay datos divergentes, el tendril muestra **fisuras doradas**. No son errores — son oportunidades. Hacés clic en una fisura y el sistema te muestra el incidente que no encaja: *"07_Carlos integró ANTES de analizar. ¿Cómo expandimos la relación para acomodar esto?"*. Podés agregar una condición ("excepto bajo urgencia laboral"), crear una ruta alternativa, o acotar la relación. La relación se vuelve **más rica**, no se descarta.

### El Sorting Log

Cada vez que probás una familia teórica, el sistema registra el intento: cuántos grupos se formaron, cuáles quedaron sin hogar, cuáles fueron forzados, cuáles son delgados (poca evidencia). Probás Proceso: 4 grupos, 1 homeless. Probás Tipología: 3 grupos, 2 homeless. Probás Causal: 5 grupos, 0 homeless. Causal tiene mejor score. Pero notás que el grupo "Percibir→Analizar" aparece en Proceso Y en Causal — eso es una señal de que es robusto.

Podés crear híbridos: "Causal como esqueleto, Tipología como capa de variación". Los grupos que aparecen en múltiples intentos son candidatos a capítulos de tu informe.

Un agente rápido pre-clasifica tus memos apenas entrás al Playground: "Este memo tiene afinidad con Causal (0.85) y Proceso (0.70)". Así sabés por dónde empezar.

### ¿Cuándo se usa RAG en el sorting?

Casi nunca. El sorting opera sobre **memos**, que ya son contenido sintetizado. Solo en tres momentos se vuelve a los datos crudos:

- Cuando un grupo es muy delgado (< 3 memos): *"¿Buscamos más evidencia en el corpus para este grupo?"*
- Cuando dos memos se contradicen: *"El memo H23 dice A→B pero el memo H31 dice B→A. ¿Verificamos contra los datos?"*
- Cuando creés haber encontrado la integración final: el sistema verifica cada relación contra el corpus y te da un índice de ajuste global.

El resto del tiempo, el sorting es estructural — rápido, sin RAG, sin costo de LLM.

### El motor de recomendaciones

Al entrar al Playground, el sistema te muestra cuatro tipos de sugerencias, ranqueadas por impacto:

1. **Conexiones**: pares de categorías que co-ocurren en los mismos documentos pero no tienen relación documentada. "¿Querés explorar si 'Analizando' y 'Decidiendo' están relacionadas? Aparecen juntas en 7 de 9 documentos."
2. **Ghosts**: memos de hipótesis que no fueron absorbidos por ninguna categoría. El `ghost_blob_mapper` (PRO) los asigna a categorías candidatas. Ves el memo como un fantasma translúcido flotando cerca de la categoría sugerida. Lo arrastrás para absorberlo.
3. **Renombres**: categorías con ≥3 versiones de definición o que duplicaron sus propiedades. El `rename_suggester` (PRO) propone 3 niveles. Ves el RenameModal y elegís.
4. **Sampling zones**: capas del gradiente de una propiedad que no están cubiertas por ningún caso. "La propiedad 'Profundidad' tiene 0 casos superficiales. ¿Muestreamos?"

### Cómo funciona la absorción de ghosts

Arrastrás un ghost-blob a una categoría. El sistema registra una nueva versión de la definición de esa categoría (ahora enriquecida con el memo absorbido). Si es la tercera versión, el `rename_detector` se activa y te sugiere un renombre. Cada absorción es una **decisión teórica**: estás diciendo "este insight pertenece a esta categoría". El sistema lo registra en el historial de definiciones.

### Las 12 familias — siempre disponibles

Los 12 lentes teóricos no los creás vos — el sistema los **siembra** al iniciar (`TheorySeeder`). Son 12 registros en `theoretical_codes` con su lógica de evaluación inspeccionable y ajustable. Podés crear nuevos, pero los 12 clásicos están siempre ahí, listos para que arrastres el primero.

---

## 9. La elaboración conceptual — no se "testea", se elabora

Hay una diferencia fundamental entre cómo funciona nuestro sistema y cómo funcionaría un sistema positivista. Nosotros no "testeamos" hipótesis. No decimos "la hipótesis es verdadera o falsa". Eso no tiene sentido con poblaciones pequeñas.

Nosotros **elaboramos** relaciones conceptuales. Un dato divergente no refuta una relación — **la expande**. Un memo no se verifica o falsea — **se modifica, se densifica, se expande**. Las categorías no tienen nombres fijos — **cambian de nombre cuando su definición crece**.

Esta filosofía está en todos lados. En el vocabulario del sistema (nunca verás "accept/reject", siempre "converge/diverge/expand"). En la visualización (los tendriles nunca se rompen — muestran fisuras doradas que invitan a expandir). En el ciclo de vida de las categorías (tres niveles de renombre, del conservador al transformador).

---

## 10. Cuando algo no encaja — el sistema de re-especificación

A veces, una decisión que tomaste en un nivel temprano resulta ser incorrecta a la luz de lo que descubriste después. Un incidente que clasificaste como baseline quizás era interpreted. Una categoría que creías sólida quizás tiene incidentes mal asignados. Una propiedad que definiste con dos polos quizás en realidad es unipolar.

El sistema no te deja solo con esto. Un agente (el **ReSpecAgent**) monitorea constantemente las señales de que algo podría necesitar revisión: incidentes marcados como ambiguos, etiquetas que el crítico rechazó, relaciones con datos divergentes sin resolver, memos que no encajan en ninguna familia teórica, ejes de comparación vacíos.

Cuando acumula suficientes señales, te lo dice. Y lo más importante: te permite **re-especificar** en cualquier dirección. Si una relación en el nivel teórico no integra bien, podés bajar al nivel de las categorías y preguntar: "¿estas categorías están bien definidas?". Si una categoría no satura, podés bajar al nivel de los incidentes: "¿estos incidentes fueron bien extraídos?". Si un incidente no encaja en ningún grupo, podés bajar al dato crudo: "¿este segmento fue bien clasificado?".

### El botón que brilla

Al completar cada etapa — open coding, selective coding, y durante el theoretical coding — un botón púrpura aparece en la esquina inferior derecha. Brilla cuando hay sugerencias de revisión. No es obligatorio clickearlo. Pero está ahí, pulsando suavemente, recordándote que siempre hay oportunidad de refinar.

---

## 11. De las pilas al papel — la redacción natural

Las pilas de memos están ordenadas. El Sorting Log tiene registro de cada intento: qué familias teóricas probaste, cuáles grupos se formaron, cuáles memos quedaron sin hogar. Ahora toca **escribir**. Y en CGT, escribir no es un acto separado del análisis — es su continuación natural.

### 11.1 La filosofía: escribir es seguir analizando

Glaser insistía en que la redacción no es "comunicar resultados" — es **seguir comparando**. Cuando escribís, descubrís que dos memos que creías conectados en realidad no encajan. O que un concepto necesita un nombre mejor. O que falta evidencia para una afirmación que dabas por sentada. El sistema te acompaña en este descubrimiento.

Las reglas son pocas pero estrictas:

- **Escribí desde las pilas, nunca desde cero.** Cada sección de tu documento es la transcripción hilada de una pila de memos ordenados. El sistema te muestra la pila a la izquierda y el editor a la derecha.
- **Tiempo presente para conceptos, pasado para ejemplos.** "El escaneo del horizonte de amenazas lleva a los periodistas a recalibrar sus rutinas" (concepto, presente). "Carlos describió que primero analiza la herramienta y luego decide" (ejemplo, pasado).
- **Relacioná conceptos, no personas.** "La percepción de amenaza modula la profundidad del análisis" — no "los periodistas jóvenes se sienten amenazados".
- **Dosis de ilustración moderada.** Una cita por afirmación basta. No ahogues el poder explicativo en descripciones.

### 11.2 El flujo: proposer → critic → HITL para cada sección

El sistema no te suelta la mano. Para cada pila de memos, el mismo ritmo de siempre:

**Proposer** (`natural_writer`, agente PRO): recibe la pila de memos ordenados (con sus relaciones, su evidencia, su familia teórica asignada) y redacta un borrador. No busca estilo — busca **construcción teórica**. Escribe rápido, sin pulir. Prioriza que los conceptos estén correctamente relacionados. Usa tiempo presente para conceptos, pasado para ejemplos. Inserta referencias @ automáticamente.

**Critic** (`writing_critic`, agente PRO): evalúa el borrador contra las reglas CGT:
- ¿Todas las afirmaciones conceptuales están en tiempo presente? ¿Los ejemplos en pasado?
- ¿Se relacionan conceptos entre sí, o se describen personas?
- ¿Las citas ilustran sin dominar? ¿Hay más de una cita por afirmación?
- ¿El texto fluye desde los memos o se inventó contenido nuevo?
- ¿Hay afirmaciones sin respaldo en la pila de memos?

Emete SAT (la sección cumple), MOD (necesita ajustes específicos), o FORCED (hay contenido inventado sin respaldo).

**Vos**: ves el borrador a la derecha, la pila de memos a la izquierda. El critic te marca: afirmaciones sin respaldo en naranja, cambios de tiempo verbal en azul, descripciones de personas en amarillo. Editás directamente. Cuando terminás, el sistema registra la versión en el historial de la sección.

### 11.3 El índice de ajuste global

Cuando todas las secciones están escritas, el sistema calcula un **índice de ajuste** para el documento completo: ¿cuántas afirmaciones tienen respaldo directo en un memo? ¿Cuántas citas se usaron? ¿Cuántas afirmaciones quedaron sin respaldo? No es una calificación — es un diagnóstico. Te dice: *"El 78% de tus afirmaciones tienen respaldo directo. Las secciones 3 y 5 concentran el 60% de las afirmaciones sin respaldo. ¿Las revisamos?"*

### 11.4 Gap feeling durante la escritura

Aquí ocurre algo que Glaser documentó: escribiendo descubrís gaps que el sorting no reveló. Una transición entre dos conceptos que parece débil. Una propiedad que solo aparece en un extremo. Una categoría que merecería ser central pero le falta evidencia.

El **Gap Feeler** (`gap_feeler`, agente FLASH) monitorea tu escritura en segundo plano. Detecta: afirmaciones sin memo de respaldo, transiciones entre secciones sin evidencia de conexión, conceptos mencionados una sola vez, propiedades con un solo polo documentado. Cuando acumula señales, te lo susurra: *"La conexión entre 'Calibrando percepción de riesgo' y 'Modulando profundidad de análisis' aparece en tu texto pero no tiene memo que la respalde. ¿La exploramos?"*

Podés hacer clic en el gap y el sistema te ofrece: buscar evidencia en el corpus, marcar como limitación, o activar el TheoSampler para recolectar datos específicos.

---

## 12. El diálogo con la literatura — los libros como datos

En la CGT clásica, la literatura no se lee antes del análisis. Se lee **después**, cuando tu teoría ya emergió. Y no se lee como autoridad — se lee como **más datos** que someter al mismo método de comparación constante.

### 12.1 La filosofía: la literatura no valida, dialoga

Tu teoría no necesita "apoyo" de la literatura. Ya está respaldada por los datos. Lo que buscás es **emergent fit**: ¿cómo tu teoría amplía, modifica, integra o trasciende lo que ya se dijo?

No es: "Mi hallazgo coincide con Bourdieu (1984), lo cual lo valida." Eso es tratar la literatura como autoridad.

Es: "Bourdieu (1984) describió la distinción como marcador de clase. Mi teoría muestra que los periodistas no solo se distinguen — escanean activamente el horizonte en busca de amenazas a su distinción, y recalibran antes de que la amenaza se materialice. Esto extiende el concepto de distinción añadiéndole una dimensión prospectiva que la literatura no capturó."

### 12.2 El flujo: la literatura como incidentes

**Proposer** (`literature_comparer`, agente PRO): recibe tu teoría completa (categoría central, categorías relacionadas, hipótesis, propiedades) y fragmentos de literatura relevante que el sistema busca por similitud semántica con tus categorías. Trata cada fragmento como un **incidente**: lo codifica con tus categorías, lo compara contra tus propiedades, evalúa si converge o diverge.

Para cada categoría tuya, genera:
- **Extiende**: la literatura describe algo similar pero tu teoría añade una dimensión no documentada.
- **Modifica**: la literatura dice algo parecido pero tu teoría muestra que funciona distinto en tu población.
- **Integra**: la literatura describe un fenómeno que tu teoría subsume como caso particular.
- **Trasciende**: la literatura no aborda este aspecto — es una contribución original de tu teoría.

**Critic** (`literature_critic`, agente PRO): evalúa el diálogo:
- ¿El proposer está forzando coincidencias donde no las hay?
- ¿Está tratando la literatura como autoridad en lugar de como dato?
- ¿Las extensiones/modificaciones son genuinas o son diferencias triviales de vocabulario?
- ¿Hay literatura relevante que el sistema no encontró y deberías revisar manualmente?

**Vos**: ves una tabla comparativa. Cada categoría tuya en las filas. Cuatro columnas: Extiende, Modifica, Integra, Trasciende. Cada celda tiene fragmentos de literatura y la evaluación del critic. Decidís qué integrar en tu documento y cómo.

### 12.3 La integración: notas al pie, no interrupciones

Cuando integrás literatura en tu documento, el sistema te ayuda a mantener el flujo argumentativo. La integración erudita va en **notas al pie** — no interrumpas la voz de tu teoría para debatir con autoridades. Una mención breve en el texto ("Como documentó Goffman (1959)...") basta; el detalle va abajo.

El sistema te sugiere automáticamente notas al pie para cada celda de la tabla que aceptaste. Las inserta donde detecta la primera mención del concepto relacionado en tu texto.

---

## 13. De la teoría a la acción — haciendo la teoría aplicable

Una Classic Grounded Theory no necesita ser "aplicada" artificialmente. **Ajusta naturalmente** porque emergió de cómo los participantes resuelven su preocupación principal. Pero podés —y deberías— explicitar las implicaciones prácticas para que otros puedan usarla.

### 13.1 La filosofía: la teoría ya funciona

No necesitás traducir tu teoría a "recomendaciones prácticas" como si fuera un producto separado. La teoría **es** práctica: describe lo que la gente ya hace para resolver su problema. Tu trabajo es identificar las palancas — los conceptos de tu teoría que alguien puede manipular para intervenir.

### 13.2 El flujo: identificando variables de control y acceso

**Proposer** (`applicability_engine`, agente PRO): recibe tu teoría completa. Para cada categoría y cada hipótesis, identifica:
- **Variables de control**: conceptos de tu teoría que un profesional puede manipular directamente. Ej: "La frecuencia de escaneo del horizonte" — un editor puede modificarla cambiando las rutinas de la redacción.
- **Variables de acceso**: conceptos que no se manipulan directamente pero que condicionan el fenómeno. Ej: "La percepción de amenaza" — no se puede ordenar a alguien que se sienta amenazado, pero se puede acceder a ella indirectamente.
- **Contextos de aplicación**: ¿en qué condiciones tu teoría predice que la intervención funcionará? ¿En cuáles no?

Para cada palanca, redacta una **directriz de intervención** en lenguaje llano, no académico. "Si querés que tu equipo de periodistas integre IA más profundamente: (1) reducí la percepción de amenaza mostrando casos donde la IA amplificó el periodismo en lugar de reemplazarlo, (2) creá espacios de experimentación sin consecuencias laborales..."

**Critic** (`applicability_critic`, agente PRO): evalúa las directrices:
- ¿La directriz se desprende genuinamente de la teoría o es un consejo genérico?
- ¿Identifica correctamente qué es control y qué es acceso?
- ¿Reconoce los límites de aplicabilidad? ¿O promete más de lo que la teoría respalda?
- ¿El lenguaje es accesible para un no-académico?

**Vos**: ves las directrices propuestas, la evaluación del critic, y las editás. El sistema te recuerda: *"Esta directriz asume que la percepción de amenaza es modificable. ¿Tu teoría respalda eso?"*

### 13.3 Proyectar, no resumir

El final de tu documento no es un resumen. Es una **proyección**. El sistema te ayuda a redactar tres elementos finales:

1. **Implicaciones para otras áreas sustantivas**: ¿en qué otros contextos tu categoría central podría explicar patrones de comportamiento? Si "Escaneando el horizonte de amenazas" funciona para periodistas, ¿funciona para médicos frente a la IA diagnóstica? ¿Para abogados frente a la revisión automatizada de contratos? El sistema sugiere áreas por similitud estructural (misma preocupación, distinta población).

2. **Agenda de investigación futura**: no es una lista de "limitaciones". Son preguntas que tu teoría **abre**. "¿El escaneo del horizonte se intensifica en profesiones con mayor regulación estatal?" "¿La propiedad 'Profundidad' tiene el mismo gradiente en poblaciones con distinto nivel educativo?"

3. **Directrices de intervención**: las palancas que identificaste, organizadas por actor (para editores, para periodistas individuales, para diseñadores de IA).

---

## 14. Trazabilidad — de la teoría al dato

Cada afirmación teórica en tu modelo final debe poder rastrearse hasta el dato que la originó. El sistema mantiene una cadena de referencias:

```
Código teórico → Relación conceptual → Categoría → Incidente → Segmento → Cita textual
```

En cualquier momento, desde cualquier nivel, podés hacer drill-down: "Esta relación de proceso entre Analizar e Integrar → ¿qué incidentes la respaldan? → mostrame las citas exactas → ¿de qué documentos? → ¿de qué entrevistados?".

Mientras editás un memo, podés invocar **@** para buscar rápidamente en todo el sistema: escribís `@analizando patrones` y el sistema te muestra resultados agrupados por jerarquía — primero las categorías que coinciden (púrpura), después los incidentes (verde), después las citas clave (amarillo). Un clic y la referencia se inserta en tu memo.

---

## 15. El investigador en el centro

En cada decisión teórica importante, el sistema se detiene y te pregunta. No es una cortesía — es un requisito metodológico. La CGT no puede ser automatizada porque el juicio teórico es humano.

Los momentos donde el sistema te pide tu decisión son:

**Durante el open coding y la síntesis:**
- **Pausa cada 3 documentos** (§4.5) — cuatro decisiones integradas:
  - ¿Aceptás, modificás o rechazás las categorías unificadas? (selección múltiple)
  - ¿Qué preocupaciones seleccionás? (múltiples hasta el batch final, luego UNA)
  - ¿Mantenés la población unificada o separás variantes? (múltiples hasta el final)
  - ¿Aceptás la recomendación de estilo de codificación? (binario)

**Durante la codificación selectiva (Fase 5b):**
- **¿Confirmás este patrón de interés?** — después de main_concern_proposer → main_concern_critic (A1+A2)
- **¿Confirmás esta categoría central?** — después de core_emergence_proposer → core_emergence_critic (A3+A4)
- **¿Confirmás el sistema reducido?** — después de selective_reduction_proposer → selective_reduction_critic (B1+B2). Ves qué se descartó, qué se fusionó, y decidís.
- **¿Esta categoría está saturada?** — después de 3 iteraciones sin did_state_expand en el loop de saturación (C1+C2). Una por cada categoría.
- **¿Confirmás los nodos?** — después de database_a_proposer → database_a_critic (D1+D2)
- **¿Confirmás las relaciones?** — después de database_b_proposer → database_b_critic (D3+D4)
- **¿Cerramos la codificación selectiva?** — después del global saturation check (Fase E)

**Durante el theoretical coding:**
- **¿Aceptás este renombre?** (cuando una categoría crece)
- **¿Promovés este blob a core?** (si supera al core actual)
- **¿Cómo resolvés este gap?** (cargar datos, buscar en corpus, marcar límite)
- **¿Absorbés este memo en esta categoría?** (arrastrar ghost-blob)
- **¿Cómo expandís esta relación?** (clic en fisura dorada)

**Durante la redacción natural (Fase 6a):**
- **¿Aceptás este borrador de sección?** — después de natural_writer → writing_critic. Editás directamente sobre el texto marcado.
- **¿Exploramos este gap detectado durante la escritura?** — el Gap Feeler te susurra. Decidís si buscar evidencia, marcar como limitación, o muestrear.
- **¿El índice de ajuste global es suficiente?** — antes de pasar a literatura

**Durante el diálogo con la literatura (Fase 6c):**
- **¿Qué celdas de la tabla integrás?** — después de literature_comparer → literature_critic. Ves la tabla Extiende/Modifica/Integra/Trasciende y decidís.
- **¿Aceptás las notas al pie sugeridas?** — el sistema las propone, vos las editás.

**Durante la aplicabilidad (Fase 6d):**
- **¿Confirmás estas directrices de intervención?** — después de applicability_engine → applicability_critic
- **¿Estas proyecciones a otras áreas son razonables?** — el sistema sugiere, vos validás.

**Cierre:**
- **¿Revisás antes de avanzar?** (stage-gate review)
- **¿Damos el estudio por cerrado?** (HITL final)

En el Theoretical Playground, el HITL es más fluido: arrastrar, hacer clic, absorber — el sistema responde en tiempo real. En las fases de redacción y literatura, el HITL es editorial: editás sobre el texto, aceptás o rechazás sugerencias. En la codificación selectiva, cada gate HITL es un punto de pausa donde el pipeline no avanza sin tu confirmación.

### 15.1 Qué pasa cuando decidís — la cascada

Cuando modificás un output (cambiás una categoría, reescribís una hipótesis, ajustás el main concern), el sistema **no solo guarda**. Limpia las tablas que dependen de ese output y reinicia el pipeline desde el nodo correcto:

| Modificaste | Se reinicia desde |
|-------------|-------------------|
| Un código abierto | `batch_code` |
| Una hipótesis | `generate_hypotheses` |
| El main concern | `find_core_concern` |
| El process identifier | `segment_and_index` |
| Una categoría | `batch_code` |
| Database A | `prepare_playground` |
| Una relación conceptual | `prepare_playground` |

Cada modificación se registra en `output_modifications` (quién, qué, cuándo, veredicto original del critic). Mientras se recalcula, el frontend recibe actualizaciones en vivo vía SSE — Redis pub/sub → eventos en tiempo real sin refresh. Esto es lo que hace que el HITL no sea un obstáculo sino una **conversación**: modificás, el sistema recalcula solo lo necesario, y vos ves el progreso.

---

## 16. El viaje completo

```
Configuración inicial
  │  Describís tu población. El sistema la generaliza.
  │  Elegís qué tipo de patrón buscás. El sistema ajusta sus lentes.
  │
  ▼
Open Coding (por documento)
  │  Cada segmento se clasifica (oro, plata, bronce, anomalía) en batch PRO.
  │  Extracción unificada: incidentes + patrón individual en un solo llamado.
  │  Cada 3 documentos: pausa de 4 actos (Synthesizers + Critic + HITL).
  │
  ▼
Síntesis Cross-Document (por batch)
  │  Incidentes del batch se agrupan por patrón (Agrupador, sin ver previas).
  │  Los grupos se etiquetan uno por uno (Etiquetador ↔ Crítico, feedback sin veredictos).
  │  Grounding vía vínculos incidente→segmento (sin embeddings).
  │
  ▼
Codificación Selectiva — Fase A: Confirmación del Patrón de Interés
  │  A1. main_concern_proposer (PRO): sensa con categorías + hipótesis.
  │  A2. main_concern_critic (PRO): evalúa SAT/MOD/FORCED.
  │  🛑 HITL: confirmás UNA preocupación.
  │  [Guardrails: 1 concern confirmado + todas las categorías con concern_label]
  │  [Maturity gate: 3 saturadas, 2 relaciones, 3 vinculadas al patrón]
  │  A3. core_emergence_proposer (PRO): rankea por grafo de hipótesis.
  │  A4. core_emergence_critic (FLASH): test de intercambiabilidad.
  │  🛑 HITL: seleccionás UNA categoría central → desbloquea el resto.
  │
  ▼
Codificación Selectiva — Fase B: Selective Reduction
  │  B1. selective_reduction_proposer (PRO): descarta y fusiona.
  │  B2. selective_reduction_critic (PRO): evalúa descartes y fusiones.
  │  🛑 HITL: confirmás el sistema reducido.
  │
  ▼
Codificación Selectiva — Fase C: Core Saturation Loop
  │  Por cada categoría ≥4 × cada documento:
  │    C1. core_saturation_proposer (PRO): propone expansiones.
  │    C2. core_saturation_critic (FLASH): ¿expansión genuina?
  │    → loop hasta 3 its sin did_state_expand
  │    🛑 HITL: confirmás saturación de esta categoría.
  │    → [si no satura] TheoSampler → nuevos docs → repetir.
  │    → [al saturar] MemoMaker: Generate → Simplificar → Correlacionar.
  │
  ▼
Codificación Selectiva — Fase D: Database A/B
  │  D1+D2: nodos planos con entity_type.
  │  🛑 HITL: confirmás el sistema de nodos.
  │  D3+D4: edges con relationship_type.
  │  🛑 HITL: confirmás el sistema de relaciones.
  │
  ▼
Codificación Selectiva — Fase E: Global Saturation Check
  │  Verifica 3 condiciones. Si todas en verde:
  │  🛑 HITL: cerrás la codificación selectiva.
  │
  ▼
Theoretical Playground — Sorting
  │  Tus categorías son blobs. Tus relaciones son tendriles.
  │  Probás familias teóricas (12 lentes). Comparás intentos.
  │  Los datos divergentes expanden, no rompen (fisuras doradas).
  │  El Sorting Log registra cada intento.
  │  El cross-family synthesizer integra todo.
  │
  ▼
Redacción Natural
  │  Cada pila de memos → una sección del documento.
  │  Natural_Writer (PRO) redacta borrador.
  │  Writing_Critic (PRO) evalúa: ¿presente? ¿conceptual? ¿moderado?
  │  🛑 HITL: editás sobre el texto marcado.
  │  Gap Feeler (FLASH) detecta afirmaciones sin respaldo.
  │  → loop hasta índice de ajuste satisfactorio.
  │
  ▼
Diálogo con la Literatura
  │  Literature_Comparer (PRO): codifica la literatura como incidentes.
  │  Literature_Critic (PRO): evalúa emergent fit.
  │  🛑 HITL: ves tabla Extiende/Modifica/Integra/Trasciende.
  │  El sistema inserta notas al pie automáticamente.
  │
  ▼
Aplicabilidad
  │  Applicability_Engine (PRO): identifica variables de control y acceso.
  │  Applicability_Critic (PRO): evalúa si las directrices son genuinas.
  │  🛑 HITL: confirmás directrices y proyecciones.
  │
  ▼
Teoría integrada
     De cada proposición teórica podés bajar hasta la cita que la originó.
     La literatura dialoga con tu teoría, no la valida.
     Las directrices de intervención emergen de las palancas que tu teoría identificó.
     El sistema te acompañó, te propuso, te criticó, te mostró evidencia.
     Pero la teoría es tuya.
```

---

## Glosario de agentes

> 📋 **Fuente canónica:** El registro completo y actualizado de todos los agentes (38 agentes, tiers, estados, inputs/outputs, prompts) esta en [`AGENTES.md`](./AGENTES.md). Este glosario se ha consolidado alli como fuente unica de verdad. Cualquier discrepancia se resuelve a favor de `AGENTES.md`.

---

## 17. Referencia técnica

Este documento describe QUÉ hace el sistema. Para entender CÓMO se implementa (transiciones de estado, tracking de tareas, cancelabilidad, checkpoints de resume, optimistic locking), consultá:

- [`4-Patrones_de_desarrollo.md`](./4-Patrones_de_desarrollo.md) — los 4 patrones y su aplicación por fase
- [`CHECKLIST_CGT_REFACTOR.md`](./CHECKLIST_CGT_REFACTOR.md) — checklist de implementación (65 ítems)
- [`AGENTES.md`](./AGENTES.md) — registro canónico de agentes (38 agentes)
- [`6-ContextWindowManager.md`](./6-ContextWindowManager.md) — diseño de escalamiento de contexto
- [`secuencia_cgt.mermaid`](./secuencia_cgt.mermaid) — diagrama de secuencia del sistema objetivo
- [`Patron_Desarrollo_Maestro.md`](../Patron_Desarrollo_Maestro.md) — las 5 reglas que todo componente debe cumplir
