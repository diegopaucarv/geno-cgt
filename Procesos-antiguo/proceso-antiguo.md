# Resumen de Workflows — Procesos-antiguo

> Generado: 2026-06-14 | Basado en `Documentacion/Proceso de Análisis.md`
> Cada workflow es un JSON de n8n. Se analiza cada nodo con su lógica interna.

---

## 1. `Formateador de entrevistas.json`
### Fase 1 — Ingesta de Datos (L64-117)
**Propósito:** Leer transcripciones TXT crudas del disco, limpiarlas y mapearlas a JSON estructurado según la guía de entrevista de cambio climático (32 preguntas en 6 secciones).

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `When clicking 'Execute workflow'` | manualTrigger | Disparador manual |
| 2 | `Read/Write Files from Disk` | readWriteFile | Lee archivos con glob `/txt_outputs/*.txt` |
| 3 | `Extract from File` | extractFromFile | Extrae texto (operation: `text`) |
| 4 | `DeepSeek Chat Model` | lmChatDeepSeek | Modelo `deepseek-reasoner`, DeepSeek account 2. **Compartido** por ambos agentes (AI Agent + AI Agent1). |
| 5 | `AI Agent` | agent (langchain) | **Agente Mapeador/Formateador.** Prompt de ~3000 chars con: (a) guía completa de 32 preguntas agrupadas en 6 secciones (I: Sociodemográficos, II: Concepciones CC, III: Percepciones entorno, IV: Rol educación, V: Acciones mitigación, VI: Perspectiva futura), (b) reglas estrictas: limpieza en vuelo (corregir ortografía, puntuación, palabras mal transcritas), mapeo inteligente (buscar respuestas sin importar orden), cero alucinaciones (`"NO ESTÁ PRESENTE"` para strings, `[]` para arrays), (c) salida JSON puro sin preámbulos. |
| 6 | `Structured Output Parser` | outputParserStructured | Schema del output de AI Agent: objeto JSON anidado con 6 secciones (`datos_sociodemograficos`, `concepciones_cambio_climatico`, `percepciones_entorno`, `rol_educacion_universitaria`, `acciones_mitigacion`, `perspectiva_futura`), cada una con sus campos (strings y arrays). Incluye campo `Alias` (nombre de flor para anonimizar). |
| 7 | `AI Agent1` | agent (langchain) | **Agente Segmentador Estructural.** Mismo prompt de guía pero con objetivo distinto: segmentar la transcripción en bloques secuenciales literales (NO resumir, NO parafrasear). Reglas: (a) literalidad — copiar respuesta exacta, (b) limpieza de forma no de fondo, (c) interrupciones del entrevistador entre paréntesis dentro del bloque, (d) preguntas faltantes se ignoran (no crea segmentos vacíos), (e) texto huérfano → `numero_pregunta: 0`, sección `"TEXTO_NO_ASIGNADO"`. |
| 8 | `Structured Output Parser1` | outputParserStructured | Schema de segmentos: `segmentos[]` con `numero_pregunta` (0-32), `seccion_entrevista` (enum de 6 secciones + TEXTO_NO_ASIGNADO), `texto_literal`. |
| 9 | `Code in Python (Beta)` | code | **Zip de files + outputs:** Itera con `zip(files, output)`, para cada par crea `{file: fileName, output: output_item.json.output}`. |
| 10 | `Convert to File` | convertToFile | Convierte a JSON archivo (modo `each`, nombre `={{ $json.file }}.json`) |
| 11 | `Read/Write Files from Disk1` | readWriteFile | Escribe a `tmp/{fileName}` la salida del segmentador |
| 12 | `Code in Python (Beta)1` | code | **Zip de files + metadata:** Similar al anterior pero usa `metadata` como key en vez de `output`. Itera `zip(files, AI Agent output)`. |
| 13 | `Convert to File1` | convertToFile | Convierte la metadata a JSON archivo |
| 14 | `Read/Write Files from Disk2` | readWriteFile | Escribe metadata a `tmp/{fileName}` |
| 15 | `Merge` | merge | Une ambas ramas (segmentos + metadata) al final (inputs 0 y 1). |

### Flujo de conexiones
```
When clicking → Read/Write Files → Extract from File
  ├─[bifurca]→ AI Agent (+ DeepSeek + Structured Output Parser) → Code1 → Convert to File1 → Read/Write2 → Merge[1]
  └─[bifurca]→ AI Agent1 (+ DeepSeek + Structured Output Parser1) → Code → Convert to File → Read/Write1 → Merge[0]
```

### Overlaps detectados
- **AI Agent** produce metadata JSON estructurada (datos sociodemográficos, concepciones, etc.) → alimenta metadata de documentos en fases posteriores.
- **AI Agent1** produce segmentos literales con numero_pregunta → estos segmentos son el input del `Open Coder - Document`.
- Ambos outputs se guardan en `/tmp/` con el mismo `fileName` pero distinto contenido, y luego se hace merge.

---

## 2. `Open Coder - Document.json`
### Fase 2 (Segmentación semántica) + Fase 3 (Open Coding por documento)
**Propósito:** Recibir una transcripción (vía `When Executed by Another Workflow` desde `Open Coder - CCA`), segmentarla semánticamente (no por preguntas sino por cambios de tópico), y luego codificar cada segmento con el método CGT de *explication de texte*.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `When Executed by Another Workflow` | executeWorkflowTrigger | **Trigger principal.** Recibe llamado externo con payload: `{numpages, numrender, info: {Title, ...}, text: "transcripción completa..."}`. |
| 2 | `Code in Python (Beta)` | code | **Limpieza inicial:** `text.replace('\n', ' ').replace('\r', ' ')`, codifica a base64 como `text_binary`. |
| 3 | `If` | if | **Filtro de archivos vacíos:** Condición `$json` exists AND `parseFloat($json.fileSize) > 0`. False branch → vacío (termina). True branch → continúa. |
| 4 | `Read/Write Files from Disk1` | readWriteFile | Lee `/tmp/{Title}_1` (archivo cache de ejecución previa). `alwaysOutputData: true`. |
| 5 | `Segmenter-UnstInterviews` | agent (langchain) | **Segmentador semántico.** Prompt: "You are a machine that divides unstructured conversations into semantically related segments." NO usa preguntas de entrevista como criterio. Usa cambios de tópico y puntuación. Output: `segment_number`, `topic_name` (frase tema en español), `summary` (oración descriptiva), `length` (número de oraciones), `first_10` (primeras 10 palabras exactas), `context` (última oración antes del segmento). |
| 6 | `Structured Output Parser` | outputParserStructured | Schema de segmentos del Segmenter. |
| 7 | `Hacedor de texto` | code (Python) | **Reconstructor de segmentos:** Toma el texto completo original, el `first_10` de cada segmento como ancla, y usa lógica de dots (puntos) para encontrar los límites reales. Calcula `start_bound` (2 puntos válidos antes del ancla) y `end_bound` (N puntos después según `length`). Extrae `text` = subcadena entre límites. |
| 8 | `AI Agent1` | agent (langchain) | **Open Coder (explication de texte).** Prompt detallado: (A) Explication de Texte — leer palabra por palabra, identificar actores, acciones, consecuencias; NO etiquetar aún. (B) Topic alignment — generar `study_question` que el segmento responde. (C) Segment classification — clasificar en 4 tipos: `baseline_data` (descripción honesta), `properline_data` (lo que "se supone" decir), `interpreted_data` (forzar opinión), `vague_data` (ocultar info). (D) Main concern — "prime mover" del participante. Usa batching con `batchSize: 1`. |
| 9 | `Structured Output Parser1` | outputParserStructured | Schema: `study_question` (string), `data_type` (enum de 4 valores), `main_concern` (string). |
| 10 | `Mem CP` | code (Python) | **Memory Checkpoint:** Hace merge de los datos base (de Hacedor de texto) con los resultados del AI Agent1. Para cada segmento: añade `study_question`, `data_type`, `main_concern` del output del agente. Luego serializa a JSON, codifica base64, y empaqueta con `binary.data` para escritura. |
| 11 | `Mem LP` | code (Python) | **Memory Loop:** Toma todos los items procesados, los combina en un solo diccionario `{index: {first_wave: item}}`, serializa a JSON, codifica base64, y empaqueta con `binary.data` → filename: `combined_output.json`. |
| 12 | `Read/Write Files from Disk` | readWriteFile | Escribe el output combinado a `/tmp/{Title}_1` (sobrescribe, `append: false`). Este archivo será leído en la siguiente iteración por `Read/Write Files from Disk1`. |
| 13 | `When chat message received` | chatTrigger | Trigger alternativo (chat). **disabled: true** — no se usa. |
| 14 | `Extract from File` | extractFromFile | Extracción de PDF (operation: `pdf`, `joinPages: true`). **No conectado al flujo principal** (conectado solo al chat trigger disabled). |
| 15 | `DeepSeek Chat Model` | lmChatDeepSeek | Modelo compartido. Conectado a: AI Agent1 (índices 0 y 1), Segmenter (0), Structured Output Parser (0), Structured Output Parser1 (0). |

### Flujo de conexiones
```
When Executed by Another Workflow → Code in Python (Beta) → Read/Write Files from Disk1 → If
  If[true] → Segmenter-UnstInterviews (+ DeepSeek + Structured Output Parser)
    → Hacedor de texto → AI Agent1 (+ DeepSeek + Structured Output Parser1)
      → Mem CP → Mem LP → Read/Write Files from Disk  ← (ciclo de realimentación)
```

### Overlaps
- Es **llamado por** `Open Coder - CCA.json` vía el nodo `Call 'Open Coder - Document'`.
- El output `combined_output.json` en `/tmp/{Title}_1` es leído por el CCA como "síntesis previa" de cada documento.
- `Hacedor de texto` reconstruye el texto real de cada segmento → esto alimenta al AI Agent1 con texto concreto, no solo metadatos.
- El ciclo Mem CP → Mem LP → Write → Read crea una **ventana de contexto rodante**: cada ejecución guarda el resultado para que la siguiente iteración tenga acceso al estado previo.

---

## 3. `Open Coder - CCA.json`
### Fase 3 — Clusterizador Informado Cross-Document + Fase 4 parcial
**Propósito:** Es el workflow más complejo (~75 nodos, ~2900 líneas). Orquesta la codificación iterativa de múltiples documentos, clustering cross-document, ciclo de memo (proponedor + testeador), resegmentación, inserción en Supabase, agrupación de constructos, consolidación de hipótesis, derivación de variables, y prueba de relaciones.

### Nodos principales (agrupados por función)

#### A. Orquestación e iteración
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Orchestrator` | code (Python) | **Orquestador principal.** Itera sobre segmentos con cursor. Maneja ventana de contexto (últimos 3 ítems). Output: `role: "mixed_batch"`, `fileName`, `target_content`, `context_list`, `next_cursor`. Chequeo de terminación: `if cursor >= total_work → {stop: true}`. |
| `Call 'Open Coder - Document'` | executeWorkflow | **Llama al workflow `Open Coder - Document`** por cada documento, pasando el texto y metadata. |
| `Aggregate` | aggregate | Agrega resultados de múltiples llamadas. |
| `Merge` / `Merge1-6` | merge | 7 nodos merge uniendo ramas (chooseBranch, 4 inputs, etc.). |
| `Loop Over Items1` | splitInBatches | Itera sobre items en lotes. |
| `If` / `If1` / `If2` / `If3` / `If4` / `If6` | if | 6 condicionales bifurcando flujo según condiciones (ej. `$input.all().length > 1`, `$json.fileSize > 0`, `$json.exists()`). |
| `Switch` | switch | Enruta a distintas ramas según largo del array. |

#### B. Memoria y contexto
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Simple Memory` | memoryBufferWindow | Ventana de memoria para el agente proponedor (contexto de conversación). |
| `Simple Memory1` | memoryBufferWindow | Ventana de memoria para el agente testeador. |
| `Resume contexto` | agent (langchain) | Sintetiza el contexto previo acumulado para inyectarlo en la nueva iteración como resumen. |

#### C. Proponedor y Testeador de Memos (§3.4 Ciclo cada 3 docs)
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Proponedor de Memos` | agent (langchain) | **A05.** Genera memos de hipótesis y propiedades desde los patrones acumulados. |
| `Testeador de memos` | agent (langchain) | **A06.** Evalúa cada memo como SAT (saturado) / MOD (modificado) / FORCED (sin fundamento). |
| `Code in Python (Beta)3` | code | Orquestador del ciclo: prepara los datos para el proponedor y testeador, maneja la lógica de cada 3 documentos. |

#### D. Clusterizado y Segmentación
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Clusterizador (doc) informado` | agent (langchain) | **A04.** Clustering de códigos abiertos entre documentos → sistema unificado. |
| `Resegmentar - Doc` | agent (langchain) | **A02.** Reagrupa segmentos por lógica de comportamiento. Conectado a: DeepSeek Chat Model2 + Structured Output Parser3. |
| `Junta segmentos` | agent (langchain) | Une segmentos relacionados semánticamente después de la resegmentación. |

#### E. Agrupación y Refinamiento (Fase 4)
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Agrupador` | agent (langchain) | **A07.** Agrupa constructos por superposición de indicadores (interchangeability of indicators, Glaser). Recibe definiciones y variaciones, busca patrones latentes que las resumen en higher-order constructs. |
| `Clusterizador informado` | (similar al anterior) | Segundo punto de clustering con criterios adicionales. |
| `AI Agent2` | agent (langchain) | **A09 — AI Agent2 (doc coding).** Recodifica documentos contra el esquema refinado. |
| `AI Agent3` | agent (langchain) | Agente de soporte para prueba de relaciones. |
| `AI Agent4` | agent (langchain) | **A11 — Insight grouping.** Agrupa insights recurrentes de memos. |
| `AI Agent5` | agent (langchain) | Agente adicional de análisis. |
| `AI Agent6` | agent (langchain) | **A12 — Thematic clusters.** Organiza Memo_Bank en clústeres temáticos. |
| `AI Agent7` | agent (langchain) | **A13 — Hypothesis testing.** Prueba hipótesis contra todos los documentos. |

#### F. Base de datos y almacenamiento
| Nodo | Tipo | Lógica |
|------|------|--------|
| `SEGMENTOS` | supabase | Lee segmentos de Supabase. |
| `Get many rows` / `1-4` | supabase | 5 nodos de lectura de distintas tablas. |
| `Create a row` / `1` | supabase | Inserciones en Supabase. |
| `Update a row` / `2` / `3` | supabase | Actualizaciones con filtros por `id`, `keyName`, etc. |
| `Insertar-segmentos` | supabase | Inserta segmentos procesados en tabla `segments`. |
| `Insertar-categorias` / `1` | supabase | Inserta categorías en `research_categories`. |
| `Supabase Vector Store1` | vectorStoreSupabase | Almacén vectorial para búsqueda semántica (RAG). Modo `load` con query `match_memos_docs`, filtro por metadata `read: false`. |
| `Execute a SQL query` | postgres | Consulta SQL directa a Postgres. |

#### G. Embeddings, RAG, y modelos
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Embeddings HuggingFace Inference` | embeddingsHuggingFace | Modelo `sentence-transformers/all-mpnet-base-v2`. |
| `Embeddings HuggingFace Inference1` | embeddingsHuggingFace | Segundo nodo de embeddings. |
| `Default Data Loader` / `1` / `2` | documentDefaultDataLoader | 3 cargadores de documentos para RAG. |
| `DeepSeek Chat Model` / `1-5` | lmChatDeepSeek | 5 modelos DeepSeek compartidos entre distintos agentes. |
| `DeepSeek Chat Model2` | lmChatDeepSeek | Modelo dedicado para `Resegmentar - Doc`. |
| `HuggingFace Chat Model` | lmChatHuggingFace | Modelo alternativo HuggingFace (en adición a DeepSeek). |

#### H. Utilidades
| Nodo | Tipo | Lógica |
|------|------|--------|
| `Sticky Note` / `1` / `2` | stickyNote | Notas: "6 categorías con variaciones", conteos de constructos. |
| `FILTRO` | readWriteFile | Filtro de archivos por patrón. |
| `Listar archivos1` | readWriteFile | Lista archivos del disco. |
| `Listar sintesis` | readWriteFile | Lee archivos de síntesis previas. |
| `Listar segmentos` / `1` | readWriteFile | Lista segmentos. |
| `Read/Write Files from Disk` / `1-5` | readWriteFile | 6 nodos de lectura/escritura. |
| `Extract from File` / `1` | extractFromFile | 2 nodos de extracción. |
| `Data para Supabase` | code | Prepara datos para inserción. |
| `Code in Python (Beta)` / `2-25` | code | ~25 nodos code para transformaciones, merge de datos, formateo, etc. |
| `Webhook` | webhook | Endpoint HTTP para triggers externos. |
| `When clicking 'Execute workflow'` | manualTrigger | Disparador manual alternativo. |

### Overlaps con otros workflows
- **Contiene el equivalente completo de `My workflow 2.json`** (clusterizado + memo + agrupador + criteria + variables), pero implementado de forma diferente (más nodos, más granular).
- **Solapa con `My workflow 4.json`** en la parte de consolidación de hipótesis y derivación de variables (AI Agent4/5/6/7 ≈ A08/A11/A12/A13).
- **Solapa con `Selective Coder.json`** pero de forma menos directa; el CCA es Fase 3-4 temprana, mientras que Selective Coder es Fase 4d-5b.
- **Contiene agentes que el proceso asigna a Fase 4** dentro de un workflow mayormente de Fase 3, lo que sugiere que este workflow fue creciendo orgánicamente.

---

## 4. `My workflow 2.json`
### Fase 3-4 — Ciclo de Memo cada 3 documentos + Agrupación + Derivación de Variables
**Propósito:** Tomar documentos y categorías existentes, agrupar documentos en lotes de 3, generar nuevas categorías con definiciones, variaciones, hipótesis, y criterios de muestreo, luego agrupar constructos y derivar variables para metadata de documentos.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `When clicking 'Execute workflow'` | manualTrigger | Disparador manual. Dispara A, B, C en paralelo. |
| 2 | `Webhook` | webhook | Disparador alternativo vía HTTP. |
| 3 | `A` | supabase | Lee tabla `segments_clusters` (todas las filas). |
| 4 | `B` | supabase | Lee tabla `documents` (todas las filas). |
| 5 | `C` | supabase | Lee tabla `segments` (todas las filas). |
| 6 | `Merge` | merge | Une A[0], B[1], C[2] → un solo stream. |
| 7 | `Get many rows` | supabase | Lee `research_categories` (filtro: todas). |
| 8 | `If` | if | `$input.all().length > 1` → true: va a `Code in Python (Beta)` (ruta de agrupación); false: va a `Orchestrator1` (ruta de clusterizado). |
| 9 | `Orchestrator1` | code (Python) | **Batch de 3 documentos.** Itera `range(0, len(documents), 3)`. Para cada batch: construye texto con `Document: {doc_name}`, y para cada categoría que referencia ese doc: `{index}. {label}: {indicators}`. Añade `Theoretical questions: {notes}`. Output: `{content: batch_text}`. |
| 10 | `DeepSeek Chat Model1` | lmChatDeepSeek | Modelo `deepseek-reasoner` con `maxRetries: 5`. |
| 11 | `DeepSeek Chat Model` | lmChatDeepSeek | Segundo modelo (sin maxRetries especial). |
| 12 | `Clusterizador informado` | agent (langchain) | **A04.** Prompt de 6 pasos: (1) Analyze for Human Purpose — agrupar por intención conductual subyacente, (2) Labeling — nombrar con gerundio, (3) Definition, Variation & Evidence Mapping — mapear cada variación a document_id + contributing_codes específicos, (4) Hypothesis Generation — transformar preguntas teóricas en hipótesis testeables, (5) Theoretical Sampling Design — inclusion/exclusion criteria, (6) Completeness Check — verificar que ningún dato quede huérfano. |
| 13 | `Structured Output Parser4` | outputParserStructured | Schema: `new_categories[]` con `category` (gerund phrase), `memo` (definition + variations con evidence_map), `theoretical_hypotheses[]`, `strategic_sampling_criteria` (inclusion + exclusion). |
| 14 | `Code in Python (Beta)2` | code | **Transformación de output del clusterizador:** aplana `new_categories[]` extrayendo `category`, `definition`, `variations`, `hypotheses`, `sampling_criteria_inc`, `sampling_criteria_exc` y añadiendo un `try` (índice). |
| 15 | `Create a row` | supabase | Inserta en `research_categories` con 7 campos: `try`, `category`, `definition`, `hypotheses`, `sampling_criteria_inc`, `sampling_criteria_exc`, `variations`. |
| 16 | `Code in Python (Beta)` | code | **Prepara datos para agrupador:** Concatena todas las categorías insertadas con formato `{id}. {category}: {definition}\nEmpirical indicators:\n -{variations}\nSampling Inclusion criteria:\n -{inc}\nSampling Exclusion criteria:\n -{exc}`. |
| 17 | `Agrupador` | agent (langchain) | **A07.** Prompt: "You are a specialist in Barney Glaser's constant comparative method." Recibe todas las definiciones de constructos. Usa interchangeability of indicators para agruparlos en higher-order constructs. Por cada nuevo constructo: `label` (gerund-based), `definition`, `summarized_ids` (ids de los constructos agrupados), `theoretical_sampling_criteria` (inclusion + exclusion unificados). |
| 18 | `Structured Output Parser2` | outputParserStructured | Schema: `summarized_constructs[]` con `label`, `definition`, `summarized_ids[]`, `theoretical_sampling_criteria`. |
| 19 | `Memos` | code (Python) | **Genera texto de memos por grupo:** Para cada summarized_construct, busca sus hipótesis originales (vía `cats_map[id].hypotheses`) y las concatena. Output: `{content: "Category {index}: {definition}\nLinked hypotheses:\n- ...", problem: "How do journalists and the news media keep professional relevance during the boom of AI?"}`. |
| 20 | `Criteria` | code (Python) | **Genera texto de criterios por grupo:** Para cada summarized_construct, extrae `inclusion` y `exclusion criteria`. Output: `{content: "Group {index}: {definition}\nInclusion criteria:\n- ...\nExclusion criteria:\n- ...", problem: ...}`. |
| 21 | `AI Agent` | agent (langchain) | **Derivador de Variables (Metadata Dictionary).** Prompt: "You are an expert Qualitative Researcher specializing in metadata schema design." Recibe los criterios de inclusion/exclusion y el main concern. Tarea: (1) identificar variables implícitas, (2) agrupar criterios relacionados, (3) definir categorías mutuamente excluyentes (binarizar/trinarizar), (4) output JSON con `variable_code`, `description`, `categories[]`. |
| 22 | `Structured Output Parser3` | outputParserStructured | Schema: `variables[]` con `variable_code` (SCREAMING_SNAKE_CASE), `definition`, `source_group_id`, `measurement_level` (Nominal/Binary), `categories[]` con `value_code`, `label`, `criteria_summary`. |
| 23 | `AI Agent1` | agent (langchain) | **Consolidador de Hipótesis.** Prompt: "Regroup and summarize all the hypotheses, erasing redundancies and the most untestable." Añade negative hypotheses para testeo. Output: `consolidated_hypotheses[]` con `id`, `hypothesis_type` (Descriptive/Correlational/Causal/Explanatory/Predictive), `statement`, `source_category_indexes[]`. |
| 24 | `Structured Output Parser5` | outputParserStructured | Schema de hipótesis consolidadas. |
| 25 | `Variables` | agent (langchain) | **Generador de JSON Schema desde variables.** Prompt: "Please make a JSON schema from this so I can use an AI agent to code my cases." Convierte las variables definidas a un schema JSON con string enums. |
| 26 | `Read/Write Files from Disk1` | readWriteFile | Escribe variables a `/tmp/vars/*`. |
| 27 | `Extract from File` | extractFromFile | Lee archivos de variables (CSV con delimiter `;`, encoding `latin1`). |
| 28 | `Merge1` | merge | Une rama de variables (índice 1) con rama de metadata (índice 0). |
| 29 | `Metadata 1` | code (Python) | **Segmenter + Merger de metadata:** Toma documentos (B), segmentos (C), y metadata externa. Para cada documento: asigna `Metadata` (del mapa externo) y `Segments` (acumulados por doc_name detectando cambios de segment_number). |
| 30 | `AI Agent2` | agent (langchain) | **Clasificador de documentos.** Prompt: "I need you to classify this document using the following variables and categories, making a metadata json table." Recibe `Document metadata`, `Interview segments`, y el `codebook` de variables. |
| 31 | `Structured Output Parser6` | outputParserStructured | Schema dinámico: `={{ $('Variables').first().json.output }}`. |
| 32 | `Code in Python (Beta)7` | code | **Merge final de datos:** Une metadatos clasificados con docs originales (B), construye `{doc_name, Notes, comparison_groups, other_data}`. |
| 33 | `Update a row` | supabase | Actualiza tabla `documents` donde `doc_name` coincide, con `dataToSend: autoMapInputData`. |

### Flujo de conexiones principal
```
When clicking / Webhook → A + B + C (paralelo) → Merge → Get many rows → If
  If[false] → Orchestrator1 → Clusterizador informado (+ DeepSeek1 + Parser4) → Code2 → Create a row
    → Code → Agrupador (+ DeepSeek1 + Parser2)
      ├─→ Memos → AI Agent1 (+ DeepSeek1 + Parser5)  [hipótesis consolidadas]
      ├─→ Criteria → AI Agent (+ DeepSeek1 + Parser3) → Variables
      │     └─→ Read/Write Files1 → Extract from File → Merge1
      └─→ Code5
  Merge1 → Metadata1 → AI Agent2 (+ DeepSeek1 + Parser6) → Code7 → Update a row
```

### Overlaps
- **`Orchestrator1`** implementa el ciclo de "cada 3 documentos" del proceso (§3.4) pero a nivel de batch text, no con agentes separados proponedor/testeador (eso está en CCA).
- **`Agrupador` + `Criteria` + `Memos` + `AI Agent`** implementan la secuencia de Fase 4b (reorganización externa) de forma más acotada que en CCA.
- **`AI Agent2`** clasifica documentos con el codebook de variables → equivalente a la recodificación de Fase 4b.4.
- El `problem` hardcodeado ("How do journalists and the news media keep professional relevance during the boom of AI?") revela el dominio de estudio: periodismo + IA.

---

## 5. `My workflow 4.json`
### Fase 4 — Consolidación de Hipótesis, Memos, y Prueba de Relaciones
**Propósito:** Leer memos, documentos, categorías y variables; consolidar hipótesis desde notas de entrevistas; insertar en vector store; muestrear documentos por variable para comparación entre grupos; probar diferencias significativas entre grupos.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `Memos` | supabase | Lee `consolidated_hypotheses`. |
| 2 | `Docs` | supabase | Lee `documents` (todas). |
| 3 | `Cats` | supabase | Lee `summarized_constructs`. |
| 4 | `Vars` | supabase | Lee `variable_definitions`. |
| 5 | `Merge` | merge | Une los 4 inputs (mode: chooseBranch, usa input 3). |
| 6 | `Code in Python (Beta)4` | code | **Extrae notas por documento:** Itera `Docs`, extrae `doc_name` y `metadata.Notes`. |
| 7 | `AI Agent1` | agent (langchain) | **Consolidador de insights teóricos.** Prompt: "Identify specific statements regarding category relationships inside each. Classify them by topic or relationship similarity. Summarize them in comprehensive bold testable statements." Output: `structured_analysis[]` con `bold_testable_statement` + `metadata: {doc, topic_cluster, constituent_insights[]}`. |
| 8 | `Structured Output Parser1` | outputParserStructured | Schema de `structured_analysis`. |
| 9 | `Code in Python (Beta)5` | code | **Aplana statements:** Itera `structured_analysis[]`, asigna índice incremental, `read: "false"`. Output: `[{content, metadata}]`. |
| 10 | `Embeddings HuggingFace Inference1` | embeddingsHuggingFace | `sentence-transformers/all-mpnet-base-v2`. |
| 11 | `Default Data Loader1` | documentDefaultDataLoader | Carga documentos con metadata: `index`, `topic_cluster`, `constituent_insights`. |
| 12 | `Insertar-categorias` | vectorStoreSupabase | Inserta en vector store `memos_docs` (modo `insert`). |
| 13 | `Get many rows` | supabase | Lee `memos_docs` (todas). |
| 14 | `If1` | if | Filtra filas que tienen campo `id`. |
| 15 | `Code in Python (Beta)7` | code | **Reset de estado:** Pone `metadata.read = "false"`, `metadata.cluster = 0` para todos. |
| 16 | `Code in Python (Beta)1` | code | **Muestreador por variable.** Agrupa documentos por `variable → category_value → [doc_names]`. Hace downsample aleatorio a máximo 5 docs por grupo (`random.sample(doc_list, 5)`). |
| 17 | `Code in Python (Beta)` | code | **Construye evidence_map:** Cruza `Docs.metadata.cats[]` con `Cats[].label`. Para cada categoría: `{name, desc, evid: {doc_name: "empirical_summary + definition_impact"}}`. |
| 18 | `Merge1` | merge | Une evidence_map con la estructura de variables (chooseBranch). |
| 19 | `Code in Python (Beta)2` | code | **Explota variables × documentos:** Para cada categoría y cada variable, itera las categorías de la variable (`cats.items()`), busca los docs que matchean en `evidence_map`, y construye `{name, desc, sampling: {variable_name: {category: [matched_docs]}}}`. |
| 20 | `AI Agent` | agent (langchain) | **Comparador de grupos.** Prompt: "I am comparing social groups. I have some field notes from 5 interviews per group. I need you to tell me if there is a significant and obvious difference between these interviewees." Output: `{has_significant_difference: bool, rationale: string}`. |
| 21 | `Structured Output Parser` | outputParserStructured | Schema: `has_significant_difference` + `rationale`. |
| 22 | `Merge2` | merge | Une ramas (chooseBranch). |
| 23 | `Supabase Vector Store1` | vectorStoreSupabase | Búsqueda semántica: modo `load`, tabla `memos_docs`, query `match_memos_docs`, filtra por metadata `read: "false"`. |
| 24 | `Switch` | switch | Si `$input.all()` tiene longitud > 1 → continúa; else → fallback. |
| 25 | `Code in Python (Beta)3` | code | **Junta memos originales + nuevos:** Toma statements de `Memos` y los combina con los del input actual, eliminando duplicados por `metadata.cluster`. |

### Flujo principal
```
Memos + Docs + Cats + Vars → Merge
  ├─→ Code4 → AI Agent1 (+ Parser1) → Code5 → Data Loader1 (+ Embeddings) → Insertar-categorias (vector store)
  └─→ Code1 (sampler) + Code (evidence) → Merge1 → Code2 (explode) → AI Agent (+ Parser)
        → Merge2
Get many rows (memos_docs) → If1 → Code7 (reset) → Merge2
Merge2 → Supabase Vector Store1 → Switch → Code3
```

### Overlaps
- La consolidación de hipótesis (`AI Agent1`) es equivalente a **A08 (AI Agent1 hipótesis)** del roster.
- La comparación de grupos (`AI Agent`) es una implementación de prueba de relaciones **§4b.4** pero simplificada (solo `has_significant_difference` bool).
- El vector store `memos_docs` y la búsqueda semántica implementan parcialmente el RAG de memos.

---

## 6. `My workflow 5.json`
### Fase 4a — Pruebas de Saturación: Cats vs Incidentes/Props/Cats
**Propósito:** Ejecutar tres agentes en paralelo para probar la saturación de categorías desde tres ángulos.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `When clicking 'Execute workflow'` | manualTrigger | Disparador manual |
| 2 | `Read/Write Files from Disk` | readWriteFile | Lee archivos de entrada |
| 3 | `Extract from File` | extractFromFile | Extrae texto (v1.1) |
| 4 | `Cats vs incidentes` | agent (langchain) | **Agente 1.** Sin prompt definido en el JSON (parameters.options: {}). Probablemente usa un prompt del sistema por defecto o el texto extraído. Compara cada categoría contra sus incidentes. Evalúa intercambiabilidad (§4a.1). |
| 5 | `Cats vs props` | agent (langchain) | **Agente 2.** Similar. Compara categorías contra sus propiedades documentadas. ¿Las propiedades cubren todas las variaciones observadas? |
| 6 | `Cats vs cats` | agent (langchain) | **Agente 3.** Similar. Compara categorías entre sí. Detecta solapamientos, posibles fusiones (§4b.2: >80% ejemplos compartidos). |
| 7-10 | `Teen Persona`, `Life Coach`, `DeepSeek Model`, `Unified Memory` | varios | **Nodos experimentales disableados.** Son de un experimento de chat simulado coach/estudiante. No son parte del flujo analítico. |

### Conexiones
```
When clicking → Read/Write → Extract from File
  ├─[paralelo]→ Cats vs incidentes
  ├─[paralelo]→ Cats vs props
  └─[paralelo]→ Cats vs cats
```

### Overlaps
- **`Cats vs incidentes`** implementa §4a.1 (comparar esencia central, intercambiabilidad de incidentes).
- **`Cats vs cats`** implementa §4b.1-4b.2 (detección de solapamientos entre categorías, condición de fusión).
- Los prompts están **vacíos** en el JSON (posiblemente se configuran en runtime o están incompletos).

---

## 7. `Recategorización.json`
### Fase 4/5 — Recategorización de Constructos
**Propósito:** Leer `research_categories`, agrupar variaciones por constructo, y actualizar `summarized_constructs` en Supabase.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `Get many rows` | supabase | Lee `research_categories` (todas). |
| 2 | `Code in Python (Beta)` | code | **Agrupador de variaciones por constructo.** Itera items, agrupa por `construct_id`. Para cada variación: extrae `variation_description` + `evidence_map` (document_ids). Formatea: `"{desc} ({evidence_str})"`. Output: `[{id: construct, evidences: [texto, ...]}]`. |
| 3 | `Execute a SQL query` | postgres | `ALTER TABLE summarized_constructs ADD COLUMN IF NOT EXISTS evidences TEXT[]` — asegura que la columna existe. |
| 4 | `Sticky Note` | stickyNote | "8 Constructos con sus variaciones." |
| 5 | `AI Agent` | agent (langchain) | **Analista de constructos latentes.** Prompt detallado: "Act like a specialist in qualitative research. Remember essential concepts of latent construct analysis, factor analysis and the interchangeability of indicators (Glaser)." Recibe: `label`, `definition`, `evidences`, `variables_with_output`. Decide entre: **ENRICH** (añadir propiedades), **SUBDIVIDE** (subconstructos/tipologías/gradientes), **DIVIDE** (separar patrones distintos). |
| 6 | `Structured Output Parser` | outputParserStructured | Schema para la decisión del AI Agent. |
| 7 | `Update a row` | supabase | Actualiza `summarized_constructs` donde `id` coincide, seteando `evidences`. |

### Conexiones
```
Get many rows → Code → [rama Update a row] + [rama AI Agent → Parser → más updates]
```

### Overlaps
- **Misma lógica que el `Agrupador` de My workflow 2** pero con foco en la tríada ENRICH/SUBDIVIDE/DIVIDE (§4a.5-4a.6).
- Actualiza `summarized_constructs` → esta tabla es leída por `My workflow 4.json` como `Cats`.

---

## 8. `Selective Coder.json`
### Fase 4d/5b — Detección de Core Concern + Database A/B
**Propósito:** Transición de open coding a selective coding. Identificar la preocupación central, generar la base de datos plana de nodos (Database A) y las relaciones (Database B).

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `Sticky Note1` | stickyNote | "6 Ideas testeadas con los datos." |
| 2 | `DeepSeek Chat Model` | lmChatDeepSeek | Modelo `deepseek-reasoner`, `responseFormat: text`. **disabled: true**. |
| 3 | `Core Concern Finder` | agent (langchain) | **A19.** Prompt: "You are an expert in Classic Grounded Theory Methodology." Tareas: (a) "which problems recur in codes? what drives the members behavior?", (b) "which codes or mechanisms seem to resolve most of these problems?", (c) "which of these codes connect most to other codes?". Reglas: etiquetar con gerundios, evitar jerga profesional, el main concern debe ser el problema real de los participantes. `executeOnce: true`. |
| 4 | `Structured Output Parser3` | outputParserStructured | Schema Database A: `nodes[]` con `id`, `label`, `entity_type` (open_code/category/core_concern/core_category/core_process), `definition_or_context`, `theoretical_sampling_note`. **disabled: true**. |
| 5 | `Selective Structure` | agent (langchain) | Genera Database A (nodos planos) desde Open Coding Results + Categories + Memos. Prompt detallado: extrae cada código/categoría, asigna entity_type, genera `theoretical_sampling_note`. **disabled: true**. |
| 6 | `Selective Structure1` | agent (langchain) | Genera Database B (edges/relaciones). Prompt: "You may ONLY create relationships between nodes that exist in Database A. Prioritize finding relationships that connect secondary codes back to the core concern." Tipos de relación: 'is a strategy for', 'is a condition of', 'is a consequence of', 'co-occurs with'. **disabled: true**. |
| 7 | `Structured Output Parser4` | outputParserStructured | Schema Database B: `edges[]` con `source_id`, `target_id`, `relationship_type`, `provisional_rationale`. **disabled: true**. |
| 8 | `Read/Write Files from Disk` | readWriteFile | Lee `/tmp/*_1`. `executeOnce: true`. |
| 9 | `Extract from File` | extractFromFile | Extrae datos. |
| 10 | `Get many rows4` | supabase | Lee `documents`. `executeOnce: true`. |
| 11+ | *(más nodos: merge, scoring agents, filters, memo rewriting, etc.)* | varios | Procesamiento de puntuación de relevancia (1-5, threshold ≥4 para selective coding) y muestreo teórico. |

### Overlaps
- **`Core Concern Finder`** = A19 del roster, descrito en §5b.1.
- **Database A/B** = propuesta de estructura para selective coding (§5b).
- Gran parte está **disabled** — es un **work in progress** o sirvió como prototipo.

---

## 9. `category saturator.json`
### Fase 4a/5b — Saturación de Categorías por Incidente
**Propósito:** Para cada par (categoría × documento), extraer incidentes con citas exactas, propiedades propuestas, y elementos paradigmáticos. Luego integrar en el estado paradigmático y verificar saturación.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `Start` | executeWorkflowTrigger | **Trigger externo.** Recibe `cat` (datos de la categoría) y `doc` (datos del documento). |
| 2 | `Category Saturator` | agent (langchain) | **Extractor de incidentes.** Prompt: "You are ONLY looking for incidents that manifest the provided Target Category. Ignore all other themes." Para cada incidente: (1) `exact_quote`, (2) `proposed_property`, (3) `paradigm_element` (dimension/condition/consequence/strategy). Si no aparece la categoría → array vacío. |
| 3 | `Structured Output Parser5` | outputParserStructured | Schema: `extracted_incidents[]` con `cat_id`, `doc_id`, `exact_quote`, `proposed_property`, `paradigm_element`. |
| 4 | `Create a row3` | supabase | Inserta en `extracted_incidents`: `exact_quote`, `interview_id`, `category_id`, `identified_property`, `paradigm_element`. |
| 5 | `DeepSeek Chat Model` / `1` | lmChatDeepSeek | Dos modelos: uno normal, uno `deepseek-reasoner`. |
| 6 | `Code in Python (Beta)` | code | **Aplana incidentes:** Itera `extracted_incidents[]` y los emite como items individuales. |
| 7 | `AI Agent1` | agent (langchain) | **Integrador paradigmático.** Prompt: "You are a Senior Methodologist maintaining a Grounded Theory codebook." Recibe: Current Paradigm State (diccionario de dimensions, conditions, consequences, strategies) + New Incidents. Tarea: (1) chequear si cada incidente mapea a un item existente, (2) si es nuevo ejemplo → no cambiar, (3) si revela variación genuinamente nueva → añadir. Output: `updated_paradigm_state`, `did_state_expand` (bool), `integration_memo`. |
| 8 | `Structured Output Parser` | outputParserStructured | Schema: `updated_paradigm_state` (dimensions[], conditions[], consequences[], strategies[]), `did_state_expand`, `integration_memo`. |
| 9 | `Update a row` | supabase | Actualiza `categories.current_paradigm_state` donde `node_id` coincide. |
| 10 | `Execute a SQL query` | postgres | **Verificador de saturación.** CTE: `LastFiveInterviews` — selecciona los últimos 5 `did_state_expand` para la misma categoría y grupo de metadata. Si COUNT = 5 AND `bool_and(did_state_expand = FALSE)` → `is_group_saturated = TRUE`. |
| 11 | `Return` | set | Devuelve `chatInput`. |
| 12 | `Code in Python (Beta)1` | code | **Calculadora de conteos de hipótesis:** Para cada memo, cuenta cuántos documentos lo confirman positivamente, por contraste, o no lo confirman. |
| 13 | `Memo rewriter` | agent (langchain) | **Reescritor de memos.** Prompt: "Rewrite the theoretical insight. Identify and classify variations, summarizing them into typologies. Identify the core issues or tensions. Identify empirically backed multidimensional causal mechanisms." |
| 14 | `Update a row` (memos_final) | supabase | Actualiza `memos_final` con el memo reescrito. |

### Flujo principal
```
Start → [loop cat×doc] → Category Saturator (+ DeepSeek1 + Parser5)
  → Create a row3 (extracted_incidents)
  → Code (aplanar) → AI Agent1 (+ DeepSeek + Parser)
    → Update a row (categories.paradigm_state)
    → Execute SQL (saturation check)
    → Code1 (conteos) → Memo rewriter → Update (memos_final)
```

### Overlaps
- **`Category Saturator`** implementa el bucle de comparación constante de §5b: buscar indicadores, extraer propiedades, clasificar paradigmáticamente.
- **`AI Agent1`** es el integrador que decide si el estado paradigmático se expande → saturación incremental.
- **`Execute a SQL query`** implementa el **criterio de saturación** de §4a.2/§5b.2: 5 iteraciones sin `did_state_expand` → saturado.

---

## 10. `ur mom.json`
### Fase 5b — TheoSampler (Muestreo Teórico)
**Propósito:** Definir targets de metadata para muestreo teórico y ejecutar SQL para encontrar documentos que cumplan los criterios de contraste/extremos/consistentes.

| # | Nodo | Tipo | Lógica real |
|---|------|------|-------------|
| 1 | `When clicking 'Execute workflow'` | manualTrigger | Disparador manual |
| 2 | `Code in Python (Beta)14` | code | **Define 7 targets de metadata** para la categoría "Building Interdisciplinary Teams": (1) `COLLABORATION_STYLE` → "Independent worker", (2) `AI_INTEGRATION_LEVEL` → "Non-user/resister", (3) `Tamaño del medio` → "Pequeño", (4) `ORGANIZATIONAL_PERSPECTIVE` → "Operational implementer", (5) `team_formality_continuum` → "Informal emergent network" + "Highly formalized matrix structure", (6) `interdisciplinary_power_dynamics` → "Journalistic domain dominance" + "Technical domain dominance" + "Balanced power sharing", (7) `resource_allocation_mechanism` → "Centralized strategic budget" + "Decentralized project-based" + "Ad-hoc/no dedicated resources". Cada target tiene su `justification` teórica. Output: `[{cat, key, vals, jus}, ...]`. |
| 3 | `Loop Over Items` | splitInBatches | Itera sobre cada target de metadata. |
| 4 | `Execute a SQL query` | postgres | **TheoSampler SQL.** CTE `target_values`: splitea `vals` (comma-separated) en filas individuales. CTE `available_docs`: JOIN con `documents` donde `d."{key}" = tv.val`, con ANTI-JOIN excluyendo docs ya en `categories.saturation_docs[]`. CTE `ranked_docs`: `ROW_NUMBER() OVER (PARTITION BY matched_category ORDER BY RANDOM())`. SELECT final: exactamente 1 documento aleatorio por categoría (`WHERE rn = 1`). |

### Conexiones
```
When clicking → Code14 → Loop Over Items → Execute SQL
```

### Overlaps
- **Implementación directa de §5b.3 TheoSampler (A17).**
- Los 7 targets con sus justificaciones son un ejemplo concreto de **casos de contraste** (ej. "Independent worker" vs. "team structures"), **casos extremos** (ej. "Non-user/resister" de AI), y **casos consistentes**.
- El ANTI-JOIN contra `saturation_docs` evita re-muestrear documentos ya saturados.

---

## 11. `Creador de contenidos.json`
### Estado: Vacío
`{"nodes": [], "connections": {}}`. Template sin contenido. Probablemente era un placeholder para un creador de prompts/configs.

---

## 📊 Mapa de Cobertura: Lo que hay vs. Lo que falta

### ✅ Cubierto (con implementación concreta)

| Fase | Workflow(s) | Agentes del roster |
|------|-------------|-------------------|
| **F1** — Ingesta | `Formateador de entrevistas` | — |
| **F2** — Segmentación | `Open Coder - Document` (Segmenter-UnstInterviews + Hacedor de texto) | Segmentación semántica no supervisada |
| **F3** — Codificación Inicial | `Open Coder - Document` (AI Agent1: explication de texte), `Open Coder - CCA` (Clusterizador, Proponedor, Testeador), `My workflow 2` (Orchestrator1 + Clusterizador informado) | A01 ✓, A02 ✓, A04 ✓, A05 ✓, A06 ✓ |
| **F4a** — Reorganización Interna | `My workflow 5` (Cats vs incidentes/props/cats), `category saturator` (Category Saturator + AI Agent1 integrador) | A16 parcial |
| **F4b** — Reorganización Externa | `My workflow 2` (Agrupador, Memos, Criteria, AI Agent para variables), `My workflow 4` (AI Agent1 consolidación, AI Agent comparación grupos), `Open Coder - CCA` (Agrupador A07, AI Agent4/6/7) | A07 ✓, A08 ✓, A09 ✓, A10 ✓, A11 ✓, A12 ✓, A13 ✓ |
| **F4c** — Deduplicación Memos | Parcial en `Open Coder - CCA` (AI Agent4/6/7) y `My workflow 4` (Code3 junta memos) | Parcial |
| **F4d** — Reformulación PI + Core | `Selective Coder` (Core Concern Finder), `Open Coder - CCA` (Resume contexto) | A14 ✓, A15 parcial, A19 ✓ |
| **F5a** — Interpretación | No hay workflow dedicado. Solo hay gestos implícitos en los prompts de los agentes. | — |
| **F5b** — Codificación Selectiva | `Selective Coder` (Database A/B), `category saturator` (extracción + integración paradigmática), `ur mom` (TheoSampler) | A17 ✓, A20 parcial |
| **F5b** — MemoMaker | `category saturator` (Memo rewriter, Code1 conteos) | A25 parcial |

### ❌ No cubierto (faltante)

| Qué falta | Detalle |
|-----------|---------|
| **Fase 0** completa | No hay workflow de configuración: preguntas de investigación, POOL inicial, selección de ruta, marco teórico RAG. |
| **Fase 1** — Fuentes múltiples | Solo entrevistas TXT. Falta: web scraping, redes sociales, audio/video, grupos focales, imágenes, BIBTEX. |
| **Fase 2** — Análisis léxico/temático | Sin BERTopic, Reinert, detección de metáforas, prime movers automáticos. Solo segmentación semántica. |
| **Fase 3** — Rutas A (Deductiva) y C (Inductiva) | Solo Ruta B (CGT/Abductiva) implementada. |
| **Fase 4b** — Prueba formal H₀/H₁ | No hay protocolo con umbrales de decisión, tabla de resultados, fuerza, consistencia como en §4b.4. |
| **Fase 4d** — Interchangeability_Tester formal | `My workflow 5` (Cats vs incidentes) lo intenta pero sin prompts definidos ni protocolo. |
| **Fase 5a** — Taller interpretativo | Sin gestos de enfoque, cuestionamiento, triangulación, incorporación, ética, análisis de silencios. |
| **Fase 5b** — MemoMaker Generate/Simplify/Correlate | Sin los 4 nodos de análisis paralelo (Patrones, Props, Causas, Consecuencias) → síntesis → tablas de doble entrada → matrices 2×2. |
| **Fase 5c** — Visualización | Sin mapas conceptuales, Sankey, dendrogramas, matrices interactivas, nubes de palabras. |
| **Fase 6a** — Redacción empírica | Sin Natural_Writer (A24). |
| **Fase 6b** — Codificación/redacción teórica | Sin Sorting_Log (A28), Gap_Feeler (A21). |
| **Fase 6c** — Discusión con literatura | Sin Literature_Comparer (A22), sin integración con RAG bibliográfico. |
| **Fase 7** — Evolución | Sin Theory_Evolver (A23). |
| **Transversal** — Manejo de errores | Sin reintentos, circuitos de degradación, resolución de conflictos entre agentes. |
| **Transversal** — Multi-usuario | Sin autenticación, roles, permisos (§0.5). |

---

## 🔗 Orden de ejecución y dependencias entre workflows

```
1. Formateador de entrevistas.json
   └─ produce: TXT formateados → JSON con metadata + segmentos literales
   
2. Open Coder - Document.json  (llamado por CCA)
   └─ produce: segmentos semánticos + codificación inicial por documento
   
3. Open Coder - CCA.json  (llama a Open Coder - Document)
   └─ produce: categorías iniciales unificadas, memos, clusters cross-document
   └─ inserta en Supabase: segments, research_categories
   
4. My workflow 2.json  (independiente o post-CCA)
   └─ lee: documents, segments_clusters, research_categories
   └─ produce: nuevas categorías, constructos agrupados, variables, metadata de docs
   └─ inserta en: research_categories, documents (metadata)
   
5. My workflow 5.json  (independiente)
   └─ prueba: saturación de categorías (cats vs incidentes/props/cats)
   
6. Recategorización.json  (independiente)
   └─ lee: research_categories → agrupa → actualiza summarized_constructs
   
7. My workflow 4.json  (independiente)
   └─ lee: consolidated_hypotheses, documents, summarized_constructs, variable_definitions
   └─ produce: hipótesis consolidadas, comparaciones entre grupos
   └─ usa vector store: memos_docs
   
8. Selective Coder.json  (depende de outputs de CCA y WF2)
   └─ lee: open coding results, categories, memos
   └─ produce: core concern, Database A (nodos), Database B (edges)
   
9. category saturator.json  (llamado externamente, por doc×cat)
   └─ produce: extracted_incidents, paradigm_state actualizado, saturation check
   └─ actualiza: categories, memos_final
   
10. ur mom.json  (independiente)
    └─ produce: muestreo teórico (documentos seleccionados por metadata)
```

### Nota sobre solapamientos (overlaps) críticos:
- **`Open Coder - CCA` y `My workflow 2`** implementan lógica similar (clusterizado + memo + agrupación) pero con enfoques distintos. CCA es más granular e iterativo; WF2 es más lineal y orientado a batches de 3 documentos.
- **`My workflow 4` y `Open Coder - CCA`** comparten la consolidación de hipótesis (A08/A11/A12/A13 están duplicados conceptualmente).
- **`My workflow 5` y `category saturator`** ambos trabajan saturación pero a distintos niveles: WF5 compara entre categorías, category saturator extrae incidentes dentro de una categoría.
- El `problem` hardcodeado en WF2 ("How do journalists and the news media keep professional relevance during the boom of AI?") debería ser dinámico desde el POOL de variables o la configuración de Fase 0.
