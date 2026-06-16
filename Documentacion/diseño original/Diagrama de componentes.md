# Diagrama de componentes

# 4. Diagrama de Componentes Unificado

```
@startuml IQAS_DiagramaComponentes_v6_ES_CORREGIDO
!theme plain
skinparam componentStyle rectangle
skinparam linetype ortho
skinparam packageBackgroundColor #FAFAFA
skinparam componentBackgroundColor #FFFFF0
skinparam databaseBackgroundColor #E8F5E9
skinparam actorBackgroundColor #E3F2FD
skinparam ArrowColor #555555

' ══════════════════════════════════════
'  LEYENDA DE REVISIONES
'  [R]  = Robustez (v4 → v5)
'  [S]  = Seguridad (v5)
'  [v6] = Cambios nuevos en v6:
'         + AG_SAMP_THEO : MuestreadorTeórico A17 explícito (§2.1)
'         + REG_EXEC     : Registro Ejecución Agentes (§2.5)
'         + DB_EXEC_LOG  : Log de ejecución de agentes (§2.5)
'         + nota recodificación masiva Fase 5a.3 (§2.6)
' ══════════════════════════════════════

' ══════════════════════════════════════
'  ACTORES EXTERNOS
' ══════════════════════════════════════
actor "Investigador Principal"  as ADMIN
actor "Colaborador"             as COLLAB
actor "Estudiante"              as STUDENT
actor "Auditor"                 as AUDITOR
actor "Visualizador"            as VIEWER

' ══════════════════════════════════════
'  SISTEMAS EXTERNOS
' ══════════════════════════════════════
package "Sistemas Externos" #F5F5F5 {
  [Proveedores LLM\n(DeepInfra · Together AI · Fireworks\n· niveles Frontera · Equilibrado · Rápido)] [R]  as LLM_PROVIDERS
  [Fuentes Externas\n(web · audio/video · BD · social)]                                                    as EXT_SRC
  [Motor de Flujo de Trabajo n8n]                                                                           as N8N
  [CMS de Contenido de Orientación\n(headless · tooltips · tutoriales · tarjetas primarias)]               as CMS
  [Registro Comunitario de Plantillas\n(paquetes JSON firmados · control de versiones)]                    as TMPL_REG
  [Gestor de Secretos Externo\n(HashiCorp Vault / AWS Secrets Manager\n· rotación automática de credenciales)] [S]  as EXT_SECRET_STORE
  [Registro de Contenedores + SBOM\n(Cosign · Sigstore · firma de imagen por SHA\n· SBOM Syft por imagen Docker)] [S]  as CONTAINER_REG
  [Stripe API\n(pagos · webhooks · facturación)] [R]                                                        as STRIPE_API
}

' ══════════════════════════════════════
'  LÍMITE DEL SISTEMA
' ══════════════════════════════════════
package "Sistema Integrado de Análisis Cualitativo v6 (Seguro · Robusto)" #FFFDE7 {

  ' ─────────────────────────────────
  '  CAPA DE PRESENTACIÓN
  ' ─────────────────────────────────
  package "Capa de Presentación" #EDE7F6 {
    [Panel de Administración\n(usuarios · permisos · configuración proyecto\n· selección de ruta · selector plantillas)]              as UI_ADMIN
    [IU del Lienzo del Plan de Análisis\n(editor de nodos estilo KNIME\n· tablero de estado · vista de fases en vivo\n· exportación de diagrama metodológico)]  as UI_CANVAS
    [Visor de Corpus y Codificación\n(segmentos · etiquetas Glaser · asignaciones\n· banderas de anomalía · residuos)]                as UI_CORPUS
    [Tablero Lexicométrico\n(Reinert · BERTopic · KWIC\n· MCA · RF/SHAP · informes de síntesis)]                                     as UI_LEXICO
    [Taller Cualitativo\n(posturas · gestos · silencios\n· expansión externa · asistente)]                                            as UI_WORKSHOP
    [Módulo de Visualización\n(5c: viñetas · grafos · Sankey\n· dendrogramas · mapas de posición)]                                   as UI_VIZ
    [Taller de Redacción\n(ordenamiento · selector esqueleto\n· volcado de ideas · alertas de vacíos · violaciones de reglas)]        as UI_WRITE
    [Tablero de Auditoría\n(rastro · historial de cambios · reflexividad\n· COREQ · evolución · trazabilidad IA [v6])]                as UI_AUDIT
    [Visor de Informes\n(salidas publicadas · exportaciones)]                                                                         as UI_REPORTS
  }

  ' ─────────────────────────────────
  '  PUERTA DE ENLACE + CONTROL DE ACCESO
  ' ─────────────────────────────────
  package "Puerta de Enlace y Control de Acceso" #FFCCBC {
    [Puerta de Enlace API\n(enrutamiento · registro de solicitudes\n· punto de entrada único)]                                        as GATEWAY
    [Filtro CORS [S]\n(lista blanca de dominios explícita\n· sin wildcard en producción\n· credenciales explícitas · preflight cache)] as CORS_FILTER
    [Middleware Anti-CSRF [S]\n(tokens doble-submit cookie\n· validación estricta Origin/Referer\n· exento para endpoints JWT Bearer)] as CSRF_FILTER
    [Limitador de Tasa [S]\n(ventana deslizante Redis · por IP · por usuario\n· por endpoint · bloqueo temporal con backoff exponencial)] as RATE_LIMITER
    [Middleware Cabeceras de Seguridad [S]\n(HSTS max-age=31536000\n· CSP frame-ancestors 'none'\n· X-Frame-Options DENY\n· X-Content-Type-Options nosniff\n· Referrer-Policy strict-origin\n· Permissions-Policy restrictiva)]  as SEC_HEADERS
    [Middleware Sanitizador de Errores [S]\n(suprime stack traces en producción\n· mapeo a códigos de error genéricos\n· rutas internas y queries SQL nunca expuestas\n· logging interno a STRUCT_LOGGER)]                          as ERROR_SANITIZER
    [Servicio de Autenticación\n(JWT · sesión · MFA · PKCE\n· refresh token rotation)]                                               as AUTH
    [Servicio de Aplicación de Permisos]                                                                                              as PES
    [Filtro de Acceso a Datos\n(enmascaramiento segmentos · filtro analíticas\n· ámbito documento)]                                   as DAF
  }

  ' ─────────────────────────────────
  '  SEGURIDAD TRANSVERSAL  [S]
  ' ─────────────────────────────────
  package "Seguridad Transversal [S]" #FFD0D0 {
    [Adaptador de Gestor de Secretos\n(abstracción Vault / AWS SM · sin .env en prod\n· inyección de credenciales en runtime\n· caché local cifrada en memoria · rotación automática\n· fallback a local_env solo en desarrollo)]         as SECRET_MGR
    [Lista Negra JWT\n(revocación de tokens antes de expiración\n· almacenada en Redis con TTL exacto igual al token\n· consultada en cada request autenticado\n· activada en logout explícito y en compromiso detectado)]              as JWT_BLACKLIST
    [Firmador de Tareas Celery\n(firma HMAC-SHA256 por tipo de tarea\n· clave gestionada por SECRET_MGR\n· validación en worker antes de cualquier ejecución\n· previene inyección de tareas vía Redis comprometido\n· rotación periódica de clave de firma)]  as TASK_SIGNER
    [Gestor de Retención y Borrado GDPR\n(pipeline right-to-erasure bajo solicitud\n· borrado programado por política de retención\n· anonimización total de PII residual\n· registro de conformidad con timestamp y firmante)]         as DATA_RETENTION
    [Generador de SBOM + Firmado de Imagen\n(Syft genera SBOM por imagen Docker\n· Grype analiza vulnerabilidades en SBOM\n· Cosign firma imagen y SBOM\n· integrado en pipeline CD · push a CONTAINER_REG)]                            as SBOM_GEN
    [Logger Estructurado con Scrubbing de PII\n(formato JSON · redacción automática de PII\n(email · nombre · documento · IP raw)\n· niveles de log por entorno\n· forward a SIEM con alertas configurables)]                          as STRUCT_LOGGER
  }

  ' ─────────────────────────────────
  '  GESTIÓN DE PERMISOS
  ' ─────────────────────────────────
  package "Gestión de Permisos" #E3F2FD {
    [Administrador de Perfil de Colaborador]  as CPM
    [Administrador de Perfil de Estudiante]   as SPM
    [Administrador de Perfil de Auditor]      as APM
    [Administrador de Perfil de Visualizador] as VPM
    [Registrador de Auditoría de Permisos]    as PAL
  }

  ' ─────────────────────────────────
  '  SISTEMA DE ORIENTACIÓN Y PLANTILLAS
  ' ─────────────────────────────────
  package "Sistema de Orientación y Plantillas" #FFF8E1 {
    [Motor de Plantillas Metodológicas\n(carga · valida · verifica firma criptográfica\n· despacho IPlantillaMetodológica)]            as TMPL_ENG
    [Servicio del Lienzo del Plan de Análisis\n(CRUD de nodos · validación topología\n· generación EspecificaciónEjecución\n· push de estado en vivo)]  as CANVAS_SVC
    [Asistente de Investigación IA\n(consciente del contexto · barra lateral colapsable\n· explica nodos · propone memos\n· registra reflexividad)]      as COMPANION
    [Servidor de Contenido de Orientación\n(tooltips · tarjetas primarias · tutoriales\n· obtención diferida CMS · caché local)]                        as GUIDE_SVC
    [Servicio de Registro de Plantillas\n(plantillas comunitarias · semver\n· verificación de firma criptográfica)]                                      as TMPL_STORE
  }

  ' ─────────────────────────────────
  '  ORQUESTACIÓN
  ' ─────────────────────────────────
  package "Orquestación" #E8EAF6 {
    [Orquestador de Fases\n(avanzar · validar · transiciones\n· lee EspecificaciónEjecución del Lienzo\n· activa recodificación masiva Fase 5a.3 [v6])]  as ORCH
    [Administrador de Bucles de Retroalimentación\n(15 bucles nombrados · mapeo Tabla 2\n· integración con anti-repetición)]          as FBK
    [Anti-repetición de Bucles de Retroalimentación\n(enfriamiento 30s · por bucle · previene vibración)]                            as DEBOUNCE
    [Bus de Eventos\n(asíncrono · eventos de fase · push WebSocket)]                                                                  as EBUS
    [Administrador de Ventana de Contexto Rodante\n(ventana 3-docs · caché · inyección\n· instantáneas pre-fase)]                    as RCWM
  }

  ' ─────────────────────────────────
  '  CAPA DE ARQUITECTURA DE IA  [R + S + v6]
  ' ─────────────────────────────────
  package "Capa de Arquitectura de IA (Robustecida + Segura)" #FFE0B2 {
    [Agente Coordinador\n(intención estratégica de fase\n· coherencia entre agentes · resolución conflictos)]                          as CWD_COORD
    [Agente Delegador\n(enrutamiento por etiqueta capacidad\n· balanceo de carga · registro agentes\n· registra cada despacho en REG_EXEC [v6])]         as CWD_DELEG
    [LiteLLM Proxy [R]\n(enrutador multi-proveedor\n· fallback automático DeepInfra→Together AI→Fireworks\n· timeout 30s · retry con backoff exponencial\n· circuit breaker: 5 fallos → abierto 60s\n· solo modelos con hash autorizado en MODEL_VERSION_MGR)]  as LITELLM
    [Administrador de Versión de Modelos [R]\n(hash SHA fijo de modelos LLM y ONNX\n· impide alias dinámicos y actualizaciones silenciosas\n· tabla model_versions en DB_MODEL_VER\n· alerta a DB_SEC_LOG ante discrepancia de hash)]         as MODEL_VERSION_MGR
    [Detector de Inyección de Prompt [S]\n(sanitización de contenido de documentos pre-LLM\n· detección de instrucciones ocultas y metacomandos\n· normalización Unicode hostil (homoglifos · RTLO)\n· cuarentena de contenido sospechoso\n· alerta a DB_SEC_LOG en detección positiva)]  as PROMPT_INJ_DETECT
    [Servicio Enrutador de Modelos\n(despacho RÁPIDO_ECONÓMICO · EQUILIBRADO\n· RAZONAMIENTO_POTENTE · seguimiento de costo)]          as MODEL_ROUTER
    [Constructor de Contexto de Agente\n(presupuesto 4000 tokens\n· ensamblaje de contexto mínimo\n· inyección de ventana rodante)]    as CTX_BUILD
    [Flujo Generador-Crítico\n(máx 3 ciclos de revisión\n· emparejamiento productor + crítico\n· escalada humana\n· registra veredicto en REG_EXEC [v6])] as GEN_CRIT
    [Aplicador de Políticas IA\n(guardarraíl ascendente · anti-alucinación\n· ética · PII · metodología)]                             as POLICY
    [Ejecutor por Lotes de API [R]\n(agrupa llamadas por nivel de modelo\n· reduce viajes de ida y vuelta)]                            as BATCH_EXEC
    ' ── [v6] §2.5 NUEVO ────────────────────────────────────
    [Servicio Registro Ejecución Agentes [v6]\n(versión prompt por agente · modelo LLM y proveedor\n· hash SHA entrada/salida · costo tokens\n· veredicto del crítico por ciclo\n· trazabilidad completa auditable por fase)]  as REG_EXEC
    ' ─────────────────────────────────────────────────────
  }

  ' ─────────────────────────────────
  '  SERVICIOS CENTRALES DE ANÁLISIS
  ' ─────────────────────────────────
  package "Servicios Centrales de Análisis" #FCE4EC {
    [Motor de Codificación\n(Fases 3 · 4 · 5b · bucle comparación constante\n· despachado por CWD)]                                  as CE
    [Motor de Comparación Secuencial\n(orden estricto incidente a incidente\n· detector perspicacia interruptiva · activador memo)]    as SEQ_COMP
    [Módulo de Preservación de Anomalías\n(protección voz divergente\n· registro perspectiva minoritaria · evita homogeneización)]    as ANOM
    [Administrador de Categorías\n(dividir · fusionar · refinar\n· verificación intercambiabilidad)]                                  as CM
    [Servicio Rastreador de Saturación\n(por categoría · por relación · por fase\n· guardia global 100 iteraciones/fase [v6])]        as SAT
    [Administrador de Memos]                                                                                                          as MEMO_SVC
    [Administrador de Grupo de Variables]                                                                                             as VAR_SVC
    [Servicio de Plan de Muestreo\n(coordina con A17 MuestreadorTeórico\n· genera PlanDeMuestreo con casos\ncontraste · extremos · consistentes)]  as SAMP_SVC
    [Servicio de Candidatos a Fusión y Relación\n(ranking por prioridad · umbrales configurables)]                                   as FRCAND
    [Registrador de Cambios por Diferencias\n(parches estilo git · diferencias JSON\n· resumen legible · incidentesMotivadores [v6])] as DIFF_REC
    [Administrador de Buffer de Residuos\n(máx 500 entradas · archivo al desbordarse)]                                               as RESID_SVC
    [Servicio Generador de Informes\n(Aplicador de 5 Reglas de Redacción\n· puerta de Política IA antes de salida)]                  as REP_SVC
    [Servicio de Caché\n(contexto rodante · incrustaciones · instantáneas pre-fase)]                                                 as CACHE
    [Servicio de Suscripciones [R]\n(planes · cuotas de tokens · integración Stripe\n· actualización atómica de límites de usuario)] as SUBS_SVC
    [Log de Idempotencia de Webhooks [R]\n(tabla webhook_logs · stripe_event_id UNIQUE\n· verificación antes de cualquier procesamiento\n· previene doble acreditación de tokens/plan)]  as IDEMPOTENCY
  }

  ' ─────────────────────────────────
  '  CONJUNTO DE AGENTES IA  [v6: A17 TheoSampler explícito]
  ' ─────────────────────────────────
  package "Conjunto de Agentes IA" #FFF3E0 {
    [Agentes de Segmentación\nA01 CodificadorAbierto · A02 Resegmentador\n[nivel EQUILIBRADO]]                                        as AG_SEG
    [Agentes de Agrupamiento\nA03 AgrupadorDocumento · A04 AgrupadorInterDocumento\n[nivel EQUILIBRADO]]                              as AG_CLU
    [Agentes de Memo\nA05 Proponente · A06 Probador · A11-A13\n(Grupos · Clústeres · ProbadorHipótesis)\n[nivel EQUILIBRADO]]         as AG_MEMO
    [Agentes de Emergencia Central\nA14 SensorPreocupaciónPrincipal · A15 DetectorEmergenciaCentral\nA16 ProbadorIntercambiabilidad\n[nivel RAZONAMIENTO_POTENTE]]  as AG_CORE
    ' ── [v6] §2.1 A17 separado para visibilidad explícita ──
    [A17 MuestreadorTeórico [v6]\n(diseña estrategias de muestreo teórico\nbasadas en puntajeDeRelevancia de categorías\n· genera PlanDeMuestreo:\n  casosContraste · casosExtremos · casosConsistentes\n· coordina con SAMP_SVC\n[nivel EQUILIBRADO])]  as AG_SAMP_THEO
    ' ─────────────────────────────────────────────────────
    [A18 ComparadorDocumentos\n(comparación sistemática entre documentos\n· detección de variaciones y contrastes\n[nivel EQUILIBRADO])]  as AG_SAMP_CMP
    [Agentes de Recodificación\nA07-A10: AgrupadorGeneral · Consolidador\nA09 Recodificador · LibroCódigosVariables\n[nivel RÁPIDO_ECONÓMICO]]  as AG_RECODE
    [Agentes de Vacío y Redacción\nA21 DetectadorVacíos · A24 EscritorNatural · A28 AgenteOrdenamiento\n[nivel RAZONAMIENTO_POTENTE]] as AG_GAP
    [Agentes de Síntesis\nA22-A31: Literatura · Memo · Retórica\nMultiSintetizador · RecomendadorRelaciones\n[nivel EQUILIBRADO/POTENTE]]  as AG_SYN
    [Nodos de Análisis Paralelo\nPatrones · Propiedades · Causas\nConsecuencias → SintetizadorMemos\n[nivel EQUILIBRADO]]             as AG_PAR
    [Agente Preservador de Anomalías\nA32: señala voces divergentes\nprotege incidencias minoritarias\n[nivel RÁPIDO_ECONÓMICO]]      as AG_ANOM
  }

  ' ─────────────────────────────────
  '  FLUJO NLP  [interfaz IMóduloNLP]
  ' ─────────────────────────────────
  package "Flujo NLP (modular — IMóduloNLP)" #E0F2F1 {
    [Caché de Incrustaciones Compartidas\n(calcula una vez · sirve a BERTopic + RAG\n· versionado · ~50% ahorro de cómputo)]          as NLP_CACHE
    [Módulo BERTopic\n[IMóduloNLP · versionado]]                                                                                      as NLP_BTP
    [Módulo Reinert / Lexicométrico\n(UC · UCE · clases · Venn\n· árbol de persistencia · sedimentación\n[IMóduloNLP · versionado])]  as NLP_REI
    [ONNX Runtime Embedder [R]\n(bge-m3 convertido a .onnx · hash SHA fijado\n· inferencia determinista y reproducible\n· empaquetado offline en imagen Docker\n· sin acceso a HuggingFace en runtime\n· 40% menos RAM vs sentence-transformers\n[IMóduloNLP · versionado])]  as NLP_ONNX
    [Selector de Variables RF / SHAP\n[IMóduloNLP · versionado]]                                                                      as NLP_RF
    [Módulo MCA\n[IMóduloNLP · versionado]]                                                                                           as NLP_MCA
    [NER y Análisis del Discurso\n(entidades · figuras retóricas\n[IMóduloNLP])]                                                      as NLP_NER
    [KWIC y Búsqueda de Términos\n[IMóduloNLP]]                                                                                       as NLP_KWIC
    [Servicio ML de Datos de Calidad\n(puntuación calidad segmentos\n· banderas de calidad de clase\n[IMóduloNLP])]                   as NLP_QML
    [Servicio de Paráfrasis y Resumen\n(paráfrasis de segmentos largos\n· resúmenes · motores primarios)]                             as NLP_PARA
    [Registro de Módulos NLP\n(registro de plugins\n· descubrimiento de capacidades\n· generación de nodos en el Lienzo)]             as NLP_REG
    [Motor de Visualización\n(renderiza: Venn · radial · co-ocurrencia\n· Sankey · dendrogramas · 2×2\n[plugins IRenderizadorVisualización])]  as NLP_VIZ_ENG
  }

  ' ─────────────────────────────────
  '  SERVICIOS DE DATOS  [S — pipeline de seguridad de archivos]
  ' ─────────────────────────────────
  package "Servicios de Datos" #E8F5E9 {
    [Procesador de Documentos e Ingesta\n(8 tipos de fuente · limpieza\n· separación de interlocutores)]                              as DS_DOC
    [Escáner de Malware [S]\n(ClamAV · reglas YARA personalizadas\n· sandbox de ejecución aislado\n· cuarentena automática de archivos positivos\n· alerta inmediata a DB_SEC_LOG\n· bloqueo del archivo antes de cualquier procesamiento)]  as DS_MALWARE
    [Sanitizador de Archivos [S]\n(validación magic bytes vs MIME declarado\n· strip de metadatos EXIF / PDF / Office\n· límite de tamaño configurable por tipo\n· validación profunda de estructura interna del archivo\n· rechazo si hay discrepancia magic/MIME)]  as DS_FILE_SANIT
    [Generador de Índice Estructural\n(secciones · etiquetas de preguntas\n· marcadores de turno de hablante)]                        as DS_IDX
    [Enrutador de Estrategia de Volumen de Tokens\n(lote · hilado · completo)]                                                        as DS_TOK
    [Motor de Segmentación\n(gramática · coref · BERTopic · división de oraciones)]                                                   as DS_SEG
    [Servicio de Consulta RAG\n(máx 5 resultados · timeout 3s)]                                                                       as DS_RAG
    [Servicio GraphRAG\n(recuperación consciente de relaciones\n· grafo de entidades entre documentos\n· contexto más rico que RAG plano)]  as DS_GRAG
    [Servicio OCR / Transcripción\n(Whisper · monólogo vs conversación)]                                                              as DS_OCR
    [Servicio de Anonimización y Enmascaramiento\n(GDPR · HIPAA · verificación DPA\n· puerta pre-llamada API externa\n· cifrado de PII residual en reposo\n· claves gestionadas por SECRET_MGR)]  as DS_ANON
  }

  ' ─────────────────────────────────
  '  SERVICIO DE BIBLIOGRAFÍA
  ' ─────────────────────────────────
  package "Servicio de Bibliografía" #F3E5F5 {
    [Indexador BibTeX + PDF\n(inyección Fase 0.3\n· modo como-datos Fase 6c)]              as BIB_IDX
    [Búsqueda Semántica de Citas]                                                           as BIB_SEARCH
    [Administrador de Citas\n(fusión heurística · traducción de términos\n· puente hacia teoría formal)]  as BIB_MGR
  }

  ' ─────────────────────────────────
  '  WORKERS ASÍNCRONOS  [R + S]
  ' ─────────────────────────────────
  package "Workers Asíncronos (Celery) [R]" #FFFACD {
    [Celery App\n(serialización JSON estricta\n· task_serializer='json' · result_serializer='json'\n· accept_content=['json'] · sin pickle en ningún modo\n· conexión a Redis con TLS + AUTH\n· credenciales inyectadas por SECRET_MGR)]  as CELERY_APP
    [Tareas de Documento\n(OCR · parsing PDF · embeddings\n· pipelines de larga duración · concurrencia limitada)]  as DOC_TASKS
    [Notificación WebSocket\n(push de estado de tareas al frontend\n· progreso en tiempo real vía Event Bus)]         as NOTIFY
    [Almacén de Idempotencia de Tareas [R]\n(tabla celery_task_ids con task_id UNIQUE\n· registro antes de ejecutar\n· segunda llamada con mismo task_id descartada\n· previene doble procesamiento en reinicio de worker)]  as TASK_IDEM
  }

  ' ─────────────────────────────────
  '  INFRAESTRUCTURA DE CONEXIÓN BD  [S]
  ' ─────────────────────────────────
  package "Infraestructura de Conexión BD [S]" #F0FFF0 {
    [PgBouncer\n(pool de conexiones PostgreSQL\n· modo transaction · autenticación scram-sha-256\n· límite de conexiones por servicio y usuario\n· limita el radio de explosión de credenciales comprometidas)]  as PGBOUNCER
  }

  ' ─────────────────────────────────
  '  CAPA DE ALMACENAMIENTO  [interfaz IAdaptadorAlmacenamiento]
  ' ─────────────────────────────────
  package "Almacenamiento (backends IAdaptadorAlmacenamiento)" #F1F8E9 {
    database "BD Principal — PostgreSQL + pgvector\n(Documentos · Segmentos · Categorías\n· Asignaciones Código · Usuarios · Fases\n· Nodos Lienzo · Plantillas · Planes Muestreo\n· Row-Level Security (RLS) activado [S]\n· cifrado en reposo · audit logging nativo)"  as DB_MAIN
    database "Índice Vectorial\n(incrustaciones de segmentos y RAG\n· pgvector · índices HNSW incrementales [R]\n· inserciones sin reindexado periódico)"      as DB_VEC
    database "Índice GraphRAG\n(nodos entidad · aristas relación\n· estructura entre documentos)"                  as DB_GRAPH
    database "Almacén Bibliográfico\n(metadatos BibTeX · referencias PDF\n· vectores bibliográficos)"             as DB_BIB
    database "Banco de Memos\n(persistente · versionado · hashTema\n· grupos temáticos · memos_finales)"          as DB_MEMO
    database "Almacén de Historial de Cambios\n(parches JSON estilo git · resúmenes legibles\n· registros de permisos · reflexividad\n· incidentesMotivadores por cambio [v6])"  as DB_HIST
    database "Almacén de Buffer de Residuos\n(máx 500 entradas · archivo al desbordarse)"                         as DB_RESID
    database "Almacén de Registro de Ordenamiento\n(iteraciones · grupos · vacíos · memos sin hogar)"             as DB_SORT
    database "Almacén de Perfiles y Políticas\n(colaborador · estudiante · auditor · visualizador)"               as DB_PERM
    database "Almacén de Resultados NLP\n(Reinert · BERTopic · Incrustaciones\n· MCA · SHAP · síntesis de clase · versionado)"  as DB_NLP
    database "Almacén de Informes\n(secciones · reglas de redacción\n· líneas futuras · auditabilidad)"           as DB_REP
    database "Almacén de Artefactos de Visualización\n(todos los tipos de artefacto\n· renderizados lexicométricos)"  as DB_VIZ
    database "Caché de Contexto e Incrustaciones\n(ventana rodante 3-docs · incrustaciones compartidas\n· instantáneas pre-fase\n· Redis con TLS + requirepass [S]\n· Lista Negra JWT con TTL [S])"  as DB_CACHE
    database "Almacén de Plantillas y Orientación\n(plantillas metodológicas · tutoriales\n· tooltips · tarjetas primarias)"  as DB_TMPL
    database "Almacén de Preservación de Anomalías\n(voces divergentes · segmentos minoritarios\n· registros de preservación)"  as DB_ANOM
    database "Log de Webhooks Stripe [R]\n(stripe_event_id TEXT PRIMARY KEY\n· processed_at TIMESTAMP · payload JSONB\n· índice único garantiza idempotencia)"  as DB_WEBHOOK
    database "Log de Idempotencia de Tareas Celery [R]\n(task_id TEXT PRIMARY KEY · created_at TIMESTAMP\n· task_type · estado de ejecución)"  as DB_TASK_IDEM
    database "Log de Seguridad Inmutable [S]\n(eventos de auth fallida · accesos denegados\n· intentos de inyección de prompt · detecciones de malware\n· discrepancias de hash de modelos · cambios de permisos críticos\n· registros hash-chained · append-only · forward a SIEM)"  as DB_SEC_LOG
    database "Almacén de Versiones de Modelos [R+S]\n(hash SHA de modelos LLM y ONNX autorizados\n· historial de autorizaciones con timestamp y firmante\n· alertas ante uso de alias dinámicos\n· consultado por LITELLM en cada llamada)"  as DB_MODEL_VER
    ' ── [v6] §2.5 NUEVO ────────────────────────────────────
    database "Log de Ejecución de Agentes [v6]\n(versión prompt · modelo LLM · proveedor\n· hash SHA entrada/salida · costo tokens\n· veredicto del crítico · por agente y fase\n· append-only para trazabilidad completa)"  as DB_EXEC_LOG
    ' ─────────────────────────────────────────────────────
  }
}

' ══════════════════════════════════
'  ACTOR → PRESENTACIÓN
' ══════════════════════════════════
ADMIN   --> UI_ADMIN
ADMIN   --> UI_CANVAS   : "diseñar flujo"
ADMIN   --> UI_CORPUS
ADMIN   --> UI_WORKSHOP
ADMIN   --> UI_LEXICO
ADMIN   --> UI_WRITE
ADMIN   --> UI_VIZ
ADMIN   --> UI_AUDIT

COLLAB  --> UI_CANVAS   : "solo vista (lectura)"
COLLAB  --> UI_CORPUS   : "filtrado por perfil"
COLLAB  --> UI_LEXICO   : "según política analíticas"
COLLAB  --> UI_WORKSHOP : "si fase permitida"
COLLAB  --> UI_WRITE    : "si fase permitida"

STUDENT --> UI_CORPUS   : "lectura / escritura limitada"
STUDENT --> UI_LEXICO   : "solo básico"

AUDITOR --> UI_AUDIT    : "solo lectura"
AUDITOR --> UI_REPORTS  : "solo lectura"

VIEWER  --> UI_REPORTS  : "solo lectura"
VIEWER  --> UI_VIZ      : "solo publicados"

' ══════════════════════════════════
'  PRESENTACIÓN → PUERTA DE ENLACE
' ══════════════════════════════════
UI_ADMIN    --> GATEWAY
UI_CANVAS   --> GATEWAY
UI_CORPUS   --> GATEWAY
UI_WORKSHOP --> GATEWAY
UI_LEXICO   --> GATEWAY
UI_WRITE    --> GATEWAY
UI_VIZ      --> GATEWAY
UI_AUDIT    --> GATEWAY
UI_REPORTS  --> GATEWAY

' ══════════════════════════════════
'  PUERTA DE ENLACE — PIPELINE DE SEGURIDAD (orden de ejecución)
' ══════════════════════════════════
GATEWAY --> CORS_FILTER       : "1. filtro CORS"
GATEWAY --> CSRF_FILTER       : "2. protección CSRF"
GATEWAY --> RATE_LIMITER      : "3. límite de tasa"
GATEWAY --> SEC_HEADERS       : "4. inyectar cabeceras de seguridad"
GATEWAY --> ERROR_SANITIZER   : "5. wrapper de errores"
GATEWAY --> AUTH              : "6. autenticación JWT / sesión"
AUTH    --> JWT_BLACKLIST     : "verifica token no revocado"
AUTH    --> PES               : "identidad resuelta → aplicar permisos"
PES     --> DAF               : "aplicar perfil de acceso a datos"
PES     --> CPM; PES --> SPM; PES --> APM; PES --> VPM
PES     --> PAL               : "registrar decisión de acceso"
DAF     --> ORCH; DAF --> CE; DAF --> NLP_KWIC
CPM --> DB_PERM; SPM --> DB_PERM; APM --> DB_PERM; VPM --> DB_PERM
PAL --> DB_HIST
PAL --> DB_SEC_LOG            : "eventos de acceso y denegación"
AUTH --> DB_SEC_LOG           : "intentos de autenticación fallidos y MFA"
ERROR_SANITIZER --> STRUCT_LOGGER : "errores internos sin PII"

' ══════════════════════════════════
'  SEGURIDAD TRANSVERSAL — CONEXIONES
' ══════════════════════════════════
SECRET_MGR --> EXT_SECRET_STORE : "obtiene secretos en runtime · nunca en .env"
SECRET_MGR --> AUTH             : "credenciales JWT, MFA y sesión"
SECRET_MGR --> DS_ANON          : "claves de cifrado de PII"
SECRET_MGR --> CELERY_APP       : "credenciales Redis TLS y BD para worker"
SECRET_MGR --> LITELLM          : "claves API de proveedores LLM"
SECRET_MGR --> TASK_SIGNER      : "clave HMAC para firma de tareas"
JWT_BLACKLIST --> DB_CACHE      : "almacenado en Redis con TTL exacto"
DATA_RETENTION --> DB_MAIN      : "pipeline right-to-erasure en tablas de usuario"
DATA_RETENTION --> DB_ANOM      : "anonimización total de anomalías con PII"
DATA_RETENTION --> DB_HIST      : "borrado según política de retención"
DATA_RETENTION --> PAL          : "registra conformidad GDPR con firmante"
DATA_RETENTION --> DB_SEC_LOG   : "auditoría de cada operación de borrado"
SBOM_GEN --> CONTAINER_REG      : "empuja SBOM firmado y hash de imagen"
STRUCT_LOGGER --> DB_SEC_LOG    : "persiste eventos críticos estructurados"
TASK_SIGNER --> CELERY_APP      : "provee firma HMAC-SHA256 a cada tarea"

' ══════════════════════════════════
'  SISTEMA DE ORIENTACIÓN Y PLANTILLAS
' ══════════════════════════════════
TMPL_ENG    --> CANVAS_SVC    : "topología + roster"
TMPL_ENG    --> DB_TMPL
TMPL_ENG    --> TMPL_STORE    : "cargar y verificar firma"
TMPL_STORE  --> TMPL_REG      : "obtener paquetes firmados"
CANVAS_SVC  --> ORCH          : "EspecificaciónEjecución"
CANVAS_SVC  --> DB_MAIN       : "persistir nodos del lienzo"
CANVAS_SVC  --> EBUS          : "push de estado a IU"
COMPANION   --> RCWM          : "lee contexto rodante"
COMPANION   --> CM            : "lee categorías actuales"
COMPANION   --> DB_MEMO       : "propone y lee memos"
COMPANION   --> GUIDE_SVC     : "obtiene tutoriales"
GUIDE_SVC   --> CMS           : "obtención diferida de CMS"
GUIDE_SVC   --> DB_TMPL       : "caché de orientación"
UI_CANVAS   --> CANVAS_SVC
UI_WORKSHOP --> COMPANION
UI_CORPUS   --> GUIDE_SVC     : "tooltips al pasar el ratón"

' ══════════════════════════════════
'  ORQUESTACIÓN INTERNA
' ══════════════════════════════════
ORCH --> FBK; ORCH --> EBUS; ORCH --> RCWM
FBK  --> DEBOUNCE
DEBOUNCE --> FBK              : "controla ejecución con enfriamiento"
FBK  --> EBUS
EBUS --> ORCH                 : "eventos de fase"
RCWM --> CACHE; RCWM --> DB_CACHE

' [v6] §2.6 — recodificación masiva OPCIONAL desde Fase 5a.3
' El Orquestador puede activar AG_RECODE (A09) sobre todo el corpus
' si el investigador lo solicita explícitamente en Fase 5a.3
ORCH --> AG_RECODE            : "[Fase 5a.3 — OPCIONAL]\nrecodificación masiva con A09\nsi investigador lo solicita"

' ══════════════════════════════════
'  CAPA DE ARQUITECTURA IA — INTERNA
' ══════════════════════════════════
CWD_COORD  --> CWD_DELEG          : "delega tareas"
CWD_DELEG  --> MODEL_ROUTER       : "selección de nivel de modelo"
MODEL_ROUTER --> LITELLM          : "despacho de llamada LLM"
MODEL_ROUTER --> BATCH_EXEC       : "envía grupo de llamadas a lotes"
LITELLM --> LLM_PROVIDERS         : "llamadas con fallback automático multi-proveedor"
LITELLM --> MODEL_VERSION_MGR     : "valida hash del modelo antes de cada llamada"
MODEL_VERSION_MGR --> DB_MODEL_VER : "persiste y consulta versiones autorizadas"
MODEL_VERSION_MGR --> DB_SEC_LOG  : "alerta si hash de respuesta no coincide"
BATCH_EXEC --> LLM_PROVIDERS      : "llamadas agrupadas por nivel de modelo"
CTX_BUILD  --> RCWM               : "lee ventana de contexto rodante"
CTX_BUILD  --> CM                 : "definiciones de categoría"
CTX_BUILD  --> PROMPT_INJ_DETECT  : "contenido de documento antes de enviarlo a LLM"
PROMPT_INJ_DETECT --> LITELLM     : "contenido sanitizado (o cuarentena si positivo)"
PROMPT_INJ_DETECT --> DB_SEC_LOG  : "registra cada intento de inyección detectado"
GEN_CRIT   --> POLICY             : "examina salida del generador"
POLICY     --> REP_SVC            : "solo salida aprobada por política"
' [v6] §2.5 — trazabilidad de ejecución de agentes
CWD_DELEG  --> REG_EXEC           : "registra cada despacho de agente"
GEN_CRIT   --> REG_EXEC           : "registra veredicto del crítico por ciclo"
REG_EXEC   --> DB_EXEC_LOG        : "persiste trazabilidad completa"

' ══════════════════════════════════
'  ORQUESTACIÓN → ARQUITECTURA IA
' ══════════════════════════════════
ORCH --> CWD_COORD
ORCH --> DEBOUNCE
CWD_COORD --> CE
CWD_COORD --> MEMO_SVC
CWD_COORD --> REP_SVC
CWD_COORD --> AG_GAP
CWD_COORD --> AG_SYN

' ══════════════════════════════════
'  SERVICIOS CENTRALES — INTERNOS
' ══════════════════════════════════
CE --> CM; CE --> SAT; CE --> MEMO_SVC; CE --> VAR_SVC
CE --> SAMP_SVC; CE --> FRCAND; CE --> RESID_SVC
CE --> CACHE                  : "leer/escribir contexto rodante"
CE --> SEQ_COMP               : "aplicar orden de comparación constante"
CE --> ANOM                   : "proteger segmentos divergentes"
CE --> NLP_BTP; CE --> NLP_REI; CE --> NLP_RF
CE --> NLP_NER; CE --> NLP_KWIC; CE --> NLP_QML
CE --> DB_MAIN; CE --> DB_RESID
CM --> DIFF_REC
MEMO_SVC --> AG_MEMO
SAMP_SVC --> AG_SAMP_THEO     : "delega diseño de estrategia a A17"
SAMP_SVC --> AG_SAMP_CMP      : "delega comparación a A18"
FRCAND --> CM                 : "proponer fusión o relación"
SEQ_COMP --> MEMO_SVC         : "perspicacia interruptiva → memo"
ANOM --> DB_ANOM
SUBS_SVC --> IDEMPOTENCY      : "verifica stripe_event_id antes de procesar"
SUBS_SVC --> STRIPE_API       : "gestión de planes y facturación"
IDEMPOTENCY --> DB_WEBHOOK    : "persiste y consulta eventos de Stripe"

' ══════════════════════════════════
'  SERVICIOS CENTRALES → CONJUNTO DE AGENTES (vía CWD)
' ══════════════════════════════════
CWD_DELEG --> AG_SEG;    CWD_DELEG --> AG_CLU
CWD_DELEG --> AG_CORE;   CWD_DELEG --> AG_SAMP_THEO
CWD_DELEG --> AG_SAMP_CMP
CWD_DELEG --> AG_RECODE; CWD_DELEG --> AG_PAR
CWD_DELEG --> AG_MEMO;   CWD_DELEG --> AG_ANOM
AG_SEG --> CTX_BUILD;    AG_CORE --> CTX_BUILD
AG_SYN --> CTX_BUILD;    AG_GAP --> CTX_BUILD
AG_PAR --> GEN_CRIT;     AG_SYN --> GEN_CRIT
AG_CORE --> GEN_CRIT

' ══════════════════════════════════
'  FLUJO NLP — INTERNO Y ALMACENAMIENTO
' ══════════════════════════════════
NLP_ONNX --> NLP_CACHE        : "produce vectores deterministas"
NLP_BTP --> NLP_CACHE         : "lee incrustaciones compartidas"
DS_RAG  --> NLP_CACHE         : "lee incrustaciones para RAG"
NLP_CACHE --> DB_VEC          : "almacena vectores"
NLP_REG --> CE                : "módulos NLP disponibles"
NLP_REG --> CANVAS_SVC        : "registra módulos como nodos del Lienzo"
DS_DOC  --> NLP_PARA
NLP_RF  --> NLP_MCA
NLP_REI --> NLP_VIZ_ENG; NLP_BTP --> NLP_VIZ_ENG
NLP_ONNX --> NLP_VIZ_ENG; NLP_MCA --> NLP_VIZ_ENG
NLP_BTP --> DB_NLP; NLP_REI --> DB_NLP
NLP_RF --> DB_NLP
NLP_MCA --> DB_NLP; NLP_NER --> DB_NLP
NLP_KWIC --> DB_MAIN; NLP_QML --> DB_NLP
NLP_VIZ_ENG --> DB_VIZ

' ══════════════════════════════════
'  SERVICIOS DE DATOS — PIPELINE DE SEGURIDAD DE ARCHIVOS
' ══════════════════════════════════
EXT_SRC --> DS_DOC
EXT_SRC --> DS_OCR            : "flujos de audio / video"
DS_DOC --> DS_MALWARE         : "todo archivo entra primero al escáner"
DS_MALWARE --> DS_FILE_SANIT  : "solo si resultado de malware es limpio"
DS_MALWARE --> DB_SEC_LOG     : "alerta inmediata ante detección positiva"
DS_FILE_SANIT --> DS_SEG      : "archivo limpio y sanitizado → segmentación"
DS_FILE_SANIT --> DS_ANON     : "archivo limpio → anonimización de PII"
DS_DOC --> DS_OCR; DS_DOC --> DS_IDX; DS_DOC --> DS_TOK
DS_SEG --> DS_RAG; DS_SEG --> DS_GRAG
DS_RAG --> DB_VEC; DS_GRAG --> DB_GRAPH
DS_IDX --> DB_MAIN; DS_DOC --> DB_MAIN; DS_SEG --> DB_MAIN
MEMO_SVC --> DB_MEMO; DIFF_REC --> DB_HIST
AG_GAP --> DB_SORT; REP_SVC --> DB_REP

' ══════════════════════════════════
'  INFRAESTRUCTURA DE BD — CONEXIONES
' ══════════════════════════════════
PGBOUNCER --> DB_MAIN         : "pool de conexiones hacia PostgreSQL principal"
PGBOUNCER --> DB_VEC          : "pool de conexiones hacia pgvector"

' ══════════════════════════════════
'  WORKERS ASÍNCRONOS — CONEXIONES
' ══════════════════════════════════
CELERY_APP --> DOC_TASKS
DOC_TASKS --> TASK_IDEM       : "registra task_id antes de ejecutar"
TASK_IDEM --> DB_TASK_IDEM    : "persiste y consulta idempotencia de tareas"
CELERY_APP --> NOTIFY
NOTIFY --> EBUS               : "push a WebSocket vía Event Bus"

' ══════════════════════════════════
'  SERVICIO DE BIBLIOGRAFÍA
' ══════════════════════════════════
DS_RAG  --> BIB_IDX; BIB_IDX --> BIB_SEARCH; BIB_SEARCH --> BIB_MGR
AG_SYN  --> BIB_SEARCH
UI_WORKSHOP --> BIB_SEARCH    : "consulta RAG (fases 5a · 6c)"
ORCH --> BIB_IDX              : "inyección de bibliografía Fase 0.3"
BIB_IDX --> DB_BIB; BIB_IDX --> DB_VEC

' ══════════════════════════════════
'  IU → RUTAS DE LECTURA DE BACKEND
' ══════════════════════════════════
UI_VIZ  --> NLP_VIZ_ENG; UI_VIZ --> DB_VIZ
UI_WRITE --> REP_SVC
UI_LEXICO --> DB_NLP; UI_LEXICO --> NLP_KWIC
UI_AUDIT --> DB_HIST          : "leer rastro de auditoría"
UI_AUDIT --> DB_MAIN          : "leer historial de cambios"
UI_AUDIT --> DB_MEMO          : "todos los memos (rol auditor)"
UI_AUDIT --> DB_EXEC_LOG      : "trazabilidad de ejecuciones IA [v6]"

' ══════════════════════════════════
'  CONEXIONES EXTERNAS RESTANTES
' ══════════════════════════════════
N8N --> ORCH                  : "disparadores de fase · webhooks · lotes"

@enduml
```
