# Análisis

# 1. Principios de Diseño y Decisiones Arquitectónicas

## A — Orientación, Plantillas y el Lienzo del Plan de Análisis

El modelo de orientación no invasiva más potente es aquel que hace visible la *metodología como una estructura navegable*, sin interrumpir al investigador con ventanas emergentes. Se implementan cuatro capas interconectadas.

**Capa 1 — El Lienzo del Plan de Análisis (estilo KNIME).**&#x55;n espacio de trabajo visual basado en nodos acompaña a cada proyecto. Cada nodo representa una fase, una puerta de decisión, una fuente de datos o un artefacto de salida. Los bordes transportan datos tipados (corpus → segmentos → categorías → memorandos → informe). El lienzo es tanto una *herramienta de planificación* (arrastrar y soltar nodos antes de que lleguen los datos) como un *tablero de estado en vivo* (los nodos pulsan, se llenan o señalan según avanza el flujo). Es generativo: el investigador *diseña* su flujo de trabajo visualmente, y el Orquestador de Fases *lee* el lienzo como su especificación de ejecución. Sin lienzo no hay ejecución. Esto hace que la metodología sea legible sin necesidad de documentación separada.

**Capa 2 — Biblioteca de Plantillas Metodológicas.**&#x4C;as plantillas son instantáneas preconfiguradas del lienzo, almacenadas como descriptores JSON versionados. Cada plantilla incluye: la topología de nodos correcta, los rosters de agentes predefinidos, umbrales por defecto, texto de `TarjetaPrimariaDeFase` incrustado y referencias bibliográficas seleccionadas. Plantillas soportadas en el lanzamiento: GT Glaseriana Clásica, GT Constructivista (Charmaz), Análisis Situacional (Clarke), Análisis del Discurso Foucaultiano, Análisis Crítico del Discurso (Fairclough/van Dijk), Análisis Retórico del Discurso, IPA, Análisis Narrativo (Riessman) y un andamio de Métodos Mixtos con predominio cualitativo. Las plantillas son módulos cargables; la comunidad puede contribuir con nuevas sin necesidad de redesplegar.

**Capa 3 — Superposiciones de Orientación Contextual.**&#x43;ada `NodoDelLienzo`, `Categoría`, `Memo` y gesto tiene asociado un `TooltipDeOrientación` (texto de 2 a 3 frases al pasar el ratón) y un `Tutorial` completo (panel expandible: qué, por qué, cuándo desviarse, errores comunes, ejemplo). Estos se redactan en un CMS headless y se cargan de forma diferida — nunca bloquean la interfaz. Una `TarjetaPrimariaDeFase` aparece exactamente una vez antes de cada transición de fase (se puede descartar, no se repite a menos que el investigador lo solicite a través de la insignia "?" del nodo del lienzo). Esto permite que los usuarios experimentados trabajen sin obstáculos y que los novatos reciban contexto inmediato.

**Capa 4 — Asistente de Investigación con IA.**&#x55;n agente lateral colapsable — no es un chatbot, no es un modal — que tiene conocimiento permanente del contexto: conoce la fase actual, la ruta de codificación activa, el estado del sistema de categorías y los últimos diez memorandos. El investigador lo invoca deliberadamente. Responde preguntas como "¿por qué mi saturación no avanza?", "¿qué comprueba exactamente el Probador de Intercambiabilidad?" o "muéstrame un ejemplo de una categoría nombrada con gerundio". Puede abrir tutoriales, resaltar nodos relevantes del lienzo y proponer borradores de memorandos, pero nunca actúa de forma autónoma. Su `SesiónDelAsistenteDeInvestigación` registra todas las interacciones como evidencia de reflexividad metodológica.

## B — Decisiones de Optimización

Se abordan seis ineficiencias estructurales de la arquitectura v3.

**B1 — Duplicación de incrustaciones (embeddings).**&#x42;ERTopic y el Índice Vectorial RAG calculan incrustaciones de oraciones sobre el mismo corpus desde flujos separados. Un `CachéDeIncrustacionesCompartidas` calcula las incrustaciones una sola vez (fastText o SentenceTransformers), almacena vectores versionados y sirve a ambos consumidores. Reducción estimada del 40–60% en el tiempo de cómputo de NLP.

**B2 — Hinchazón del contexto de los agentes.**&#x43;ada llamada a un agente recarga todo el contexto del proyecto. Un `ConstructorDeContextoDeAgente` ensambla la *porción mínima necesaria*: el resumen de la ventana actual del `AdministradorDeVentanaDeContextoRodante` + las definiciones de categorías relevantes + la declaración de la `PreocupaciónPrincipal` activa + la instrucción específica de la fase. Esto reduce el costo por llamada de tokens en un 50–70% estimado para agentes en mitad del flujo.

**B3 — Derroche de niveles de modelo.**&#x45;jecutar modelos de clase GPT-4 en tareas de reformateo deterministas (reasignación masiva del `A09 AgenteReCodificador`, aplicación de esquemas JSON, indexación estructural) es caro y lento. Un `EnrutadorDeModelos` clasifica las tareas en tres niveles — RÁPIDO\_ECONÓMICO (modelo pequeño, < 1 s), EQUILIBRADO (modelo mediano) y RAZONAMIENTO\_POTENTE (modelo de frontera, reservado para `DetectorDeEmergenciaCentral`, `SensorDePreocupaciónPrincipal`, `EscritorNatural`) — y las despacha en consecuencia. Reducción estimada del 60% en costos de API sin pérdida de calidad en tareas deterministas.

**B4 — Vibración (chattering) de bucles de retroalimentación.**&#x45;l `AdministradorDeBuclesDeRetroalimentación` con sus 15 bucles puede dispararse múltiples veces ante un mismo evento. Un `Anti-repeticiónDeBuclesDeRetroalimentación` con períodos de enfriamiento configurables por bucle (30 s por defecto) evita que se reactive en cascada cuando, por ejemplo, una división de categoría activa simultáneamente la nota reflexiva del grupo de variables y el bucle del ciclo de memorandos.

**B5 — Hinchazón del historial de cambios.**&#x41;lmacenar instantáneas de texto completas antes y después de cada división/fusión crea un crecimiento O(n × tamaño\_corpus). Un `MotorDeDiferencias` calcula diferencias estructurales en JSON (formato de parche al estilo git). El registro de `HistorialDeCambios` almacena la diferencia + un resumen legible por humanos; la reconstrucción completa es bajo demanda. Reducción estimada del 80–90% en el almacenamiento del historial de cambios.

**B6 — Cuello de botella secuencial en la trilogía CGT.**`SensorDePreocupaciónPrincipal` → `DetectorDeEmergenciaCentral` → `ProbadorDeIntercambiabilidad` es una cadena puramente secuencial, pero los dos primeros consumen entradas diferentes: el SP lee todos los códigos y memorandos; el DEC lee los resúmenes de categorías y la salida del SP. Se pueden paralelizar parcialmente: tanto el SP como el DEC comienzan su fase de carga de entrada simultáneamente; el paso de razonamiento del DEC solo se dispara después de que el SP complete. Esto reduce el tiempo de ejecución de la trilogía aproximadamente en la duración de la carga de entrada del DEC (15–25% de aceleración dependiendo del tamaño del corpus).

## C — Estrategia de Modularización

Se introducen cinco límites formales de plugins, cada uno respaldado por una interfaz definida. Cualquier componente detrás de un límite de interfaz puede ser intercambiado, extendido o deshabilitado sin tocar la lógica central de orquestación.

**C1 —&#x20;****`IMóduloNLP`****&#x20;(Interfaz de Plugin de NLP).**&#x54;odos los analizadores NLP implementan: `ejecutar(corpus, config): ResultadoVersionado`, `puedeEjecutarConRuta(ruta: RutaDeCodificación): booleano`, `entradasRequeridas(): cadena[]`, `nivelDeComplejidadEstimado(): NivelDeModelo`. Los nuevos analizadores (ej., un léxico de sentimientos, un analizador sintáctico, un integrador de normas psicolingüísticas) se registran en el `RegistroDeMódulosNLP` y quedan disponibles en el Lienzo del Plan de Análisis como nodos arrastrables.

**C2 —&#x20;****`IAgente`****&#x20;(Interfaz de Plugin de Agente).**&#x45;xtiende la clase abstracta `Agente` existente con: `etiquetasDeCapacidad(): cadena[]`, `nivelDeModeloPreferido(): NivelDeModelo`, `aceptaContexto(ctx: ContextoDeAgente): booleano`. El `AgenteDelegador` usa estas etiquetas para el enrutamiento dinámico — no hay cableado duro de agentes a fases.

**C3 —&#x20;****`IAdaptadorDeAlmacenamiento`****&#x20;(Patrón de Repositorio).**&#x49;nterfaz abstracta con: `obtener(id)`, `consultar(filtro)`, `insertarOActualizar(entidad)`, `eliminar(id)`, `inserciónMasiva(entidades[])`. Adaptadores concretos: `AdaptadorSupabase`, `AdaptadorPgVector`, `AdaptadorPinecone`, `AdaptadorSistemaDeArchivosLocal`. La capa de aplicación nunca importa un controlador de almacenamiento directamente.

**C4 —&#x20;****`IRenderizadorDeVisualización`****&#x20;(Plugin de Visualización).**&#x43;ada uno de los nueve subtipos concretos de `ArtefactoDeVisualización` implementa: `renderizar(datos, config): CargaÚtilDeArtefacto`, `soporta(tipoDeArtefacto): booleano`, `exportarComo(formato): Buffer`. Los nuevos tipos de visualización (ej., una red bipartita, un mapa de calor geográfico) se registran en el `RegistroDeRenderizadoresDeVisualización`.

**C5 —&#x20;****`IPlantillaMetodológica`****&#x20;(Plugin de Plantilla).**&#x43;ada plantilla implementa: `obtenerTopologíaDelLienzo(): NodoDeLienzo[]`, `obtenerRosterDeAgentesPorDefecto(): ConfiguraciónDeAgente[]`, `obtenerUmbralesPorDefecto(): ConfiguraciónDeUmbral`, `obtenerContenidoDeOrientación(): PaqueteDeOrientación`. Las plantillas se cargan desde un `RegistroDePlantillas` al crear el proyecto y pueden ser contribuidas por la comunidad como paquetes JSON firmados.

***

# 2. Análisis del Sistema (Actualizado)

## Actores, Acciones, Propósitos

El modelo de actores gana tres incorporaciones respecto a v3. El Asistente de Investigación con IA es un nuevo actor semiautónomo — es invocado por el investigador pero se ejecuta como un agente con acceso al estado completo del proyecto, produciendo respuestas de orientación en lugar de resultados analíticos. El Agente Coordinador y el Agente Delegador formalizan el patrón de orquestación CWD **(gestionado ahora nativamente a través de un motor de grafos de estado especializado, descartando automatizadores genéricos como n8n para soportar bucles de razonamiento complejos)**: el Coordinador mantiene la intención estratégica de la fase y evalúa la coherencia entre agentes; el Delegador enruta tareas a agentes trabajadores según etiquetas de capacidad y carga actual. El Agente Crítico es un actor de puerta de calidad que evalúa cada síntesis importante (resúmenes de categorías, declaraciones de preocupación central, secciones escritas) antes de que llegue al investigador, usando un BucleGeneradorCrítico que itera hasta obtener `VeredictoDelCrítico.APROBADO` o hasta que se activa una escalada humana.

El Módulo de Preservación de Anomalías se formaliza como un actor en lugar de solo una bandera — resiste activamente la tendencia del LLM a suavizar hacia la tendencia central señalando, preservando y resaltando las voces divergentes de los encuestados, las categorías minoritarias y las incidencias inesperadas. Esto aborda directamente el riesgo de "homogeneización con molde" identificado en la evaluación cualitativa.

## Descripción Estructural C1/C2 (Actualizada)

A nivel del contexto C1, se introducen dos nuevas relaciones con sistemas externos. El CMS de Contenido de Orientación es un CMS headless externo (ej., Contentful o una instancia autoalojada de Strapi) que sirve textos de tooltips, tutoriales, tarjetas primarias y metadatos de plantillas — mantenido externo para que el contenido de orientación pueda actualizarse sin redesplegar. El Registro Comunitario de Plantillas es un repositorio externo opcional donde se pueden publicar y consumir plantillas metodológicas validadas, gobernado por un paso de verificación de firma antes de cargarlas.

A nivel del contenedor C2, la adición estructural más significativa es la **Capa de Arquitectura de IA (ahora estructurada sobre frameworks optimizados para agentes como LangGraph o NVIDIA AI-Q drb2, reemplazando el orquestador n8n para un manejo más eficiente del contexto y las interrupciones)**, que se sitúa entre el Orquestador de Fases y el Conjunto de Agentes. Contiene el trío CWD (Coordinador, Delegador y su lógica de enrutamiento), el Enrutador de Modelos, el Flujo Generador-Crítico y el Aplicador de Políticas de IA. Ninguna llamada a un agente sale de esta capa sin pasar por el constructor de contexto (minimizando tokens) y el enrutador de modelos (minimizando costos). Los resultados importantes del Conjunto de Agentes que alimentan al investigador o al sistema de redacción pasan por el Crítico antes de mostrarse. El Sistema de Orientación y Plantillas es un nuevo contenedor que se comunica con todos los demás contenedores a través de un flujo de eventos de solo lectura — observa las transiciones de estado y pone a disposición el contenido de orientación sin interceptar ningún flujo de trabajo.

```
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Context.puml

title Nivel C1: Diagrama de Contexto - Sistema CAQDAS Colaborativo

Person(researcher, "Investigador Principal", "Dirige el análisis y gestiona el proyecto")
Person(co_researcher, "Co-Investigadores", "Colaboran en tiempo real en memos y codificación")
Person(ai_assistant, "Asistente de IA", "Actor semiautónomo. Sugiere orientaciones y códigos en el lienzo")

System_Boundary(c1, "Sistema IQAS v5") {
    System(caqdas_platform, "Plataforma CAQDAS", "Orquesta análisis fundamentado, colaboración en tiempo real y agentes IA")
}

System_Ext(cms_guidance, "CMS de Orientación", "Sistema externo (Strapi/Contentful)")
System_Ext(template_registry, "Registro Comunitario", "Repositorio externo de plantillas metodológicas")
System_Ext(llm_apis, "Proveedores LLM", "Motores remotos (DeepSeek, Gemma, GLM, Nemotron)")

Rel(researcher, caqdas_platform, "Define planes, evalúa síntesis", "HTTPS/WSS")
Rel(co_researcher, caqdas_platform, "Edita memos concurrentemente", "WSS")
Rel(ai_assistant, caqdas_platform, "Lee el estado y redacta sugerencias en CRDTs")

Rel(caqdas_platform, cms_guidance, "Solicita contenido didáctico", "API REST")
Rel(caqdas_platform, template_registry, "Descarga plantillas validadas", "API REST")
Rel(caqdas_platform, llm_apis, "Delega razonamiento, evaluación y visión", "API REST")

@enduml
```

![](assets/9yFbDU3Zhmm2VtXmjnafljLsw48RKbpAYYelV92Y4JM=.png)

```
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Container.puml

title Nivel C2: Arquitectura de Contenedores (LangGraph + Colaboración + TEI)

Person(researcher, "Equipo de Investigación", "Interactúa simultáneamente")

System_Boundary(c1, "Entorno Cloud / Local (VPS)") {
    
    Container(ui, "Frontend SPA", "React Native / Rsbuild", "Lienzo interactivo multi-usuario")
    
    Container(api_gateway, "API Principal", "FastAPI", "Gestión de proyectos, Auth y delegación")
    Container(collab_server, "Servidor de Colaboración", "Hocuspocus (Node.js)", "Sincroniza estado del UI vía WebSockets (Yjs)")
    Container(guidance_system, "Sistema de Orientación", "Servicio Python", "Observa eventos y sirve contenido del CMS")

    Container_Boundary(ai_layer, "Capa de Arquitectura de IA (LangGraph / AI-Q)") {
        Container(cwd_trio, "Trío CWD", "Grafos de Estado", "Coordinador y Delegador (Enruta según intención)")
        Container(critic_loop, "Agente Crítico", "Bucle Generador-Crítico", "Puerta de calidad de la Teoría Fundamentada")
        Container(model_router, "Enrutador de Modelos", "Python", "Constructor de contexto y LLM Factory")
    }

    Container_Boundary(agent_pool, "Workers / Agentes Asíncronos") {
        Container(worker_agents, "Agentes Trabajadores", "Celery", "Ejecutan NLP, visión (GLM) y orquestación")
        Container(anomaly_module, "Módulo de Anomalías", "Interceptador", "Preserva voces divergentes")
    }

    ' [NUEVO] Contenedor aislado para Embeddings
    Container(tei_service, "Servidor de Embeddings (TEI)", "Microservicio Docker (Rust/C++)", "Carga los modelos en RAM una sola vez y expone API de inferencia en lote")

    ContainerDb(db_relacional, "PostgreSQL + pgvector", "SQL", "Persistencia CRDT, estado CWD y vectores")
    Container(redis, "Redis", "Broker/PubSub", "Bus de eventos y escalado de Hocuspocus")
    Container(minio, "MinIO", "S3", "Almacenamiento de documentos crudos")
}

System_Ext(cms_external, "CMS y Registro", "Externo")
System_Ext(llm_apis, "Motores de LLM", "APIs (DeepSeek, Gemma, etc.)")

Rel(researcher, ui, "Edita en tiempo real", "HTTPS/WSS")
Rel(ui, collab_server, "Sincroniza teclas/punteros", "WSS")
Rel(ui, api_gateway, "Peticiones estándar", "REST")

Rel(collab_server, redis, "Pub/Sub para multi-instancia")
Rel(collab_server, db_relacional, "Persiste documentos Yjs")

Rel(api_gateway, ai_layer, "Inicia fases metodológicas")
Rel(ai_layer, agent_pool, "Asigna tareas a Celery")

' [ACTUALIZADO] Peticiones de red al nuevo contenedor
Rel(ai_layer, tei_service, "Solicita vectores de contexto rápido", "HTTP REST")
Rel(agent_pool, tei_service, "Genera embeddings de documentos masivos", "HTTP REST")

Rel(agent_pool, minio, "Lee PDF/Imágenes")
Rel(ai_layer, llm_apis, "Ejecuta LLMs remotos", "HTTPS")
Rel(guidance_system, cms_external, "Obtiene textos", "HTTPS")

@enduml
```

![](assets/GicK_o2ERxYG9ykWqd19Uc18TqUOgEkpEJ14ZW34lHk=.png)

```
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Component.puml

title Nivel C3: Diagrama de Componentes Completo - Ecosistema Backend, Colaboración e IA (IQAS v5)

' ==================== BOUNDARY: CORE API & COLLABORATION ====================
Container_Boundary(api_backend, "Servicios del Backend Core (FastAPI + Hocuspocus)") {
    
    ' Componentes FastAPI
    Component(router, "API Router", "FastAPI", "Endpoints REST/WS. Punto de entrada del Lienzo e Investigadores")
    Component(auth, "Módulo Auth", "JWT / OAuth2", "Valida sesiones, roles de suscripción B2B e identidades")
    Component(guidance_service, "Servicio de Orientación", "Python", "Observa el bus de eventos y despacha tooltips/plantillas sin bloquear hilos")
    Component(vector_manager, "Gestor RAG & Vectores", "SQLAlchemy + pgvector", "Fragmenta transcripciones y ejecuta consultas de similitud")
    Component(task_manager, "Gestor de Delegación", "Celery Client", "Encola intenciones y tareas analíticas en el broker")

    ' Componentes de Colaboración en Tiempo Real (Node.js)
    Component(collab_ws, "WebSocket Handler", "Hocuspocus Server", "Mantiene conexiones concurrentes activas para edición multiusuario")
    Component(yjs_syncer, "Sincronizador Yjs", "Yjs / CRDT", "Resuelve conflictos de edición en tiempo real sobre documentos, códigos y memos")
    Component(persistence_hook, "Hook de Persistencia", "NodeJS Database Client", "Escribe de forma asíncrona los estados binarios de los CRDTs en la BD")
}

' ==================== BOUNDARY: AI LAYER & WORKERS ====================
Container_Boundary(ai_runtime, "Entorno de Ejecución de IA y Agentes (LangGraph + Celery Workers)") {
    
    Container_Boundary(ai_layer, "Capa de Arquitectura de IA (NVIDIA AI-Q drb2)") {
        Component(cwd_trio, "Gestor CWD (Coordinador/Delegador)", "LangGraph", "Mantiene la intención de la fase cualitativa y evalúa la carga")
        Component(critic_loop, "Agente Crítico", "Bucle Generador-Crítico", "Puerta de calidad: valida síntesis hasta obtener APROBADO o escalar")
        Component(context_router, "Enrutador y Optimizador", "Python", "Calcula ventanas de contexto dinámicas para minimizar tokens")
        Component(llm_factory, "LLM Service Factory", "Patrón Abstracto", "Encapsula e intercambia las llamadas a las APIs de inferencia")
    }

    Container_Boundary(agent_workers, "Conjunto de Workers Asíncronos") {
        Component(doc_processor, "Procesador Documental", "PyMuPDF / scikit-image", "Limpieza de PDF con binarización Sauvola y extracción estructural")
        Component(anomaly_module, "Módulo de Anomalías", "Interceptador de Síntesis", "Protege e indexa voces divergentes evitando la homogeneización del LLM")
        Component(nlp_extractor, "Extractor NLP", "Python / Celery Task", "Lleva a cabo tareas atómicas de codificación abierta y etiquetado")
    }
}

' ==================== ALMACENAMIENTO Y EVENTOS CONCRETOS ====================
ContainerDb(db, "PostgreSQL + pgvector", "SQL", "Persistencia de estado CWD, metadatos, vectores e instancias Yjs")
Container(minio, "MinIO", "S3", "Almacenamiento de audios, imágenes y PDFs originales")
Container(redis, "Redis", "Broker / Bus de Eventos", "Mensajería Celery y Pub/Sub para escalado horizontal de WebSockets")

Component(tei_api, "API Text Embeddings (TEI)", "Microservicio Local (Puerto 8080)", "Maneja F2LLM/Jina en memoria aislada con Batching Dinámico")

' ==================== INFRAESTRUCTURA Y SISTEMAS EXTERNOS ====================
System_Ext(cms_guidance, "CMS Headless", "Sistema externo (Tooltips/Tutoriales)")
System_Ext(template_registry, "Registro Comunitario", "Repositorio de plantillas validadas")
System_Ext(local_embeds, "Local Embeddings", "F2LLM-v2-4B / Jina v5 text small")

System_Ext(ds_pro, "DeepSeek Pro API", "Zero-Shot / Razonamiento profundo")
System_Ext(ds_flash, "DeepSeek Flash API", "Extracción Atómica")
System_Ext(gemma, "Gemma 4 31B API", "Estructuración Lingüística / Formatos")
System_Ext(glm, "GLM-5V Turbo API", "Análisis Visual Aislado")
System_Ext(nemotron, "Nemotron 3 API", "Deep Research")

' ==================== RELACIONES DEL BACKEND CORE ====================
Rel(router, auth, "Valida token")
Rel(router, doc_processor, "Envía flujos de archivos pesados")
Rel(router, cwd_trio, "Inicia/Muta estados del grafo cualitativo")
Rel(router, guidance_service, "Solicita contenido de ayuda")

Rel(collab_ws, yjs_syncer, "Transmite mutaciones de texto/lienzo")
Rel(yjs_syncer, persistence_hook, "Envía actualizaciones consolidadas")
Rel(persistence_hook, db, "Escribe estados binarios de la sesión", "SQL")
Rel(collab_ws, redis, "Escucha/Sincroniza eventos Pub/Sub inter-instancia")

Rel(guidance_service, redis, "Escucha eventos de estado del proyecto (Solo lectura)")
Rel(guidance_service, cms_guidance, "Descarga textos dinámicos", "API REST")
Rel(guidance_service, template_registry, "Verifica firmas de plantillas", "API REST")

Rel(doc_processor, minio, "Almacena y recupera binarios limpios", "S3 API")
Rel(vector_manager, db, "Búsqueda de vecinos cercanos (HNSW)", "SQL")
Rel(vector_manager, local_embeds, "Genera representaciones vectoriales locales", "HTTP/gRPC")

' ==================== RELACIONES DE LA CAPA DE IA Y WORKERS ====================
Rel(router, task_manager, "Despacha tareas complejas en lote")
Rel(task_manager, redis, "Registra payloads en colas (Fast/Heavy)", "Redis Protocol")
Rel(redis, cwd_trio, "Consume intenciones de orquestación")
Rel(redis, nlp_extractor, "Asigna subtareas etiquetadas")

Rel(cwd_trio, vector_manager, "Solicita piezas de contexto (RAG)")
Rel(nlp_extractor, anomaly_module, "Entrega borradores analíticos crudos")
Rel(anomaly_module, critic_loop, "Envía datos cualitativos protegidos contra homogeneización")

Rel(critic_loop, context_router, "Solicita regeneración controlada ante rechazos")
Rel(context_router, llm_factory, "Instancia cliente de inferencia con contexto optimizado")

Rel(vector_manager, tei_api, "Pide vector para query", "HTTP POST")
Rel(doc_processor, tei_api, "Pide vectores en lote para segmentación", "HTTP POST")

' Fábrica de LLMs enrutando a proveedores externos
Rel(llm_factory, ds_pro, "Ejecuta (Heavy MoE)")
Rel(llm_factory, ds_flash, "Ejecuta (Fast Text)")
Rel(llm_factory, gemma, "Ejecuta (Structured Context)")
Rel(llm_factory, glm, "Ejecuta (Vision Aislada)")
Rel(llm_factory, nemotron, "Ejecuta (Research)")

@enduml
```

![](assets/mzX6EgX8eEa3pWk4_kp2ZfcQvQ1MHxC0Ehg2iOi7kCc=.png)

