# Analisis cualitativo 3.0

# Sistema Integrado de Análisis Cualitativo — Casos de Uso

## Selección de Ruta de Codificación (Interruptor de todo el sistema)

Tres rutas mutuamente excluyentes gobiernan las Fases 3 a 5. Todas las fases posteriores hacen referencia a la ruta seleccionada.

| Ruta                | Interés central                                                                     | Marco                     |
| ------------------- | ----------------------------------------------------------------------------------- | ------------------------- |
| **Deductiva**       | Validar o extender un marco teórico existente                                       | MT existente              |
| **Abductiva (CGT)** | Procesos sociocognitivos; hábitos hipotéticos de comportamiento; hipótesis causales | CGT / Analítica Inductiva |
| **Inductiva**       | Emergencia temática pura; riqueza sin marco previo                                  | Ninguno                   |


Ruta CGT = Ruta Abductiva. Todas las referencias al diagrama CGT PlantUML se aplican a la rama Abductiva.

***

![](assets/5zXmTVDDEPVhJmMEm01eGDtnIgjeGQeDEs_T_ONykZ8=.png)



## Fase 0: Configuración del Sistema

**Propósito:** Establecer el contexto analítico que persiste en la ventana de contexto de la IA para todas las fases posteriores. No se codifica ni escribe nada hasta que esto esté configurado.

### 0.1 Preguntas de Investigación y Contexto de la Población

* Definir de 1 a N preguntas de investigación, cada una con:
  &#x20; \* Tipo: descriptiva / interpretativa / explicativa / relacional
  &#x20; \* Plan de análisis: qué objetivos son inductivos, cuáles deductivos
  &#x20; \* Variables asociadas (del POOL, si ya se conocen)
* Describir el contexto de la población y del campo (utilizable antes de tener datos)
* Las PI + el contexto se inyectan en la ventana de contexto de la IA en cada invocación de fase — nunca se eliminan
* Restricción bidireccional: cambiar el marco teórico requiere revisar las PI, y viceversa

### 0.2 Selección de la Ruta de Codificación

* Elegir: Deductiva / Abductiva (CGT) / Inductiva
* La selección restringe: el roster de agentes de la Fase 3, la lógica de reorganización de la Fase 4, los criterios de saturación en todas las fases
* Para CGT/Abductiva: omitir la Fase 0.3

### 0.3 Marco Teórico \[omitir para CGT]

* Inyectar RAG bibliográfico (fuentes BIBTEX + PDF/ePub)
* Seleccionar constructos: definir, relacionar, operacionalizar
* Generar una explicación teórica falsable para contrastar con los datos
* Criticar el alcance del marco — evitar categorías demasiado amplias
* Nota: los constructos pueden reorganizarse creativamente según el contexto de campo

### 0.4 POOL de Variables Iniciales

* Fuentes: esquema de metadatos, PI, marco teórico (si existe), criterios de muestreo
* El POOL es dinámico: crece durante las Fases 2 a 6
* Propósito: guía las decisiones de muestreo teórico, la postulación de relaciones, el seguimiento de la saturación
* Cada evento de división/fusión/cambio de nombre añade una nota reflexiva: *"¿Este cambio se relaciona con alguna variable del POOL?"*

### 0.5 Configuración de usuarios

* “El sistema debe soportar autenticación multi‑usuario con roles (investigador, auditor, visualizador).”
* Análisis en paralelo online con permisos.

## Fase 1: Ingesta de Datos

**Propósito:** Introducir los datos brutos en el sistema en una forma adecuada para la segmentación y el análisis.

**Equivalente n8n:** Leer PDFs del disco → Extraer texto del PDF

### 1.1 Tipos de Fuente Aceptados

| Tipo de fuente                      | Notas                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| Encuesta / BD estructurada (MAXQDA) | Extraer esquema → proponer lista de códigos desde columnas existentes        |
| Web scraping                        | Tratamiento por página o por hilo                                            |
| Redes sociales                      | Por conversación/hilo; separar interlocutores                                |
| Audio / Video (YouTube, etc.)       | Transcripción automática; marcar monólogo vs. conversación                   |
| Bibliografía (BIBTEX + PDF/ePub)    | Alimenta el RAG de la Fase 0.3; puede reingresar como nuevo dato en Fase 6.6 |
| Informes cuantitativos              | Solo contextuales, a menos que se codifiquen como documentos                 |
| Grupos focales                      | Separar moderador de participantes; marcar dinámicas de interacción          |
| Imágenes                            | Descritas automática o manualmente; tratadas como unidades de segmento       |

### 1.2 Manejo de Datos Estructurados vs. No Estructurados

**Datos estructurados:**

* Extraer esquema → proponer lista de códigos alineada con columnas/etiquetas existentes

**Datos no estructurados (predeterminado para CGT):**

* Autolimpieza: separar oraciones donde no hay puntuación
*
* Segmentar párrafos para monólogos o lenguaje especializado
* Marcar turnos de moderador/entrevistador; el investigador decide si incluir o excluir
* Opcional: IA parafrasea segmentos largos (original conservado junto a la paráfrasis)
* Generar índice estructural por documento

### 1.3 Estrategia para Volumen de Tokens

| Volumen                 | Estrategia                                                                |
| ----------------------- | ------------------------------------------------------------------------- |
| Bajo–Medio              | Ingestionar todo; procesar completamente                                  |
| Alto, no conversacional | Lotes iterativos; añadir pasada de reclasificación para residuos al final |
| Alto, conversacional    | Cada hilo independiente; interlocutores separados                         |

### 1.4 Salida

* Corpus de texto limpio e indexado
* Índice estructural por documento
* Anonimización de documentos y búsqueda de información sensible. Si se usan datos sensibles (GDPR, HIPAA), el procesamiento debe realizarse en local o con proveedores que firmen un DPA
* Marcas de moderador/entrevistador por documento
* Marcas de datos potencialmente no importantes.
* Documentos preparados para la Fase 2

***

## Fase 2: Análisis y Segmentación de Corpus

**Propósito:** Comprender la estructura del documento analíticamente antes de codificar. Producir segmentos enriquecidos listos para RAG y codificación abierta.

**Equivalente n8n:** Segmentación y clustering (por doc) → Open Coder → Resegmentar-Doc → Junta segmentos → Verificación de contexto previo → Resume contexto → Clusterizador (doc) → Insertar en BD

### 2.1 Resúmenes de Documentos y Tematización Inicial

* Generar resumen ejecutivo por documento
* Aplicar BERTopic + análisis de clases léxicas de Reinert
* Identificar *prime movers* (problemas centrales, preocupaciones motoras) por documento
* Detectar posicionamientos emergentes, tipologías y posibles metáforas

### 2.2 Enriquecimiento de Metadatos

* Construir base de metadatos enriquecible por documento
* Campos generados por IA: etiquetas de categoría, resúmenes de documentos, extracción de texto a variable
* Campos editables por el investigador: notas contextuales, marcas de inclusión/exclusión
* Anexar variables extraídas al **POOL DE VARIABLES INICIALES**
* Aplicar criterios unificados de inclusión/exclusión de la Fase 0.1

### 2.3 Informe de Adecuación del Documento (por documento)

* ¿Qué PI específica responde mejor este documento?
* Profundidad de la información contextual para el campo
* Identificación de procesos, etapas, preguntas contrafácticas en el contenido
* Posicionamientos, tipologías, metáforas que emergen del documento
* Sugerencias de memo: la IA marca pasajes como candidatos para memo inmediato

### 2.4 Informe de Crítica del Documento (por documento)

* Análisis de sesgos, intertextualidad, relaciones entre actores, coherencia entre documentos
* Clasificación del tipo de dato según Glaser por segmento:
  &#x20; \* `baseline_data` — descripción honesta y no solicitada
  &#x20; \* `properline_data` — lo que el participante cree que debería decir
  &#x20; \* `interpreted_data` — opinión forzada o provocada
  &#x20; \* `vague_data` — información activamente ocultada u oscurecida
* Mensaje de chat reflexivo: *"¿Qué sentiste cuando el entrevistado dijo X?"*
* Sugerencias de memo: la IA propone anotaciones críticas para consideración del analista

### 2.6 Lexicometría

* 3\) Léxico (método Reinert)
  * Análisis por clase - Palabras. 
    * Añadir por clase - documentos. 
  * Análisis por palabra - Clases
    * Comparación inter‑clases.
  * Clasificación-Detalle: añadir checks a todos los gráficos: Documentos, UCs, UCEs, Palabras. El donnut es lo mismo que el de abajo, pero mostrar documentos y ucs/uc tambien. Debajo añadir  \[Transiciones discursivas, Confusión semántica]. Añadir diagrama de venn triclase de palabras. Añadir Árbol de persistencia de clústeres, Scree plot
* 4\) Semántica
  * Gramatical (Tipo palabra - clases)
    * Diagramas de Categorías gramaticales, Perfil de modalización x Clases x variables
  * NER? nombres propios y tal
  * Discursivo
    * IA: Extracción de figuras retóricas (p.e., evidencialidad, metáforas) por clase. 
  * Semántico (Semántica o embeddings o UMAP de palabras (agrupadas term-stem-lemma) x clases)
    * Embeddings de palabras individuales vs agrupadas, oraciones o UCs x Clases x Variables escogidas
  * BERTOPIC con UCES x semántica, gramática, NER, discurso. Resultado de PCA o AFC (Miguel). Solo clasificación
  * Datos de calidad (ML)
* 5\) Socio-Linguística 
  * ¿Qué variables elegir primero?: RF y SHAP. Esto organiza las variables.
  * Docs por variables (donnuts)
  * Buscador de terminos + Checks para elegir variables (default todos, click en una categoría de o una var, o en todas de esa var, pero click en otra var y se reactiva) + resultados y KWIC (2 pestañas). Click en resultado o kwic:
    * Tres columnas \[1,2,2]. Filtro de variables se mantiene. En ambas: docs vertical + lector (mapa de clases arriba o abajo, horizontal). Mismo resultado, pero se puede añadir otro documento según variable.
    * Predicción de variables más importantes. Clases, topicos, terminos, pragmatica, x variables (MCA + estadisticas de terminos | grupos de palabras | tipos de palabras de clases interactiva que se active según vars elegidas). 
  * Datos de calidad
* 6\) Síntesis
  * Resumen por clase de cada paso anterior. Requiere entonces procesar y guardar cada output por clase y tópido, incluyendo calidad.
  * Relaciones entre lexico y topicos: Muestra porcentaje de contribución de clases (lo que se dice: asco) según semántica (lo que se quiere decir: emociones) bajo diferentes parámetros. Mostrar también uces y estimar térninos con mayor y menor presencia en clases semánticas. 
  * Recomendación de relaciones con columnas de comparación entre resumenes de clases. columna pequeña intermedia: es \_\_\_\_ de. Posible ayuda de IA.

### 2.5 Segmentación de texto

* Dividir o unir segmentos brutos usando: reglas gramaticales, coocurrencia, correferencia, BERTopic
* Añadir subtítulos a secciones del documento; añadir etiquetas de pregunta para transcripciones de entrevistas
* Homogeneizar la estructura de segmentos entre documentos de diferentes fuentes

**Enriquecimiento de Segmentos**

Por segmento, la IA asigna:

* Tipo de dato Glaser primario (desde 2.4)
* Procesos, patrones o temas que aborda el segmento
* *Prime movers* o preocupaciones centrales del participante en este segmento
* **Peso de diferenciación:** cuánto se desvía este segmento del resto del corpus
* **Peso de ayuda:** cuánto contribuye a responder patrones/PI identificados
* **Marca de residuo:** si el segmento no encaja en ningún patrón conocido → añadir al Búfer de Residuos

**Estructura de Almacenamiento y RAG**

* Unidad de almacenamiento: `Documento → Segmento → Frase` (máx X palabras por frase)
* Todos los segmentos enriquecidos se ingieren en el índice RAG semántico/de vectores
* Índice RAG disponible para consultas durante todas las fases posteriores
* n8n: Insertar segmentos y documentos en BD Supabase

## Fase 3: Codificación inicial

**Propósito:** Generar el primer sistema de categorías a partir de los datos. Aquí divergen tres rutas. Los agentes, la lógica y los ciclos de memo difieren según la ruta, pero todas producen los mismos artefactos de salida.

**Equivalente n8n:** Open Coder → Resegmentar-Doc → ciclo de memo cada 3 documentos → Clusterizador informado → research\_categories

**Equivalente CGT PlantUML:** Fase 1 — Flujo Natural de Codificación Abierta

### 3.0 Gestión de Contexto Previo por Documento

Antes de codificar cada documento:

* Verificar si existe contexto previo o resúmenes de documentos ya codificados
* Si existe contexto previo: el agente Resume contexto lo sintetiza y lo inyecta en el contexto de trabajo
* Los resúmenes de resultados de codificación se almacenan en memoria rodante (refrescada cada 3 documentos)
* Propósito: evitar reanálisis; permitir que cada nuevo documento se compare con la comprensión acumulada

### RUTA A: Codificación Deductiva

**3.A.1 Generación de códigos**

* Generar códigos directamente desde los constructos teóricos definidos en la Fase 0.3
* Asegurar exclusividad mutua entre categorías
* Asignar grandes bloques de texto a códigos
* Crear resúmenes de categorías iterativamente a partir de los segmentos asignados

**3.A.2 Expansión iterativa**

* Ofrecer resúmenes de subcategorías en niveles más bajos
* Expandir el esquema cuando los segmentos revelen áreas no cubiertas en el marco original
* Los nuevos códigos se añaden explícitamente; se registran como extensiones del marco

**3.A.3 Producción de memos**

* Memos de hipótesis: cómo se relaciona esta categoría con una predicción teórica
* Memos de propiedades: variaciones en cómo se manifiesta la categoría entre casos

***

### RUTA B: Codificación Abductiva (CGT)

**3.B.1 Selección del interés abductivo**

El investigador elige uno (o define una combinación):

* Hipótesis causal (Analítica Inductiva)
* Proceso sociocognitivo: *"hábitos hipotéticos de comportamiento que procesan preocupaciones similares o más amplias en la vida diaria del entrevistado"* — predeterminado CGT
* Proceso central longitudinal
* Interés definido por el investigador

**3.B.2 Generación de patrones**

* Generar menos de X patrones grandes mutuamente excluyentes
* Los patrones deben exhibir suficiente variación interna para ser analíticamente útiles
* Método:
  &#x20; \* Comparación iterativa de resúmenes de segmentos (todos los segmentos referenciados; ninguno omitido)
  &#x20; \* La síntesis minimiza las diferencias entre documentos; produce una lista de códigos manejable
  &#x20; \* Para cada grupo: ¿qué eventos parecen indicar el mismo interés? ¿En qué se diferencian?
  &#x20; \* Regla de nombramiento: usar gerundios; evitar predicados; evitar jerga teórica
  &#x20; \* El nombre de la categoría se deriva de *la intercambiabilidad de indicadores*

**3.B.3 Asignación y resumen**

* Presentar la lista de códigos al investigador; asignar grandes bloques de texto a códigos
* Crear resúmenes de categorías resumiendo iterativamente los segmentos asignados
* Documentar cualquier conexión con resultados de codificación previos si es un segundo pase

**3.B.7 Memos de muestreo teórico inicial (TheoSamp1)**

Después del primer lote de documentos:

* Indicar *a priori* qué variables (del contexto o de los datos) sería bueno comparar en adelante
* El muestreo en esta etapa es deliberadamente abierto; guiado solo por una perspectiva sociológica general y el área temática amplia
* Probar: ¿la lógica de muestreo emergente se conecta con el POOL DE VARIABLES INICIALES?
* Documentar como tipo de memo: Hipótesis (justificación tentativa del muestreo)

***

### RUTA C: Codificación Inductiva

**3.C.1 Estrategias de codificación**

Elegir o combinar:

* Paráfrasis: larga (descriptiva) o corta (similar a etiqueta)
* Tema–subtema: agrupación jerárquica
* Variabilizar: identificar variantes dentro de un fenómeno en lugar de nombrar el fenómeno
* Estructural: autocrear nuevas categorías para preguntas que quedan fuera del esquema inicial

**3.C.2 Codificación por documento**

* Construir categorías documento por documento, luego agregar entre documentos
* El proceso es inherentemente más desordenado que en las Rutas A o B
* Riesgo: puede perder calidad de nominalización / teorización — monitorear y marcar

**3.C.3 Instrucción por lote de 3 documentos**

> *"Analiza estos segmentos. Ten en cuenta que te presento una mezcla de la percepción del investigador y extractos directos del corpus original. Reorganizarás todos los segmentos en categorías separadas mutuamente excluyentes según exclusivamente \[hábitos hipotéticos de comportamiento que procesan preocupaciones similares o más amplias en la vida diaria del entrevistado]. Separa estos de los comportamientos vistos únicamente en el entorno de la entrevista, que no son mi foco. Las interpretaciones del investigador podrían ser erróneas."*

**3.B.4 Procesamiento unificado por segmento (flujo cognitivo CGT)**

Por segmento, un flujo cognitivo integrado — sin subagentes separados:

1. Leer el segmento (explicación — ¿qué dice literalmente?)
2. Preguntar: *"¿Qué está pasando aquí?"*
3. Preguntar: *"¿Qué categoría indica esto?"*
4. Asignar código en gerundio si emerge un patrón
5. Sin preetiquetado; sin preprocesamiento; sin categorías forzadas

**3.B.5 Comparación con incidentes previos**

Cuando se reconoce un patrón potencial:

* Comparar con incidentes previamente codificados (vía Comparison\_Engine o Clusterizador)
* Preguntar: ¿es esto similar a lo visto antes? ¿En qué se diferencia? ¿Modifica la comprensión existente?
* Dejar que la comparación guíe la asignación del código — no un algoritmo de puntuación

Después de que todos los documentos han sido procesados individualmente:

* **Clusterizador informado:** realiza clustering de códigos abiertos entre documentos
* Fusiona las categorías por documento en un sistema de categorías inicial unificado
* Guarda en `research_categories` (BD)

***

### 3.4 Ciclo de Memo Cada 3 Documentos (todas las rutas)

Se activa cada 3 documentos. Dos agentes operan en paralelo (bifurcación):

* **Proponedor de memos:** genera memos de HIPÓTESIS y memos de PROPIEDAD a partir de los patrones acumulados hasta ahora
* **Testeador de memos:** evalúa cada memo como uno de:
  &#x20; \* `SAT` — saturado; el memo es robusto; no se necesita más evidencia
  &#x20; \* `MOD` — modificado; el memo necesita refinamiento; devolver al investigador con sugerencia
  &#x20; \* `FORCED` — no tiene fundamento empírico; descartar o marcar para reconsideración

Los memos se escriben en Memo\_Bank (sistema de archivos / almacenamiento persistente).

**Tipología de memos:**

| Tipo                   | Contenido                                                                                  |
| ---------------------- | ------------------------------------------------------------------------------------------ |
| Hipótesis              | Afirmación causal o relacional tentativa entre categorías                                  |
| Propiedad              | Una dimensión o variación dentro de una categoría                                          |
| Relación               | Coocurrencia documentada o afirmación direccional entre categorías                         |
| Reflexión metodológica | Nota de proceso del investigador, reconocimiento de sesgo o registro de decisión analítica |
| Muestreo               | Justificación de por qué se eligió un documento o comparación específica                   |

### Salida de la Fase 3

* Sistema de categorías inicial unificado con resúmenes y propiedades
* Corpus codificado: Documento → Segmento → Asignaciones de categoría
* Memo\_Bank poblado con memos de hipótesis, propiedades, muestreo y metodológicos
* POOL DE VARIABLES INICIALES actualizado
* Búfer de Residuos: todos los segmentos marcados como no clasificables durante esta fase

## Fase 4: Refinamiento de Categorías y Preguntas 

**Propósito:** Refinar el sistema de categorías mediante divisiones/fusiones internas, comparación entre categorías, postulación de relaciones y (para CGT) identificación de la preocupación principal y la categoría central.

**Equivalente n8n (etapas tardías de WF2):** Resumen de constructos → Finalización de memos

**Equivalente CGT PlantUML:** Fase 2 — Dejar Emerger el Núcleo

**Notas metodológicas:** Fases 5a, 5b, 5c + agentes de Resumen de Constructos de n8n

### 4a: Reorganización Interna — División / Refinamiento

**Principio:** La codificación inicial es imperfecta. Todos los cambios deben rastrearse en la **memoria de recodificación**. El objetivo final no es solo tener categorías estables, sino que cada categoría alcance una **saturación descriptiva**: su definición y propiedades deben dar cuenta explícita de las **diversidades y variaciones internas** presentes en los incidentes que agrupa.

#### 4a.1 Proceso iterativo — por incidente

Para cada categoría, probarla contra sus diferentes **incidentes** (resúmenes de segmentos con referencias):

1. **Eliminar los detalles de contexto** del incidente (abstraer lo específico).
2. **Comparar solo la esencia central** entre incidentes.
3. Preguntar: *"¿Son realmente el mismo patrón? ¿Podrían sustituirse entre sí en una explicación?"*
   * **Si SÍ (intercambiables):** la categoría se mantiene; **no se añade nueva diversidad** en este incidente.
   * **Si NO (no intercambiables):** se abre la posibilidad de **enriquecer la categoría** capturando su variación interna. Aplicar una de estas acciones:
     * **DIVIDIR** — crear subcategoría(s) o categoría(s) hermana(s); reasignar todos los segmentos afectados; actualizar resúmenes y propiedades para cada nueva categoría. Esto es adecuado cuando los incidentes forman **dos o más familias esencialmente diferentes**.
     * **REFINAR** — añadir a la **descripción de la categoría existente** para dar cuenta de la variación; **no dividir**. Esto es adecuado cuando los incidentes son variantes de un mismo fenómeno central (por ejemplo, diferentes manifestaciones de la misma propiedad).

#### 4a.2 Saturación como ampliación de la descripción

La saturación de una categoría no significa que todos los incidentes sean idénticos, sino que la **descripción de la categoría** ha logrado:

* Explicitar las **dimensiones de variación** interna (ej. intensidad, frecuencia, forma).
* Enumerar los **tipos o perfiles** que se dan dentro de la categoría.
* Especificar los **límites** (qué incidentes quedan excluidos, aunque parezcan relacionados).
* Proveer **ejemplos típicos y atípicos** que ilustren el rango de la categoría.

**Criterio de saturación para la reorganización interna:**

* Una categoría se considera **descriptivamente saturada** cuando, tras **3 iteraciones consecutivas** sin división, todos los nuevos incidentes pueden ser explicados por las propiedades ya documentadas (aunque añadan nuevos matices, no requieren cambiar la estructura de la categoría). La saturación se alcanza cuando las **diversidades internas** están completamente mapeadas.

#### 4a.3 Representación antes/después

* Capturar el **estado de las categorías y las asignaciones de segmentos** antes y después de cada iteración.
* Proporciona **pista de auditoría**; permite al investigador revisar y aprobar cambios.
* Registrar en el **historial de cambios** la razón de cada división o refinamiento.

#### 4a.4 Salida analítica por categoría (después de cada iteración)

Para cada categoría (ya sea original, dividida o refinada), responder:

* **¿Qué pregunta de investigación (PI) responde esta categoría?** ¿Con qué nivel de ajuste (alto, medio, bajo)?
* **Deductiva:** ¿Qué secciones del marco teórico involucra? ¿Confirma, matiza o contradice la teoría?
* **Abductiva:** ¿Qué dicen los datos sobre **patrones generales de comportamiento**? ¿Qué hábitos hipotéticos revela?
* **Inductiva:** ¿Qué temas parecen analíticamente más importantes? ¿Qué riqueza temática emerge?

#### 4a.5 Protocolo de división (condición formal)

* **Condición:** Dos grupos de incidentes dentro de la misma categoría demuestran **esencias no intercambiables** (es decir, no pueden sustituirse en una explicación de la preocupación central).
* **Acción:** Crear **dos o más categorías separadas** (tantas como grupos esencialmente distintos). Reasignar todos los segmentos. Escribir resúmenes y propiedades actualizados para cada nueva categoría, asegurando que cada una capture su propia variación interna.
* **Registro:** Documentar la división en el historial, incluyendo la justificación basada en incidentes específicos.

#### 4a.6 Protocolo de refinamiento (ampliación de descripción)

* **Condición:** Los incidentes no intercambiables son **variantes de un mismo fenómeno** (comparten una esencia común, pero difieren en grados, matices o contextos).
* **Acción:Añadir a la descripción** de la categoría existente:
  * Nueva propiedad o dimensión (ej. "intensidad: baja/media/alta").
  * Nuevo tipo o perfil (ej. "tipo evitador", "tipo confrontador").
  * Nuevos ejemplos límite.
  * Ajustar la definición para que abarque la variación sin romper la coherencia.
* **No dividir.** La categoría se vuelve más rica, no más fragmentada.
* **Registro:** Documentar cada refinamiento con los incidentes que lo motivaron.

#### 4a.7 Conexión con el POOL de variables

* Después de cada **división, fusión o cambio de nombre** (especialmente después de refinar), añadir una **nota reflexiva**:
* Si la respuesta es sí, vincular la categoría (o sus nuevas propiedades) a esa variable. Esto alimenta el muestreo teórico en fases posteriores.
* Si la respuesta es no, considerar si la **variable debería añadirse al POOL** (si la variación interna capturada es relevante para la teoría).

#### 4a.8 Criterio de término de la reorganización interna

* La Fase 4a concluye cuando **todas las categorías** han alcanzado la saturación descriptiva (según 4a.2) y no se requieren más divisiones o refinamientos.
* En ese punto, se pasa a la **Fase 4b (Reorganización Externa)** con categorías internamente ricas y estables.

***

### 4b: Reorganización Externa — Fusión y Relaciones (con sugerencia inteligente de cruces y prueba de hipótesis)

#### 4b.1 Generación de candidatos a relación (sin comparar todos los pares)

En lugar de comparar todas las combinaciones de categorías, el sistema **propone cruces potenciales** utilizando las siguientes fuentes:

* **Resúmenes de categorías**: la IA lee los resúmenes generados en la Fase 4a y detecta solapamientos semánticos, contrastes o posibles conexiones.
* **Memos**: los memos de hipótesis y de relación ya contienen sugerencias implícitas o explícitas de vínculos entre categorías.
* **Co-ocurrencia en documentos**: se consulta la base de datos para identificar pares de categorías que aparecen **frecuentemente juntos** en los mismos segmentos o documentos (sin necesidad de predefinir umbrales, solo se listan los más frecuentes).
* **Informes de adecuación de documentos (Fase 2.3)**: si un documento se señaló como especialmente relevante para una pregunta de investigación, sus categorías tienen más peso para generar cruces.
* **POOL de variables iniciales**: si dos categorías están asociadas a la misma variable o a variables relacionadas, se prioriza su comparación.
* **Sugerencia directa del investigador**: el investigador puede marcar manualmente un par de categorías para analizar su relación.

**Proceso de sugerencia:**

1. La IA recopila todas las fuentes anteriores y genera una **lista priorizada de candidatos** (pares de categorías) ordenada por **probabilidad de relación relevante** (basada en frecuencia de co-ocurrencia, solapamiento semántico en resúmenes, menciones en memos, etc.).
2. Se presenta al investigador una lista de, por ejemplo, **hasta 20 candidatos** más probables (el número puede configurarse).
3. El investigador puede:
   * Aceptar todos.
   * Seleccionar manualmente qué pares analizar.
   * Añadir pares adicionales.

**Ventaja:** Se evita la explosión combinatoria y se enfoca el análisis en las relaciones con mayor probabilidad de ser significativas.

#### 4b.2 Condición de fusión (si el sistema detecta que son el mismo fenómeno)

Antes de probar relaciones, el sistema evalúa si los dos candidatos deberían fusionarse (es decir, si en realidad son la misma categoría). Esto se activa cuando:

* La IA (basada en resúmenes y ejemplos típicos) estima que **más del 80% de los ejemplos típicos son compartidos**.
* **Ningún patrón diferenciador** se identifica en los memos o en las propiedades.

**Acción de fusión:**

* Fusionar en una sola categoría.
* Tomar la categoría **más grande o mejor definida** como base.
* Unificar descripciones, propiedades y ejemplos.
* Registrar la fusión en el **historial de cambios**.
* **Nota:** Si se fusionan, no se prueba relación (porque ya no hay dos categorías distintas).

#### 4b.3 Inclusión del Búfer de Residuos (reclasificación)

*(Sin cambios respecto a la versión anterior)*

Después de las fusiones y relaciones, reintentar clasificar los segmentos residuales (máx. 3 intentos; luego anomalía justificada).

#### 4b.4 Prueba de hipótesis para relaciones (solo sobre los candidatos seleccionados)

Para cada par `(A, B)` que **no se fusiona** y que ha sido aceptado para análisis (por el sistema o por el investigador), se aplica el siguiente **protocolo de prueba de hipótesis**.

**Tipos de relaciones a probar (la IA puede sugerir uno o varios para cada par según el contexto):**

* Jerarquía (A es subtipo de B, o viceversa)
* Causalidad (A → B, o B → A)
* Tipología (A y B son variantes de un mismo tipo superior)
* Etapas de proceso (A precede a B)
* Oposición (A y B son polos opuestos)
* Co‑ocurrencia (sin orden)

**Para cada relación candidata&#x20;****`R(A,B)`****&#x20;(puede ser más de una por par):**

1. **Formular hipótesis nula y alternativa** (igual que antes).
2. **Diseñar la prueba empírica**:
   * Seleccionar una **muestra teórica** de documentos (todos los documentos donde aparece al menos una de las dos categorías, o una muestra dirigida por TheoSampler).
   * Extraer segmentos relevantes.
   * Aplicar criterios específicos según el tipo de relación.
3. **Recoger evidencia** (calcular frecuencia, fuerza, necesidad, contraejemplos).
4. **Aplicar umbrales de decisión** (configurables):
   * Presencia mínima: al menos `N_docs_min = 3` documentos (o 20% del corpus) deben mostrar la relación.
   * Fuerza: `cumple_R / (documentos con A)` ≥ 0.7 (para direccionales).
   * Consistencia: contraejemplos ≤ 10%.
5. **Decidir**: si se cumplen umbrales → rechazar H₀ y aceptar H₁ (la relación existe). En caso contrario, no aceptar.
6. **Registrar resultados** en la tabla de salida:

| Categoría A | Categoría B | Tipo de relación probado | ¿H₁ aceptada? | Evidencia (docs / fuerza) | ¿Nuevo par? |
| ----------- | ----------- | ------------------------ | ------------- | ------------------------- | ----------- |

1. **Actualizar descripciones de categorías**: añadir una **propiedad relacional** a cada categoría involucrada. Por ejemplo:
2. **Actualizar el POOL de variables**: incorporar la relación confirmada como una variable derivada (útil para muestreo teórico posterior).

#### 4b.5 Iteración y estabilidad

* Una vez procesados los candidatos iniciales, se puede repetir el proceso de **sugerencia de nuevos candidatos** basándose en las relaciones recién aceptadas (las relaciones pueden abrir nuevas conexiones).
* El proceso termina cuando no se aceptan nuevas relaciones en una ronda completa y el investigador confirma que no hay más cruces de interés.

#### Flujo actual: 

Una vez que se han terminado las reorganizaciones internas (fusión, división y ajuste de categorías), el sistema realiza automáticamente los siguientes pasos por cada categoría

1. **Revisar los solapamientos entre categorías.**
   El sistema detecta si dos o más categorías comparten muchos indicadores (segmentos de texto, ejemplos, propiedades) y las agrupa. Esto ayuda a ver si realmente son independientes o si podrían unificarse.
2. **Unificar las hipótesis.**
   Se juntan todos los memos de hipótesis que se hayan generado, se eliminan los repetidos y se resuelven las contradicciones entre ellos. El resultado es un conjunto de hipótesis claras y coherentes.
3. **Crear un registro de variables útiles.**
   A partir de los criterios de muestreo que se hayan usado (por ejemplo, contrastes por edad, género, tipo de organización) y del **POOL de variables** que se ha ido construyendo, el sistema elabora una lista ordenada de variables que serán relevantes para el análisis selectivo.
4. **Recodificar los documentos con el sistema refinado.**
   Tomando como base el esquema de categorías ya mejorado y las variables identificadas, el sistema revisa todos los documentos y **reasigna los códigos** donde sea necesario. Esto asegura que todos los segmentos queden bien clasificados según la última versión de las categorías.

Finalmente, se **actualizan las bases de datos**:

* Los segmentos de texto se guardan con sus nuevos códigos.
* Las categorías se actualizan con las variables que les corresponden (por ejemplo, una categoría puede quedar vinculada a variables como “intensidad alta”, “contexto rural”, etc.).

Todo esto se hace de forma automática, pero el investigador puede revisar y ajustar los resultados antes de continuar.

***

### 4c: Deduplicación: Finalización de Memos

A**I Agent4 – Agrupa ideas recurrentes**

Lee todos los memos generados hasta el momento y detecta qué temas, reflexiones o hallazgos aparecen una y otra vez a lo largo del análisis. Los organiza por afinidad, ayudando al investigador a ver rápidamente cuáles son las preocupaciones o patrones más recurrentes en el corpus.

**AI Agent6 – Ordena el banco de memos**

Toma el conjunto completo de memos (el `Memo_Bank`) y lo estructura en grupos temáticos coherentes. El resultado es un índice o mapa de memos que permite navegar por las ideas analíticas sin perderse, identificando qué categorías o relaciones han generado mayor desarrollo.

**AI Agent7 – Contrasta hipótesis con los documentos**

Para cada hipótesis documentada en los memos, la somete a prueba revisando sistemáticamente todos los documentos (segmento por segmento). Anota qué evidencia la respalda, qué contraejemplos aparecen y en qué casos no aplica. Así se evita dar por válida una hipótesis sin haberla confrontado con la totalidad de los datos disponibles.

Salida: `memos_final` — la entrada principal para las Fases 5, 6 y 7

### 4d: Reformulación de la(s) Pregunta(s) de Investigación

**Disparadores — cualquiera de estos justifica la reformulación:**

* La IA detecta tensiones no resueltas en el registro de memos que las PI actuales no abordan
* Se ha elegido una categoría central y se requiere delimitación
* Aparecen contraejemplos recurrentes que ninguna categoría actual puede absorber
* El investigador solicita explícitamente un enfoque diferente

**Por ruta de codificación:**

*Deductiva:*

* Comparar el informe teórico de la Fase 0.3 con las categorías resultantes
* ¿Qué investigaciones son posibles dados los datos actuales y el MT?
* ¿Qué PI han sido respondidas? ¿Dónde hay vacíos? ¿Dónde hay genuina novedad?
* Generar opciones de PI reformuladas específicas (desde descriptivas hacia interpretativas)
* Filtrar u ordenar las PI por suficiencia de datos antes de comprometerse
* Mapear cada categoría retenida a las PI teóricas elegidas

*Abductiva:*

* Analizar los memos de codificación y refinamiento junto con los resúmenes de códigos
* Responder: 
* **Detección de la preocupación principal (Main\_Concern\_Sensor):**

  Entrada: todos los códigos + todo Memo\_Bank

  Preguntas para trabajar (razonamiento cualitativo, no puntuación):
  1. ¿Qué problemas recurren en los códigos?
  2. ¿Qué tensiones parecieron importantes en los memos?
  3. ¿Qué impulsa el comportamiento de los participantes más allá de sus razones explícitas?
  4. NO buscar problemas declarados — sentir la preocupación subyacente latente
  Salida: *"Preocupación principal detectada: \[Declaración de la preocupación]"*

  **Revelación de la categoría central (Core\_Emergence\_Detector):**

  Usando la preocupación principal detectada, evaluar cada categoría candidata:
  1. ¿Qué patrón resuelve la preocupación principal?
  2. ¿Qué patrón se conecta con el mayor número de otros patrones?
  3. ¿Qué patrón tiene el mayor *agarre teórico* (se siente generativo, no solo descriptivo)?
  4. ¿Qué patrón se siente más central para entender los datos?
  La evaluación es cualitativa. No hay algoritmo de puntuación. Es emergente, no forzada.

  Salida: lista de categorías centrales candidatas y justificación con grab empírico

  **Prueba de intercambiabilidad verdadera (Interchangeability\_Tester):**

  ¿Resuelve el main concern? Indicaciones: Tiene pocas relaciones = Es poco saturada, y es "popular" y "emocionante" en vez de sintetizar descriptivamente lo que realmente pasa en los datos

  Resultados:
  * **SÍ — intercambiables:** la categoría es conceptualmente válida → proceder a la delimitación
  * **NO — no intercambiables:** dividir o refinar la categoría → volver a 4a
* Mapear y elegir cada categoría retenida a la tendencia central identificada en la población

*Inductiva:*

* Aplicar criterios de Saldaña: tríada de riqueza, orden de eventos, grandes oposiciones, proceso
* Marcar cada categoría por estos criterios en adelante para guiar la estructura de escritura

***

### Salida de la Fase 4

* Sistema de categorías refinado y validado con historial de cambios documentado
* `memos_final`: memos de hipótesis, propiedades, relaciones y metodológicos organizados por tema
* POOL actualizado con variables refinadas y relaciones postuladas
* PI reformuladas (si corresponde) y Categoría central (ruta CGT/abductiva)
* Anomalías residuales: documentadas y justificadas

## Fase 5: Codificación Secundaria

### 5a: Interpretación (texto en contexto)

P**rincipio rector:** El sistema no dirige. El investigador pregunta. El sistema responde. El investigador decide qué hacer con la respuesta.

**Estado de partida:** Categorías refinadas (Fase 4), `memos_final`, nuevas preguntas (Fase 4e). El sistema ha colocado todo esto en una **mesa de trabajo compartida**. Nada se ejecuta automáticamente.

#### 5a.1 Rol: Posturas interpretativas (criterios)

En cualquier momento, el investigador puede decirle al sistema: *"Quiero actuar como..."* y elegir una de estas posturas. El sistema entonces ajusta sus respuestas a esa postura.

| Postura                | ¿Qué significa?                                                                      | Ejemplo de instrucción al sistema                                                                                                                                          |
| ---------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Explorador**         | Busco conexiones inesperadas, patrones ocultos, relaciones que no vi.                | *"Muéstrame relaciones entre la categoría X y la Y que no haya documentado antes."*                                                                                        |
| **Abogado del diablo** | Quiero que desafíes mis conclusiones, que busques agujeros.                          | *"Dame 3 razones por las que mi interpretación podría estar equivocada."*                                                                                                  |
| **Etnógrafo virtual**  | Quiero acercarme a la experiencia de los participantes.                              | *"Actúa como un \[rol] y reacciona a este hallazgo."*                                                                                                                      |
| **Teórico crítico**    | Quiero ver cómo se conecta esto con la literatura o con conceptos abstractos.        | *"¿Qué diría Bourdieu de esta categoría?"*                                                                                                                                 |
| **Editor**             | Quiero darle estructura narrativa a esto según criterios de una revista              | *"Reescribe este párrafo en modo más claro, manteniendo el contenido."*                                                                                                    |
| **Auditor**            | Quiero verificar la solidez ética y empírica de mis afirmaciones.                    | *"Revisa este texto por sesgos o falta de evidencia."*                                                                                                                     |
| Dialéctico             | Quieres crear un diálogo constante entre datos y teoría, entre tu voz y otras voces. | El sistema alternará automáticamente citas de datos con interpretaciones teóricas, y te sugerirá cómo estructurar el texto en modo paralelo o entrelazado (según tu guía). |

#### 5a.2. Gestos interpretativos (qué puedes pedir en cualquier momento)

Mientras trabajas, puedes **seleccionar un fragmento** de texto (un párrafo, una cita, una hipótesis) y pedirle al sistema que haga algo con él. También puedes pedir gestos sin selección, sobre el contexto completo.

Los gestos están directamente inspirados en tu guía: corresponden al ciclo hermenéutico (enfoque, cuestionamiento, triangulación, incorporación) y a la ética interpretativa.

**Gestos de enfoque (qué aprendí de nuevo)**

| Gesto                            | Qué hace                                                                                                                            |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| *“¿Qué hay de nuevo aquí?”*      | Resume los aprendizajes emergentes del texto seleccionado en contraste con lo que ya sabías.                                        |
| *“¿Qué pregunta responde esto?”* | Asocia el fragmento a una o varias preguntas de investigación (las que tengas definidas). Si no encaja, sugiere una nueva pregunta. |
| *“¿Qué no sabemos todavía?”*     | Identifica lagunas en la información: qué datos faltan, qué contradicciones persisten.                                              |

**Gestos de cuestionamiento (desafiar la interpretación)**

| Gesto                                     | Qué hace                                                                                                                                    |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| *“¿Qué contexto falta?”*                  | Detecta elementos contextuales ausentes (históricos, espaciales, demográficos, relacionales) según tu guía. Te propone añadirlos.           |
| *“¿Qué sesgo podría haber?”*              | Cruza el fragmento con tus memos metodológicos personales (si los has escrito) y te señala posibles proyecciones emocionales o ideológicas. |
| *“¿Hay un contraejemplo?”*                | Busca en la base de datos segmentos codificados que contradigan la afirmación seleccionada. Te los muestra con sus referencias.             |
| *“¿Qué supuesto teórico estoy forzando?”* | Si usas un marco teórico, el sistema identifica conceptos que podrían estar sobreaplicados o mal ajustados a los datos.                     |
| *“Actúa como un crítico”*                 | (postura abogado del diablo) El sistema escribe un párrafo argumentando en contra de tu interpretación, usando tus mismos datos.            |

**Gestos de triangulación (traer otras voces)**





| Gesto                                 | Qué hace                                                                                                                                      |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| *“¿Qué dice la literatura?”*          | Consulta el RAG bibliográfico y te trae 2-3 citas de autores que hayan estudiado algo similar, indicando semejanzas y diferencias.            |
| *“¿Qué dice internet o los medios?”*  | Si está habilitado, busca noticias, informes públicos o redes sociales sobre el tema. Te muestra fragmentos relevantes.                       |
| *“Actúa como un informante”*          | Simula la voz de un participante típico (basado en el perfil de tu corpus) y reacciona al hallazgo. Puedes especificar el rol.                |
| *“¿Qué diría un colega?”*             | Genera un conjunto de preguntas críticas que podrías hacerle a un compañero experto, o simula la respuesta de ese colega.                     |
| *“Tráeme una voz local / extranjera”* | Diferencia entre generalización interna (mismo país/comunidad) y externa (otros contextos). El sistema busca fuentes en una u otra dirección. |

**Gestos de incorporación (estructurar y escribir)**





| Gesto                                                           | Qué hace                                                                                                                                         |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| *“Estructura esto como… \[inductivo / dialéctico / deductivo]”* | Reorganiza el fragmento según la estructura elegida (emergente, modular, minimalista; paralela, entrelazada; de cimientos, estribillo, anclada). |
| *“Escribe un borrador”*                                         | Convierte el fragmento y las discusiones asociadas en un párrafo o sección de informe, respetando la postura activa y el tiempo presente.        |
| *“Convierte en pregunta”*                                       | Transforma una afirmación en una nueva pregunta de investigación (útil para reformular).                                                         |
| *“Generaliza”* o *“Especifica”*                                 | Eleva el nivel de abstracción o baja a un ejemplo concreto.                                                                                      |
| *“¿Qué conexión tiene con la categoría X?”*                     | Muestra solapamientos, diferencias o relaciones causales entre el fragmento y otra categoría del sistema.                                        |

**Gestos éticos (auditoría en caliente)**

| Gesto                                          | Qué hace                                                                                                                                                                                                                                          |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| *“Audita éticamente esto”*                     | Aplica las cinco comprobaciones de tu guía (ceguera contextual, falta de reflexividad, colonialismo interpretativo, fabricación/falta de trazabilidad, colusión con informante). Te devuelve un informe con alertas y acciones sugeridas.         |
| *“¿Dependo de un solo informante?”*            | Analiza la distribución de citas en el fragmento o categoría. Si más del 60% viene de una fuente, te avisa.                                                                                                                                       |
| *“¿Es trazable esta afirmación?”*              | Verifica que cada afirmación importante tenga al menos una cita o referencia a un segmento específico. Marca las que no.                                                                                                                          |
| *“¿Estoy imponiendo mi marco?”*                | Si usas teoría occidental en contexto no occidental, el sistema sugiere conceptos nativos que hayan aparecido en los datos.                                                                                                                       |
| *“Prepara una devolución ética de resultados”* | Toma un hallazgo o categoría, lo traduce a lenguaje no técnico, añade ejemplos anonimizados y genera una nota para compartir con participantes (si aplica). Incluye advertencias sobre cómo evitar estigmatización y cómo pedir retroalimentación |

También se extiende la auditoría con una pregunta sobre \*\*posibles daños de la generalización\*\*: \*“¿Mi teoría, si se aplica en otro contexto, podría etiquetar injustamente a un grupo?”\*. El sistema busca en el RAG ejemplos históricos de teorías mal aplicadas.

**Análisis de silencios y visión jerárquica (in-data)**

Estos gestos exploran lo que **no está presente** en los datos o lo que está débilmente representado, así como las relaciones entre niveles de abstracción.

| Gesto                                                     | Qué hace                                                                                                                                            | Referente metodológico                                               |
| --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| *“¿Qué palabras faltan en esta clase lingüística?”*       | Compara el vocabulario esperado (según otras clases o corpus externo) con el observado. Lista términos ausentes que podrían ser significativos.     | Becker: los silencios revelan acuerdos tácitos o temas tabú.         |
| *“¿Qué clases no aparecen en este tópico?”*               | Cruza la asignación de clases (lingüísticas) y tópicos (BERTopic/Reinert). Señala combinaciones vacías o inesperadas.                               | Abbott: las distinciones fractales – lo excluido define el límite.   |
| *“¿Qué tópicos no están vinculados a ninguna categoría?”* | Identifica grupos temáticos que la codificación cualitativa no ha capturado. Sugiere revisar esos segmentos.                                        | Hammersley: pueden ser lagunas de muestreo o áreas no saturadas.     |
| *“¿Qué categorías no se integran en la teoría actual?”*   | Muestra categorías con baja centralidad o pocas relaciones. Pregunta si deberían descartarse, fusionarse o repensar la teoría.                      | Becker: “la teoría es un mapa, no el territorio”.                    |
| *“Visión jerárquica (de palabras a teoría)”*              | Genera una visualización anidada: palabras → clases lingüísticas → tópicos → categorías → teoría, con grosores que indican solidez de la evidencia. | Abbott: escalamiento (micro-macro) para ver recurrencia de patrones. |

Expansión de contexto externo (out-data) y muestreo de nuevas fuentes

El sistema propone activamente qué datos adicionales recoger para enriquecer, matizar o falsar los hallazgos en cada nivel analítico.

| Nivel actual                   | Pregunta al sistema                                                                                                   | Sugerencia de datos externos                                                                                                 | Base metodológica                             |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| **Clases lingüísticas**        | *“¿Qué microculturas podrían explicar estas palabras?”*                                                               | Buscar entrevistas o documentos de grupos con jerga, profesión o subcultura similar.                                         | Becker: mundos sociales compartidos.          |
| **Tópicos (BERTopic/Reinert)** | *“¿Qué grupos por capas de cercanía podrían tener una organización diferente de estos temas?”*                        | Datos de organizaciones vecinas, asociaciones profesionales, comunidades online con distintos grados de proximidad.          | Becker: seguir la cadena de inferencia.       |
| **Categorías cualitativas**    | *“¿Qué contextos de personas (según intertextualidad y variables) podrían cuestionar los límites de esta categoría?”* | Entrevistas a casos extremos o atípicos, documentos que contradigan la propiedad dominante.                                  | Hammersley: buscar evidencia negativa.        |
| **Teoría emergente**           | *“Diseña un experimento mental que ponga a prueba la teoría.”*                                                        | Escenarios hipotéticos, contraargumentos lógicos o aplicaciones a dominios distintos.                                        | Abbott: analogía estructural.                 |
| **Cualquier nivel**            | *“¿Cómo podrían cambiar estos hallazgos en el tiempo?”*                                                               | Datos longitudinales (si existen) o reconstrucciones históricas; si no, simular tendencias mediante extrapolación cautelosa. | Abbott: los procesos sociales son temporales. |

El investigador puede activar estos análisis con comandos como: *“Propón datos externos para mi categoría X”* o *“Genera un experimento mental que desafíe la relación A→B”*.

Generalización externa y traducción comparativa

Este conjunto de gestos ayuda a trasladar los hallazgos a otros campos, disciplinas o poblaciones, identificando qué es transferible y qué es local.

| Gesto                                                                                                                             | Qué hace                                                                                                                                                                                                      | Producto                                                                                                                        |
| --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| *“Recomienda disciplinas afines”*                                                                                                 | Analiza las palabras clave, constructos y preguntas de investigación; las coteja con un mapa de campos académicos (precargado o via RAG).                                                                     | Lista de disciplinas (ej. sociología del trabajo, antropología de la salud, psicología organizacional) con justificación.       |
| *“Sugiere términos de búsqueda para literatura comparativa”*                                                                      | Extrae de los hallazgos conceptos centrales, los traduce a lenguaje académico estándar y propone sinónimos, antónimos y términos relacionados.                                                                | Conjunto de cadenas de búsqueda (ej. “*avoidance behavior* AND *gig economy* NOT platform”) listas para usar en bases de datos. |
| *“¿En qué países o regiones se han observado fenómenos similares?”*                                                               | Busca en la literatura (vía RAG) casos geográficamente diversos donde aparezcan palabras o estructuras análogas. Señala semejanzas y diferencias contextuales.                                                | Mapa o tabla comparativa con referencias.                                                                                       |
| *“¿Qué grupos sociales (según campo científico) podrían mostrar una organización diferente de clases/tópicos/categorías/teoría?”* | Propone poblaciones alternativas (ej. trabajadores formales vs. informales, estudiantes vs. profesores, usuarios tempranos vs. tardíos) donde la misma categoría central podría manifestarse con otra lógica. | Lista de hipótesis contrastables: “En el grupo Y, esperaríamos que la categoría Z se desdoble en dos subcategorías porque…”.    |
| *“Traduce mi teoría a un contexto diferente”*                                                                                     | Pide al sistema que reescriba las proposiciones teóricas usando el vocabulario y los ejemplos de otro campo (ej. de la educación a la salud).                                                                 | Borrador de sección de discusión sobre transferibilidad.                                                                        |

Estos gestos pueden combinarse con los de triangulación (literatura, internet, informantes virtuales) para obtener una visión más rica.



#### 5a.3 : \[OPCIÓN] Recodificación

**Cuándo aplicar:**

* El sistema de categorías cambió significativamente al punto que la codificación previa no es confiable
* El investigador juzga que recodificar todos los datos está justificado
* Una categoría falla consistentemente en saturarse en la Fase 5 — la recodificación masiva puede resolverlo

**Proceso:**

* Aplicar el sistema de categorías refinado a todos los documentos (o a una muestra teórica dirigida)
* Permitir reasignaciones masivas de códigos
* Si los cambios revelan nuevas divisiones/fusiones: volver a 4a/4b antes de reingresar a la Fase 5

**Nota:** Esta es una opción impulsada por el investigador, no un paso obligatorio. La decisión depende de la magnitud de los cambios conceptuales realizados en 4a/4b.

#### 5a.4. El ciclo hermenéutico como diálogo, no como receta

Ejemplo concreto de un investigador real:

1. **Enfoque:** Lee el resumen de la categoría “rutinas de evitación”. Selecciona la frase *“Los repartidores cambian de zona cuando el algoritmo les da pocos pedidos”*.
   → Gesto: *“¿Qué hay de nuevo aquí?”*
   → El sistema responde: *“Esto confirma la hipótesis de agencia reactiva, pero no explica cuándo optan por cambiar de app en lugar de zona.”*
2. **Cuestionamiento:** El investigador sospecha que está simplificando.
   → Gesto: *“¿Qué contexto falta?”*
   → El sistema señala: *“No mencionas la hora del día ni la densidad de repartidores en la zona. En tus datos, estos factores modifican la decisión.”*
3. **Triangulación:** Quiere ver qué dice la literatura.
   → Gesto: *“¿Qué dice la literatura sobre evitación algorítmica?”*
   → El sistema trae dos estudios: uno sobre “gaming the algorithm” en Uber, otro sobre “resistance through mobility”.
4. **Incorporación:** Decide escribir un párrafo dialéctico.
   → ¿Qué añaden los nuevos datos contextuales a nuestros datos primarios?
   → El sistema produce dos columnas: datos (citas de repartidores) vs. interpretación (conceptos de la literatura).
5. **Ética:** Antes de guardar, pide auditoría.
   → Gesto: *“Audita éticamente esto”*
   → El sistema alerta: *“Usas el término ‘gaming the algorithm’ que viene de estudios anglosajones. Tus datos usan la frase local ‘dar la vuelta’. Sugiero reemplazar.”*
6. Recodificar con reglas claras.

El investigador ajusta, guarda el memo interpretativo, y sigue.

Ningún gesto fue obligatorio. Pudo haber empezado por la auditoría, o por la triangulación. El sistema nunca le dijo “ahora tienes que hacer el paso 2”.

### 5b: Codificación Selectiva

**Propósito:** Desarrollar la categoría central comparando sistemáticamente incidentes entre documentos. Enfocarse exclusivamente en datos relevantes para la categoría central y sus propiedades. Rastrear la saturación numéricamente.

**Equivalente n8n:** WF1 — Bucles de categoría × variable con bucle de comparación constante

**Equivalente CGT PlantUML:** Fase 3 — Codificación Selectiva Natural

**Notas metodológicas:** Fase 6.2 (primera parte — lógica de bucle y saturación)

#### 5b.1 Configuración

Entrada desde la Fase 4: memos\_final, research\_categories, summarized\_constructs, preocupación central

**Subproceso WF3 (Recategorización):**

* Lee research\_categories de la BD
* Realiza análisis de constructos
* Actualiza summarized\_constructs en la BD

**Buscador de la Preocupación Central (Core Concern Finder):**

* Reconfirmar o refinar la preocupación principal de la Fase 4d
* Entrada: sistema de categorías completamente refinado de la Fase 4
* Salida: declaración definitiva de la preocupación central (registrada; persiste para todas las fases restantes)

**Verificación de la lista de categorías:**

* Si no existe una lista plana de categorías: el agente Listar categorias la extrae del sistema de categorías

#### 5b.2 Puntuación de Relevancia

Para cada categoría, asignar una puntuación del 1 al 5 basada en la fuerza del vínculo con la preocupación central.

| Puntuación | Significado                                                       |
| ---------- | ----------------------------------------------------------------- |
| 1–2        | Periférica; no analíticamente útil para la fase selectiva         |
| 3          | Marginalmente relacionada; monitorear pero no procesar            |
| 4–5        | **Supera el umbral; entra en el bucle de codificación selectiva** |

Umbral: **≥ 4 requerido** para la inclusión en la codificación selectiva.

Las puntuaciones se escriben en la BD. Las categorías con puntuación 1–3 se conservan pero no se procesan más a menos que el investigador anule.

#### 5.3 Muestreo Teórico para Codificación Selectiva (TheoSampler)

Para cada categoría que supera el umbral, diseñar una estrategia de muestreo dirigida a maximizar las diferencias en los datos (variaciones de propiedades, dimensiones):

| Tipo de muestreo   | Justificación                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| Casos de contraste | Documentos con valores altos vs. bajos en variables relevantes — revela límites de propiedades |
| Casos extremos     | Documentos más alejados de la norma — prueba la categoría bajo estrés                          |
| Casos consistentes | Documentos similares — verifica la replicabilidad de las afirmaciones sobre propiedades        |

Ahora la búsqueda será de indicadores empíricos específcos o slices de data. No se necesitan todos los documentos enteros. Conectar la necesidad de data según las core categories al POOL de variables o bien a nuevas FUENTES de información. Registrar como memos de muestreo.

Cuando una comparación requiere estructura dicotómica:

* Binarizar distribuciones de variables continuas u ordinales
* Se utiliza para estructurar combinaciones de FUENTES en el bucle de comparación constante

Para cada categoría x variable, por combinación de documentos:

1. Cargar datos de la combinació&#x6E;*&#x20;(lacat2 en n8n)*
2. **Compara varios docs:** encontrar insights nuevos / confirmados / actualizados
   &#x20;  \* **Nuevo:** dimensión de propiedad no observada previamente en esta categoría
   &#x20;  \* **Confirmado:** la propiedad aparece nuevamente — incrementar contador de saturación
   &#x20;  \* **Actualizado:** propiedad refinada; límites cambiados — reiniciar contador de saturación; documentar el refinamiento
   1. Si es nuevo o actualizado, **Para cada indicador entrante en codificación selectiva:**
      1. ¿Este indicador se relaciona con la categoría central?
      2. ¿Desarrolla una propiedad de la categoría central?
      3. Si SÍ → codificarlo; desarrollar la propiedad
      4. Si NO → ignorarlo (esto es la delimitación en acción; no un fracaso)
3. SATURACIÓN: Actualizar el estado de la categoría incrementalmente: propiedades, límites de definición, ejemplos representativos
4. Si aparece un **contraejemplo**: reiniciar contador de saturación; documentar el contraejemplo explícitamente

**Verificación de Saturación**

**Nodos de análisis paralelo (ejecución simultánea):**

* **Nodo de Patrones de Comportamiento:**
  &#x20; \* Identificar incidentes de comportamiento recurrentes (el patrón debe aparecer en ≥ 3–4 entrevistados)
  &#x20; \* Citar identificadores de entrevistados por cada patrón afirmado
  &#x20; \* Agrupar manifestaciones opuestas del mismo fenómeno juntas
  &#x20; \* No tratar casos aislados como patrones; usarlos como ilustraciones de patrones más grandes solo si procede
* **Nodo de Propiedades:**
  &#x20; \* Identificar variaciones, gradientes y extremos que indican subpatrones latentes
  &#x20; \* Mapear dimensiones: ¿qué varía entre casos que comparten el código de categoría?
  &#x20; \* Identificar perfiles o tipos claramente opuestos dentro de la categoría
* **Nodo de Causas:**
  &#x20; \* Identificar condiciones determinantes: ¿qué desencadena o permite que ocurra esta categoría?
  &#x20; \* Distinguir condiciones estructurales (siempre presentes) de condiciones contingentes (varían)
* **Nodo de Consecuencias:**
  &#x20; \* ¿Qué produce actuar sobre esta categoría?
  &#x20; \* ¿Qué estrategias genera en los participantes?
  &#x20; \* ¿Cuáles son los efectos posteriores?

**Síntesis (nodo Generate):**

Recibe: todas las 4 salidas paralelas + JSON bruto + metadatos (hoja de cálculo)

Produce: informe de memo integrado con secciones:

1. Patrones de Comportamiento: perspectiva compartida; incidentes recurrentes nombrados con gerundios
2. Propiedades: constructos latentes indicados por cómo varía la categoría
3. Diferencias internas: perfiles y tipos que la categoría captura
4. Condiciones causales: estructurales y contingentes
5. Respuestas y estrategias: qué hacen los participantes con la categoría
6. Pensamiento vs. Acción: patrones de coherencia y fragmentación entre puntos de vista declarados y comportamiento real

**Refinamiento secuencial:**

* **Nodo de simplificación de variaciones** (Nodo B):
  &#x20; \* Entrada: salida de Generate
  &#x20; \* Explorar dimensiones y gradientes que abarcan los datos citados
  &#x20; \* Comparar, reclasificar y resumir variaciones que están claramente correlacionadas
  &#x20; \* Separar variaciones correlacionadas de las no correlacionadas
  &#x20; \* Producir tablas de doble entrada para dimensiones correlacionadas
  &#x20; \* Verificar intersecciones empíricamente antes de concluir correlación
  &#x20; \* Debe indicar, dentro de las tablas, qué patrón se refiere a qué tema
* **Nodo de búsqueda de correlaciones** (Nodo C):
  &#x20; \* Entrada: salida de Generate + salida de Simplificación de variaciones + hoja de cálculo de metadatos
  &#x20; \* Cruzar las tablas de Simplificación de variaciones
  &#x20; \* Identificar dimensiones bivariadas o multivariadas precisas; descartar las no sustentadas
  &#x20; \* Producir matrices 2×2 para tipologías basadas en evidencia
  &#x20; \* Citar identificadores de entrevistados dentro de las matrices
  &#x20; \* Proporcionar descripciones cualitativas de cada cuadrante
  &#x20; \* Usar términos estadísticos de manera laxa — la salida es cualitativa, no cuantitativa

**Por categoría/variable — criterios:**

| Criterio                                                                                                      | Umbral |
| ------------------------------------------------------------------------------------------------------------- | ------ |
| Iteraciones consecutivas sin cambio en propiedades, definición o ejemplos                                     | 3      |
| Para afirmaciones relacionales abductivas: documentos distintos mostrando la misma relación, 0 contraejemplos | 5      |
| Iteraciones máximas por variable antes de la revisión forzada                                                 | 20     |

**No saturada → Protocolo de Limpieza de Memoria:**

* Limpiar el contexto de trabajo de la IA para esta categoría
* Conservar: definiciones actuales de categorías, declaración de preocupación central, todos los memos
* Repetir el bucle de comparación constante desde un estado limpio con la misma categoría
* Si aún no está saturada después de la limpieza de memoria: activar la Fase 4c (Reinterpretación) para esta categoría

**Saturada → avanzar a la siguiente categoría**

#### 5b.3 Condición de Saturación Global

La fase de codificación selectiva termina cuando TODAS las siguientes condiciones son verdaderas:

* Todas las categorías con puntuación de relevancia ≥ 4 están saturadas (según el criterio de 5.6)
* Todas las relaciones inter-categoriales postuladas están saturadas (5 documentos, 0 contraejemplos)
* El Búfer de Residuos ha sido revisado: los segmentos restantes están clasificados como anomalías justificadas (documentadas)

OJO: La idea tiende a resumir en demasía. Cada ejecución se antepone a la parte superior del documento; las versiones anteriores se conservan debajo

### 5c: Descripción y visualización

¿Qué no hace este flujo?

* No prueba hipótesis (no hay H₀/H₁, ni umbrales de fuerza).
* No busca saturación de propiedades (solo describe lo que hay, no cuándo parar).
* No formula preguntas de investigación reformuladas (aunque el investigador puede hacerlo aparte).
* No integra literatura ni voces externas (eso es para el taller interpretativo).

**Es puramente descriptivo‑visual.** Su producto final es un **catálogo ordenado y visualmente comprensible** de los hallazgos, útil para informes, tesis o como paso previo a una interpretación más profunda (entonces se cambiaría de postura).

#### 5c.1. Análisis de una categoría específica

El investigador necesita herramientas para **explorar, resumir y contextualizar** una categoría que ya ha sido definida (sola, no en relación con otras).

**1.1 Resúmenes y narrativas**

* Generar un **resumen descriptivo** de la categoría: definición, ejemplos típicos, frecuencia (cuántos segmentos, en cuántos documentos), excepciones.
* Generar una **viñeta narrativa**: un relato breve (1-2 párrafos) que integre los segmentos más representativos como una escena única, escrita en estilo etnográfico.
* Generar un **resumen poético** (opcional): extraer frases emocionalmente potentes o metáforas y organizarlas como verso libre o prosa lírica.

**1.2 Visualizaciones de una categoría a través de documentos**

* **Modelo de distribución**: diagrama radial donde la categoría está en el centro y los documentos alrededor, con líneas de grosor proporcional a la cantidad de segmentos de esa categoría en cada documento. Útil para ver qué casos son más representativos.
* **Línea de tiempo**: si los documentos contienen fechas o secuencias, mostrar cómo aparece la categoría a lo largo del tiempo (cronología de eventos asociados).
* **Diagrama de proceso inductivo**: a partir de la secuencia temporal de los segmentos dentro de cada documento, inferir un flujo de pasos (A → B → C) que caracteriza a la categoría. El investigador puede ajustar manualmente.

**1.3 Estadísticas y contextualización cuantitativa (small‑n)**

* Mostrar **frecuencias simples**: número de segmentos, número de documentos.
* Si hay variables de documento (género, edad, región, etc.), permitir **cruzar la categoría con una variable**: tabla de contingencia (presencia/ausencia de la categoría por grupos) y prueba de chi‑cuadrado. El software debe explicar el resultado en lenguaje claro (ej. “la diferencia entre hombres y mujeres no es estadísticamente significativa”). Esto funciona con cruces automatizados a la power bi
* **Gráficos bivariados**: diagrama de barras agrupadas o de sectores que compare la proporción de documentos que contienen la categoría entre grupos.
* **Gráfico de palabras vs variables**: nube de palabras diferenciada por grupos (ej. una nube para hombres y otra para mujeres), para ver diferencias léxicas en los segmentos de la categoría.

**1.4 Diagramas personalizados de una categoría**

* Permitir al investigador **crear su propio diagrama** (tipo canvas) donde pueda colocar la categoría, añadir notas, citas, y dibujar conexiones manualmente. El software debe guardar esto como parte del memo de la categoría.

***

#### 5c.2. Análisis de varias categorías (relaciones entre ellas)

El investigador necesita herramientas para **ver cómo se relacionan dos o más categorías**, sin forzar causalidad (a menos que el investigador quiera explorarla inductivamente).

**2.1 Mapas conceptuales**

* Generar un **mapa conceptual** (nodos = categorías, aristas = relaciones). Opciones:
  * Mostrar solo las categorías (estructural).
  * Mostrar también **segmentos de ejemplo** al hacer clic o pasar el ratón.
  * **Colorear o filtrar por variables de documento**: al estilo ATLAS.ti, permitir que los nodos o aristas cambien de color según el valor de una variable (ej. rojo = aparece más en hombres, azul = más en mujeres). El investigador puede activar/desactivar este filtro.
* El mapa debe ser **interactivo**: arrastrar nodos, expandir/colapsar subcategorías, exportar como imagen.

**2.2 Diagramas de oposición o tipología**

* **Diagrama de Venn** (para 2-3 categorías): mostrar solapamientos (cuántos documentos o segmentos comparten dos categorías). Útil cuando las categorías son mutuamente excluyentes o se oponen.
* **Mapa de posiciones** (gráfico 2x2 o espectro): cuando hay dos dimensiones que se oponen (ej. “control externo” vs “autonomía”, o “baja frecuencia” vs “alta frecuencia”). El investigador elige dos categorías (o dos variables derivadas de categorías) y el software ubica cada documento como un punto en ese plano. Opcional: colorear los puntos según una tercera categoría.

**2.3 Diagramas de co‑ocurrencia o flujo (cuando no hay oposición)**

* **Diagrama de co‑ocurrencia**: grafo donde los nodos son categorías y las aristas tienen grosor proporcional al número de segmentos (o documentos) donde aparecen juntas. Útil para ver qué temas van de la mano.
* **Diagrama de Sankey**: muestra flujos secuenciales entre categorías (ej. “falta de tiempo” → “estrategias de ahorro” → “agotamiento”). El software infiere la secuencia a partir del orden de los segmentos en cada documento. El investigador puede ajustar el orden y la dirección.

**2.4 Diagramas causales o procesuales inductivos**

* **Diagrama causal** (exploratorio): el investigador propone una relación (A → B) y el software busca evidencia de secuencia temporal en los documentos (A aparece antes que B en los mismos documentos). Muestra el porcentaje de documentos donde se cumple la secuencia y los contraejemplos. No es una prueba estadística, solo una exploración.
* **Comparación de procesos entre grupos**: si hay una variable de grupo (ej. género, región), el software genera dos diagramas de flujo paralelos (uno por grupo) para mostrar si el proceso (secuencia de categorías) es similar o diferente.

***

#### 5c.3. Análisis de documentos vs. categorías (comparación de casos)

El investigador necesita herramientas para **comparar múltiples documentos entre sí** en función de las categorías que contienen.

**3.1 Matrices**

* **Matriz códigos × documentos**: tabla donde las filas son categorías, las columnas documentos (o conjuntos de documentos). Cada celda puede mostrar:
  * Presencia/ausencia (✓/✗).
  * Número de segmentos.
  * Un **resumen corto** generado por IA (útil para cuadrículas de resúmenes).
* **Matriz de tipologías**: cuando los documentos tienen variables categóricas (dicotómicas o tricotómicas), se puede crear una matriz donde las filas son combinaciones de valores de variables (ej. “mujer, zona urbana”, “hombre, zona rural”) y las columnas son categorías. Cada celda muestra la frecuencia o porcentaje de documentos de ese perfil que contienen la categoría.

**3.2 Mapa de clúster de códigos (análisis de agrupamiento)**

* Generar un **dendrograma** (árbol de clúster) que agrupe los documentos según la similitud de sus perfiles de codificación (qué categorías tienen y con qué intensidad). El investigador puede elegir:
  * Número de clústeres (3, 4, etc.).
  * Guardar la pertenencia a clúster como una nueva variable de documento para usarla en otros análisis.
* Opcional: **mapa de clúster de códigos** (en lugar de documentos) para agrupar categorías que suelen aparecer juntas.

**3.3 Herramientas de comparación visual por variables**

* **Comparación de procesos entre grupos** (ya mencionado en 2.4) también sirve aquí: el investigador selecciona dos o más conjuntos de documentos (ej. por una variable) y el software muestra diagramas de flujo paralelos.
* **Nubes de palabras comparativas**: una nube para cada grupo (ej. hombres / mujeres) basada en los segmentos de las categorías seleccionadas.

## Fase 6: Organización y Redacción

### 6a. Redacción empírica (formatos comunes)

* El usuario carga un conjunto de memos y códigos. El sistema devuelve un mapeo sugiriendo cómo se conectan los memos alrededor de esa categoría.
* El sistema despliega un menú de parametrización antes de redactar el documento final. Exige al usuario definir dos variables: **Público** (jurado, colegas, tomadores de decisiones) y **Objetivo** (resolver un problema, entretener/emocionar, enseñar, o accionar).
* El usuario ingresa un texto desordenado y escrito rápidamente (brain-dump). El sistema reescribe el texto para mejorar la fluidez y le devuelve preguntas estratégicas sobre dónde necesita profundizar o enfatizar más.
* El usuario elige un "esqueleto" narrativo para sus resultados. El sistema reordena los memos seleccionados según el formato elegido: Estudio de caso, Comparación, Narrativa cronológica, Historia de suspenso (dejando pistas analíticas) o Emblema (micro a macro).
* Si el usuario indica bloqueo o exceso de abstracción, el sistema extrae un documento o memo al azar (opción *serendipity*) y le pide al usuario que lo lea en voz alta. 
* **A**plica un filtro de estilo basado en la decisión metodológica del usuario según la matriz de voces. Alternativamente, el sistema sugiere cambiar sustantivos descriptivos a verbos/adverbios para forzar la abstracción.

| Persona     | Enfoque   | Estilos Disponibles para la IA                                                         |
| ----------- | --------- | -------------------------------------------------------------------------------------- |
| **Primera** | Directo   | Confesional (Relatos de campo), Autoetnografía, Juego de roles                         |
| **Primera** | Indirecto | Formal (académico clásico), Interpretativo, Proverbios (metafórico)                    |
| **Tercera** | Directo   | Etnodrama (guion de conflicto), Etnoteatro (con acotaciones escénicas), Colaborativo   |
| **Tercera** | Indirecto | Descriptivo (realista/visual), Crítico (estructuras de poder), Narrativo (cronológico) |



Para garantizar que el modelo de lenguaje actúe con rigor científico, el *System Prompt* del backend debe incluir reglas restrictivas claras. Tu analista puede traducirlas en restricciones del sistema (Non-Functional Requirements):

* **Regla de Fidelidad Absoluta (Anti-Alucinación):** "Bajo ninguna circunstancia inventes citas, datos, participantes o anécdotas. Debes utilizar estricta y únicamente la información provista en los memos y segmentos de texto del investigador. Si te falta información para completar una narrativa, deja un espacio en blanco `[Falta evidencia aquí]`."
* **Regla de Transparencia de Incertidumbre:** "Si la relación empírica entre dos categorías no es evidente en los datos proporcionados, indícalo explícitamente al investigador. No fuerces conexiones lógicas ni inventes causalidades que los datos no respaldan."
* **Regla de Preservación de la Voz:** "Al estructurar los resultados y presentar ejemplos, mantén absolutamente intactos los modismos, la gramática original, la intensidad emocional y el contexto de las citas directas de los sujetos de estudio. No "limpies" ni formalices la forma de hablar de los participantes."
* **Regla de Soberanía Humana:** "Tu rol es sugerir estructuras lógicas y limpiar borradores, no reemplazar el juicio analítico del investigador. Concluye tus síntesis lógicas pidiéndole al usuario que valide si el marco propuesto hace 'click' con su experiencia real en el campo de estudio."
* **Regla de Dignidad y No-Estigmatización:** "Al redactar descripciones de poblaciones, escenarios o individuos, utiliza un lenguaje neutro y dignificante. Evita la caricaturización o el exotismo, incluso cuando el investigador te pida aplicar tonos dramáticos (como el etnodrama) o narrativos."

### 6b. Codificación y redacción teórica

Recuperar todos los documentos de análisis:

* Memos de hipótesis, propiedades, relaciones, metodológicos y de muestreo de Memo\_Bank (OJO: todo memo está asignado a una o varias categorías)
* Descripciones de categorías
* Incluir cualquier memo de clasificación de medio proceso generado aquí

Un agente iterará sobre todos los memos y documentos del análisis al mismo tiempo, o hará resúmenes, para hallar cómo es que cada familia de códigos teóricos unen las categorías ya existentes. El agente escribe en `Sorting_Log`:

* Etiquetas de los grupos formados y lista de categorías por grupo. Justificación de las relaciones.
* Documentos **sin hogar** (no se asignan a ningún grupo).
* Decisiones ambiguas o colocaciones forzadas.

#### Iteraciones estándar (cada familia tiene su prompt)

1. **Temática** – *“Agrupa memos por tema o asunto compartido. No impongas categorías externas.”*
2. **Causal** – *“Identifica causas, efectos, condiciones mediadoras y variables intervinientes. Construye cadenas causales.”*
3. **Temporal / proceso** – *“Busca estructura antes/durante/después, etapas de progresión.”*
4. **Jerárquica / importancia** – *“Clasifica memos como centrales, periféricos, condiciones o consecuencias.”*
5. *(Opcional)***Oposición / tipología** – *“Agrupa por polos opuestos o perfiles contrastantes.”*
6. Y si no halla relación aún:

| Sesión | Criterio                                                                          | Familia teórica CGT que se evalúa |
| ------ | --------------------------------------------------------------------------------- | --------------------------------- |
| 5      | Oposición / contraste / polaridad                                                 | Familia tipológica / dimensional  |
| 6      | Seis Cs: condiciones, contexto, contingencias, consecuencias, covarianzas, causas | Familia de las Seis C             |
| 7      | Etapas de proceso social básico (entrada, paso, salida)                           | Familia de proceso                |
| 8      | Matrices de dos por dos (intersectar dos dimensiones)                             | Familia tipológica / de matrices  |

El agente genera un **memo de clasificación** por cada iteración y uno final:

* ¿Por qué se formaron esos grupos?
* ¿Qué insight teórico apareció?

Estos memos se convierten en **borradores de esquemas de capítulos**: cada grupo estable (que se repite en varias iteraciones) es una sección del informe.

Tras completar las iteraciones, el agente responde (cualitativamente, sin puntuación):

* ¿Qué estructuras reaparecen en múltiples iteraciones? ¿Qué documentos parecen ir juntos? ¿Por qué?
* ¿Qué disposiciones requirieron menos colocaciones forzadas?
* ¿Qué memos quedaron sin hogar y por qué? 
  * Montones **delgados** (pocos memos, evidencia débil).
  * Conexiones débiles entre montones.
  * Preguntas sin respuesta. ¿Dónde es escasa la evidencia en relación con la afirmación teórica que se está haciendo?
  **Dos rutas:**
  * **Brecha interna** (se puede llenar con datos existentes) → consultar `Transcript_DB` y reingresar a **Fase 5** (codificación selectiva) enfocada en esa brecha. Luego volver a esta fase.
  * **Brecha externa** (requiere nuevo conocimiento) → pasar a **Fase 6.6**.

Al final se elabora un documento final según los siguientes criterios:

* Escribir lo que dicen los memos — no imponer una estructura lógica externa sobre ellos
* Escribir en **tiempo presente** (la teoría describe procesos en curso, no eventos pasados)
* Escribir sobre **conceptos**, no sobre personas (nivel de abstracción teórica)
* Si una conexión entre secciones requiere una idea no presente en los memos, marcarla — es una brecha, no una deducción lógica

OJO: Monitorear la propia escritura continuamente (agente crítico) para:

* Afirmaciones que carecen de suficiente apoyo de memos
* Brechas lógicas entre secciones que requieren suposiciones no declaradas
* Propiedades que aparecen en el texto pero no tienen un memo correspondiente
* Conexiones asumidas pero nunca validadas empíricamente en las fases de codificación

Cuando se descubre una brecha:

* Marcar: *"La escritura reveló una brecha: \[Descripción de la brecha]"*
* Bucle: → Fase 6.5 (Gap\_Feeler) → Fase 5.5 (muestreo dirigido) → volver a la escritura

### 6c. Discusión con la teoría extante

#### Discusión contrastiva (validación externa de hallazgos microanalíticos)

* **Seleccionar un hallazgo o categoría** y lanzar una búsqueda automática de literatura relevante en bibliotecas internas o externas.
* **Generar una tabla comparativa** de dos columnas («Nuestro hallazgo» / «Hallazgo en la literatura») pre-llenada por IA basada en similitud semántica. El investigador edita y ajusta.
* **Calcular un «índice de consistencia» cualitativo** que muestre: «El 70% de los autores revisados coinciden; el 30% presentan matices o discrepancias». No es estadístico, es un recuento orientativo.
* **Identificar contradictores** automáticamente: «Autor Y (2020) afirma lo contrario a tu hallazgo sobre X. ¿Quieres examinar su evidencia?».
* **Generar un informe de tensiones** que enumere puntos de acuerdo, desacuerdo y silencio bibliográfico.

#### Diálogo de deconstrucción (bricolaje teórico e interpelación)

* **Cargar un texto teórico clásico** (o varios) y pedir: «Enfrenta este texto con mis datos categoría por categoría». El sistema devuelve un informe de tensiones: «Bourdieu dice X; en tu entrevista 3 ocurre Y».
* **Activar el «modo abogado del diablo» aplicado a la literatura**: el sistema argumenta desde la posición de un autor clásico para desafiar tus hallazgos, y luego tú respondes con tus datos. El resultado es un borrador de diálogo.
* **Detectar puntos ciegos** de la literatura dominante: el sistema analiza las referencias geográficas, de género o disciplinares de los textos cargados y alerta: «El 80% de los autores son de contextos anglosajones. ¿Quieres buscar literatura de otras regiones?».
* **Generar un contraargumento estructurado**: el investigador selecciona un pasaje de un autor, el sistema propone tres objeciones basadas en tus datos.
* **Guardar el diálogo** como un memo interpretativo que luego puede convertirse en sección de discusión.

#### Apoyo causal para inferencias contrafácticas (explicación estructural)

* **Construir visualmente una cadena causal** (diagrama de flechas) entre categorías (A → B → C) basada en la secuencia temporal observada en los datos.
* **Para cada flecha**, el sistema busca en la literatura afirmaciones que respalden esa conexión causal, mostrando fragmentos de textos con relaciones similares.
* **Calcular una puntuación de respaldo bibliográfico**: «Esta relación (A→B) aparece respaldada en 5 de los 12 textos revisados; 2 la contradicen; 5 no la mencionan».
* **Identificar mecanismos causales** propuestos en la literatura que podrían explicar la conexión observada en tus datos.
* **Generar un memo de «justificación causal»** que integre la evidencia empírica (tus datos) y el respaldo bibliográfico (citas).

#### La literatura como «más datos» (integración final por comparación constante)

* **Importar literatura** (PDFs, textos, referencias) en una carpeta especial, pero con la misma interfaz de codificación que los documentos empíricos.
* **Codificar segmentos de literatura** arrastrándolos a categorías existentes o creando nuevas categorías.
* **Comparar automáticamente** las propiedades de una categoría (extraídas de tus datos) con los fragmentos de literatura. El sistema señala: «Este párrafo de Autor X introduce una propiedad no documentada: ‘resistencia pasiva’. ¿Deseas añadirla?».
* **Densificar la categoría central** pidiendo: «Busca en la literatura ejemplos adicionales de esta propiedad». El sistema recupera citas relevantes y las presenta como sugerencias.
* **Registrar la procedencia** de cada integración (cita completa) para el informe final.

#### Fusión heurística y etiquetado retrospectivo (conceptos sensibilizadores)

* **Seleccionar una categoría** y pedir «Sugiere conceptos cercanos en la literatura». El sistema busca en los textos cargados términos que se solapan semánticamente con la definición de la categoría.
* **Mostrar una nube de conceptos afines** con indicador de frecuencia y similitud. El investigador clic en uno para ver cómo se usa en el texto original.
* **Comparar la definición de tu categoría** con la definición de un concepto de la literatura, resaltando solapamientos y diferencias.
* **Renombrar la categoría** usando el concepto seleccionado, conservando el nombre anterior en el historial (trazabilidad).
* **Generar un memo de «anclaje teórico»** que explique por qué ese concepto de la literatura captura bien tu categoría, y señale qué matices propios añades.

#### Tránsito de teoría sustantiva a teoría formal

* **Cargar nuevos conjuntos de datos** (de otra población, región, sector) y aplicar automáticamente la teoría sustantiva existente.
* **Señalar puntos de desajuste** (emergent fit): el sistema lista las categorías que no encajan, las propiedades que fallan y los nuevos incidentes no explicados.
* **Sugerir modificaciones a la teoría** para absorber esos desajustes: añadir propiedades, dividir categorías, ajustar definiciones.
* **Comparar la teoría sustantiva con teorías formales existentes** en la biblioteca, mostrando solapamientos, divergencias y posibles integraciones.
* **Simular la aplicación de la teoría formal** a un caso hipotético generado por IA y mostrar cómo explica el fenómeno.
* **Generar un borrador de artículo** que presente la teoría formal, contrastándola con la literatura y mostrando su poder explicativo para múltiples contextos.

#### Redacción de recomendaciones aplicadas (praxis y acción)

* **Extraer soluciones locales** de los propios datos: el sistema busca segmentos donde los participantes resolvieron un problema y los resume como recomendaciones.
* **Generar borradores de recomendaciones** con plantillas: «Para abordar \[categoría problema], los datos sugieren \[acción], basado en \[cita]».
* **Adaptar el tono y formato** según el destinatario seleccionado por el investigador (gestores, profesionales, comunidad, políticos). El sistema reescribe las recomendaciones.
* **Evaluar el impacto potencial** de cada recomendación: buscar en la literatura estudios de intervención similares y mostrar sus resultados.
* **Exportar las recomendaciones** como un informe ejecutivo separado, con enlaces directos a los segmentos originales que las justifican.

#### Reflexividad y evaluación de criterios de calidad

* **Registrar automáticamente la pista de auditoría**: guarda versiones de categorías, memos, decisiones de fusión/división, cambios de nombre, con fechas y justificaciones.
* **Generar un informe de reflexividad** con preguntas guía: «¿En qué momento tu posición personal pudo influir?», «¿Qué sesgos reconoces en la interpretación de X?». El investigador responde, y el sistema guarda las respuestas como memos metodológicos.
* **Comparar el proceso** con listas de verificación estándar (COREQ, criterios de Lincoln y Guba) y señalar qué aspectos están documentados y cuáles faltan.
* **Producir un diagrama de evolución** de las categorías a lo largo del tiempo (versiones) para mostrar el proceso analítico.
* **Exportar el informe de auditoría** como anexo del trabajo final, demostrando la confirmabilidad y dependencia.

#### Elaboración de agendas de investigación futura

* **Detectar lagunas automáticamente** a partir de: contradicciones no resueltas en los datos, propiedades de categorías con pocos incidentes, relaciones no exploradas, variables del POOL no utilizadas.
* **Sugerir preguntas de investigación** en modo tentativo, basándose en esas lagunas y en vacíos detectados en la literatura (ej. «¿Cómo varía la categoría central en el tiempo?», «¿Qué papel juega la variable X en otros contextos?»).
* **Proponer metodologías alternativas** para abordar cada pregunta (estudio longitudinal, análisis comparado, métodos mixtos, etc.).
* **Generar un mapa de futuras líneas** como diagrama de ramificaciones, conectando preguntas con métodos y con literatura relevante.
* **Permitir al investigador** seleccionar, editar y priorizar las preguntas que luego formarán la sección «trabajos futuros».

#### Análisis de silencios y visión jerárquica (in-data) aplicado a la literatura

Además de comparar hallazgos con literatura, el sistema puede analizar **qué temas están ausentes** en la revisión bibliográfica existente.

-*“¿Qué conceptos relevantes de mis datos no aparecen en la literatura cargada?”* → Lista de vacíos bibliográficos.

-*“¿Qué perspectivas teóricas no están representadas en mi corpus de referencias?”* → Sugiere autores o escuelas que podrían dialogar con los datos.

-*“Visión jerárquica de la literatura”* → Muestra cómo las palabras clave se agrupan en escuelas, éstas en paradigmas, y cómo se relacionan con los niveles de tu teoría (palabras → clases → tópicos → categorías → teoría).

#### Contextualización externa y muestreo de data complementaria (out-data)

Ampliamos el muestreo teórico más allá de los datos empíricos originales, incorporando fuentes externas sugeridas automáticamente.

-*“Busca datos de contraste para mi categoría X”* → El sistema genera una consulta estructurada (países, grupos sociales, períodos) y la envía a repositorios conectados (si los hay). Devuelve una lista de fuentes potenciales con justificación (basada en Abbott: paralelismo estructural; Hammersley: casos que pongan a prueba los límites; Becker: mundos sociales adyacentes).

-*“Simula cómo cambiaría mi teoría si añadiéramos datos de \[población/contexto]”* → El sistema realiza un razonamiento contrafáctico: modifica las propiedades de las categorías según lo que cabría esperar del nuevo contexto y muestra un delta teoría (antes/después). Esto no es una prueba empírica, sino un ejercicio heurístico para identificar supuestos sensibles.

#### Generalización externa y traducción comparativa

Se añaden herramientas específicas para apoyar la transferencia de hallazgos a otros dominios, siguiendo las recomendaciones de Hammersley (generalización moderada) y Abbott (analogía estructural).

-*“Genera un informe de generalización moderada”* → El sistema toma la teoría central, enumera las condiciones contextuales (población, temporalidad, interacciones) y propone **dominios de transferencia plausible**. Incluye un nivel de confianza cualitativo (bajo, medio, alto) basado en la similitud de condiciones.

-*“Busca casos paralelos en otros campos”* → Utiliza el RAG bibliográfico para encontrar estudios que, aunque traten objetos diferentes, compartan una **estructura de relaciones** similar (ej. “evitación algorítmica” en repartidores puede ser análoga a “evitación burocrática” en funcionarios). El sistema extrae las analogías y las presenta como sugerencias para la discusión.

-*“Crea un mapa de términos traducibles”* → Para cada categoría o propiedad, el sistema propone términos equivalentes en tres jergas disciplinares (ej. sociología, psicología, economía). Esto facilita la publicación interdisciplinaria y la búsqueda de literatura cruzada.

-*“¿Qué preguntas quedarían sin respuesta si trasladáramos mi teoría a \[país/colectivo]?”* → El sistema realiza una prueba de sensibilidad inversa: enumera supuestos que podrían no cumplirse y sugiere rediseños metodológicos para adaptar la teoría.

#### Ética de la generalización y devolución

Se añade un subapartado final sobre **devolución y responsabilidad externa**:

-*“Prepara una sección de limitaciones para públicos no académicos”* → Toma los hallazgos y escribe un resumen en lenguaje llano, destacando qué conclusiones son robustas y cuáles tentativas, y advierte sobre riesgos de mala interpretación o estigmatización si la teoría se aplica sin matices.

-*“Audita la posible aplicación de mi teoría en políticas públicas”* → Busca en el RAG casos históricos donde marcos similares hayan sido usados (o mal usados) en intervenciones. Señala alertas éticas y sugiere salvaguardas.

***

## Anexos

### Manejo de errores y excepciones





| Situación                                                                                   | Lo que falta                                                                               | Acción sugerida                                                                                                              |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| **Fallo de un agente IA** (timeout, respuesta malformada)                                   | No se define reintento ni circuito de degradación                                          | “Reintentar hasta 2 veces con backoff exponencial; si persiste, marcar el ítem como ‘requiere revisión manual’ y continuar.” |
| **Conflicto entre dos agentes** (ej. Proponedor y Testeador dan resultados contradictorios) | No hay resolución automática                                                               | “Se eleva al investigador con un memo de ‘conflicto entre agentes’ y ambos resultados.”                                      |
| **Pérdida de conexión con la BD**                                                           | No hay estrategia de persistencia local                                                    | “Los cambios se guardan localmente en caché y se sincronizan al restaurar conexión.”                                         |
| **Segmento demasiado largo** (excede el límite de embedding)                                | No se especifica                                                                           | “Segmentos > 512 tokens se dividen por párrafos antes de ingresar al RAG.”                                                   |
| Límites de iteraciones                                                                      | Máximos globales para evitar bucles infinitos no solo por variable, sino por fase completa | “La Fase 5b (selectiva) terminará automáticamente tras 100 iteraciones totales, notificando al investigador.”                |
| Tamaño del Búfer de Residuos                                                                | Cuándo se purga o se archiva                                                               | “El búfer no crecerá más allá de 500 segmentos; los excedentes se archivan con marca ‘pendiente de revisión humana’.”        |
| Rendimiento de RAG                                                                          | Latencia máxima, número de resultados por consulta                                         | “Cada consulta RAG devolverá máximo 5 fragmentos, con timeout de 3 segundos.”                                                |

* ¿Cómo se actualizan los prompts de los agentes sin perder trazabilidad?
* ¿Se permite al investigador ajustar los prompts del sistema?
* ¿Se registra la versión del modelo de IA (GPT-4, Claude, etc.) en cada ejecución?

### Tabla 1: Criterios de saturación (ampliada y unificada)





| Nivel                       | Criterio                                                                                                  | Umbral                                       | Condición de reinicio                                                           | Acción al alcanzar saturación                                                                                 |
| --------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| **Incidente**               | Nuevos incidentes no añaden nuevas propiedades a una categoría                                            | 0 nuevas propiedades en últimos 5 incidentes | Aparece una nueva propiedad → contador a 0                                      | La categoría se marca como “estable para esa propiedad”                                                       |
| **Categoría (descriptiva)** | Iteraciones consecutivas sin cambios en propiedades, definición o ejemplos                                | 3 iteraciones                                | Se detecta un contraejemplo o una nueva variación → contador a 0                | La categoría se considera **saturada descriptivamente**                                                       |
| **Relacional (abductiva)**  | Misma relación (A→B) aparece en documentos distintos sin contraejemplo                                    | 5 documentos (mínimo)                        | Aparece un contraejemplo (A y no B) → contador a 0 y documento el contraejemplo | La relación se acepta como **empíricamente respaldada**                                                       |
| **Fase (selectiva)**        | Todas las categorías con relevancia ≥ 4 están saturadas Y todas las relaciones postuladas están saturadas | Ambas condiciones simultáneamente            | No aplica (es una condición de término)                                         | Se dispara la salida de la Fase 5b                                                                            |
| **Global**                  | Fase selectiva terminada + Búfer de Residuos vacío o todas las anomalías justificadas                     | Confirmación explícita del investigador      | Investigador decide volver a abrir el análisis                                  | Se declara la **teoría saturada**                                                                             |
| **Guardia de bucle**        | Iteraciones máximas por variable/categoría antes de revisión forzada                                      | 20 iteraciones                               | No se reinicia; se fuerza intervención humana                                   | Se activa un memo de advertencia y se pide al investigador decidir (continuar, ajustar umbrales, recodificar) |

### Tabla 2: Bucles de retroalimentación (feedback loops) entre fases





| Evento desencadenante                                                                                                                             | Fase origen | Fase destino                | Acción automática                                                                          | ¿Requiere confirmación del investigador?                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | --------------------------- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| Detección de una metáfora o figura retórica recurrente en una clase                                                                               | 2 (o 5a)    | 4a (refinamiento)           | Generar un memo de hipótesis sobre posible propiedad o dimensión implícita                 | No (se añade al Memo\_Bank automáticamente, pero el investigador puede revisarlo) |
| Inconsistencia entre léxico dominante y tópicos semánticos (ej. clase A usa palabras de emoción pero BERTopic la asigna a “procedimientos”)       | 2           | 4b                          | Sugerir una posible fusión o división de categorías basada en la tensión léxico-semántica  | Sí (se muestra un informe de “tensión interpretativa” y se pide decisión)         |
| Un término o grupo de palabras tiene alta contribución a una clase pero baja presencia en los documentos de esa clase (según análisis de calidad) | 2           | 1 (ingesta) o 5b (muestreo) | Sugerir revisar la codificación de esos documentos o añadir nuevas fuentes para clarificar | Sí (se notifica como posible error de segmentación o necesidad de nuevos datos)   |
| La comparación inter-clases léxicas muestra un solapamiento >70% entre dos clases                                                                 | 2           | 4b                          | Activar automáticamente la condición de fusión (sin esperar la ronda normal)               | Sí (se muestra la evidencia y se pregunta si fusionar)                            |
| Falla prueba de intercambiabilidad (CGT)                                                                                                          | 4d          | 4a                          | Dividir o refinar la categoría; reasignar segmentos                                        | Sí (se muestra diff antes/después)                                                |
| Condición de fusión detectada ( >80% ejemplos compartidos)                                                                                        | 4b          | 4a                          | Fusionar categorías; unificar descripciones                                                | Sí (se muestra propuesta de fusión)                                               |
| Categoría falla saturación después de memory wipe                                                                                                 | 5b          | 4c (opción)                 | Sugerir recodificación masiva                                                              | Sí (investigador decide si ejecutar)                                              |
| Brecha identificada durante sorting (falta evidencia)                                                                                             | 6b          | 5b (TheoSampler)            | Diseñar muestreo teórico dirigido a esa brecha                                             | No (automático, pero se notifica)                                                 |
| Brecha externa (requiere nuevos datos)                                                                                                            | 6b          | 1.1 (ingesta)               | Abrir asistente para importar nueva fuente                                                 | Sí (investigador selecciona fuente)                                               |
| Brecha descubierta durante escritura                                                                                                              | 6a          | 6b (Gap\_Feeler)            | Reabrir fase de clasificación para esa sección                                             | No (automático, con memo)                                                         |
| Contraejemplo encontrado en bucle de comparación                                                                                                  | 5b          | 5b                          | Reiniciar contador de saturación; documentar contraejemplo                                 | No (registro automático)                                                          |
| Tensiones no resueltas en memos                                                                                                                   | 4c          | 4d                          | Sugerir reformulación de preguntas de investigación                                        | Sí (se muestran alternativas)                                                     |
|                                                                                                                                                   |             |                             |                                                                                            |                                                                                   |

### Tabla 3: Gestión de memoria (contexto de IA, caché, almacenamiento persistente)





| Tipo de memoria                         | Contenido                                                                             | Alcance                                                | ¿Cuándo se limpia?                                                | ¿Qué se preserva después de limpieza?                                                          |
| --------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| **Contexto permanente**                 | Preguntas de investigación + contexto población + declaración de preocupación central | Toda la sesión                                         | Nunca                                                             | –                                                                                              |
| **Contexto de trabajo por fase**        | Resúmenes de resultados de la fase actual, definiciones activas de categorías         | Fase actual                                            | Al cambiar de fase (ej. Fase 4 → Fase 5)                          | Solo las definiciones de categorías y el POOL se transfieren a la siguiente fase               |
| **Contexto de agente por iteración**    | Prompt actual, últimos 5 segmentos o incidentes comparados                            | Un ciclo de agente (ej. una comparación de documentos) | Al terminar cada iteración (o al fallar saturación – memory wipe) | Las definiciones de categorías y la preocupación central (se reinyectan en el siguiente ciclo) |
| **Caché de resultados de codificación** | Resúmenes de documentos y segmentos ya procesados                                     | Ventana rodante de 3 documentos                        | Cada 3 documentos (se refresca)                                   | Los resúmenes se guardan en Memo\_Bank (persistente) antes de limpiar                          |
| **Almacenamiento persistente**          | Memo\_Bank, POOL de variables, categorías, Búfer de Residuos, historial de cambios    | Todo el proyecto                                       | Nunca (crece)                                                     | –                                                                                              |
| persistente (análisis)                  | Resultados de Reinert, BERTopic, embeddings, RF/SHAP, MCA, etc. por clase             | Todo el proyecto                                       | Nunca (se acumulan versiones si se repiten análisis)              | – (no aplica limpieza)                                                                         |

### Tabla 4: Roster de agentes (integrado y ampliado con tipos)





| ID  | Nombre del agente                            | Fase(s) | Tipo               | Función principal                                                                                               | Entrada clave                                                            | Salida clave                                             |
| --- | -------------------------------------------- | ------- | ------------------ | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------- |
| A01 | Open Coder                                   | 3       | Procesamiento      | Segmentar texto en unidades de comportamiento                                                                   | Texto bruto del documento                                                | Segmentos con marcas de unidad                           |
| A02 | Resegmentar-Doc                              | 2–3     | Procesamiento      | Reagrupar segmentos por lógica de comportamiento                                                                | Segmentos iniciales                                                      | Segmentos agrupados                                      |
| A03 | Clusterizador (doc)                          | 3       | Agrupación         | Agrupar segmentos dentro de un documento                                                                        | Segmentos de un documento                                                | Categorías intra-documento                               |
| A04 | Clusterizador informado                      | 3       | Agrupación         | Clustering de códigos abiertos entre documentos                                                                 | Todos los códigos y segmentos                                            | Sistema de categorías inicial unificado                  |
| A05 | Proponedor de memos                          | 3       | Generación         | Generar memos de hipótesis y propiedades                                                                        | Patrones acumulados cada 3 documentos                                    | Memos (hipótesis y propiedades)                          |
| A06 | Testeador de memos                           | 3       | Evaluación         | Evaluar memos como SAT/MOD/FORCED                                                                               | Memos generados                                                          | Clasificación y sugerencias de modificación              |
| A07 | Agrupador                                    | 4f      | Agrupación         | Agrupar constructos por superposición de indicadores                                                            | Categorías refinadas                                                     | Constructos agrupados                                    |
| A08 | AI Agent1 (hipótesis)                        | 4f      | Consolidación      | Consolidar y deduplicar hipótesis                                                                               | Todos los memos de hipótesis                                             | Conjunto de hipótesis coherentes                         |
| A09 | AI Agent2 (doc coding)                       | 4f      | Codificación       | Recodificar documentos contra esquema refinado                                                                  | Categorías refinadas, segmentos                                          | Segmentos recodificados                                  |
| A10 | AI Agent3 (var codebook)                     | 4f      | Derivación         | Derivar libro de códigos de variables                                                                           | POOL de variables, criterios de muestreo                                 | Lista ordenada de variables útiles                       |
| A11 | AI Agent4 (insight grouping)                 | 4c      | Agrupación         | Agrupar insights recurrentes de memos                                                                           | Memo\_Bank                                                               | Grupos temáticos de memos                                |
| A12 | AI Agent6 (thematic clusters)                | 4c      | Organización       | Organizar Memo\_Bank en clústeres temáticos                                                                     | Memo\_Bank completo                                                      | Índice/mapa de memos por tema                            |
| A13 | AI Agent7 (hypothesis testing)               | 4c      | Validación         | Probar hipótesis contra todos los documentos                                                                    | Hipótesis, corpus codificado                                             | Evidencia / contraejemplos por hipótesis                 |
| A14 | Main\_Concern\_Sensor                        | 4d      | Sensado            | Detectar preocupación principal latente                                                                         | Códigos + Memo\_Bank                                                     | Declaración de preocupación principal                    |
| A15 | Core\_Emergence\_Detector                    | 4d      | Selección          | Identificar categoría central cualitativamente                                                                  | Preocupación principal, categorías candidatas                            | Lista priorizada de categorías centrales                 |
| A16 | Interchangeability\_Tester                   | 4d      | Prueba             | Probar intercambiabilidad de incidentes                                                                         | Incidentes de la categoría candidata                                     | Veredicto (intercambiable / no intercambiable)           |
| A17 | TheoSampler                                  | 5b      | Muestreo           | Diseñar estrategia de muestreo teórico                                                                          | Categorías con score ≥4, POOL                                            | Plan de muestreo (casos contraste/extremos/consistentes) |
| A18 | Compara varios docs                          | 5b      | Comparación        | Comparar documentos por combinación de categorías y variables                                                   | Datos de combinación (lacat2)                                            | Insights nuevos/confirmados/actualizados                 |
| A19 | Core Concern Finder                          | 5b      | Confirmación       | Reconfirmar preocupación central al inicio de selectiva                                                         | Categorías refinadas                                                     | Declaración definitiva de preocupación central           |
| A20 | Filtra por relación                          | 5b      | Filtrado           | Asignar puntuación de relevancia 1–5 a cada categoría                                                           | Categorías, preocupación central                                         | Puntuaciones en DB, categorías filtradas (≥4)            |
| A21 | Gap\_Feeler                                  | 6b      | Detección          | Identificar áreas delgadas y conexiones débiles en sorting                                                      | Sorting\_Log, memos                                                      | Lista de brechas (internas/externas)                     |
| A22 | Literature\_Comparer                         | 6c      | Comparación        | Comparar teoría con literatura como diálogo                                                                     | Teoría saturada, RAG bibliográfico                                       | Tablas comparativas, informes de tensiones               |
| A23 | Theory\_Evolver                              | 7       | Evolución          | Gestionar teoría viva y refinamiento continuo                                                                   | Nueva data, teoría actual                                                | Teoría actualizada con log de cambios                    |
| A24 | Natural\_Writer                              | 6a      | Escritura          | Escribir desde memos clasificados en tiempo presente                                                            | Montones de memos (Sorting\_Log)                                         | Borrador de sección de informe                           |
| A25 | MemoMaker (nodo Generate)                    | 5b      | Síntesis           | Integrar 4 análisis paralelos en informe de memo                                                                | Patrones, propiedades, causas, consecuencias                             | Memo integrado por categoría                             |
| A26 | MemoMaker (simplificación de variaciones)    | 5b      | Reducción          | Producir tablas de doble entrada para dimensiones correlacionadas                                               | Salida de Generate                                                       | Tablas de dimensiones                                    |
| A27 | MemoMaker (búsqueda de correlaciones)        | 5b      | Análisis           | Cruzar tablas y construir matrices 2×2                                                                          | Tablas de variaciones + metadatos                                        | Matrices 2×2 con tipologías                              |
| A28 | Sorting\_Log (agente)                        | 6b      | Registro           | Iterar sobre familias teóricas, generar memos de clasificación                                                  | Todos los memos y categorías                                             | Log de grupos, memos sin hogar, justificaciones          |
| A29 | Extractor de figuras retóricas               | 2, 5a   | Procesamiento (IA) | Identificar metáforas, evidencialidad, ironía, etc. por clase                                                   | Segmentos de una clase (o documento)                                     | Lista de figuras retóricas con ejemplos y clase asociada |
| A30 | Sintetizador multi-análisis                  | 2, 6    | Síntesis (IA)      | Generar resumen por clase de todos los análisis previos (léxico, semántico, socio-lingüístico)                  | Salidas de todos los análisis por clase, más metadatos                   | Resumen integrado por clase (texto + tablas)             |
| A31 | Recomendador de relaciones léxico-semánticas | 6       | Recomendación (IA) | Sugerir vínculos entre patrones léxicos y tópicos semánticos, y ofrecer comparaciones entre resúmenes de clases | Resúmenes de clase, datos de contribución léxica, tablas de transiciones | Columnas de comparación y recomendaciones hipotéticas    |
|     |                                              |         |                    |                                                                                                                 |                                                                          |                                                          |

[Análisis](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/FanRREWwdpDg0N_Ka94Nv)

[Deployment](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/wGm4J6HtuUnuFZe7Wt8Pt)

[Plan](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/KKwwaiqKfmEW4DbRbqkwc)

[Diagrama de clases](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/UtxuLWs59Yiiui237EAdN)

[Diagrama de componentes](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/hA6YMNyQYrrLBuarLF-T9)

[Github](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/dLaNJ9udHaze8zHm2z3eR)

[Seguridad](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/CZQYugu4HWyN8VJBZmLVq)

[Sequence (escenarios)](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/y-ttID16erCELoElVHOS0)

[Estructura de costos](assets://./workspace/afd7131b-bb46-4e70-8ebc-61301c2c5c49/Dr7gGDHYvWzAeoSrJkA0z)

