# Deployment



```
@startuml
!include https://raw.githubusercontent.com/plantuml-stdlib/C4-PlantUML/master/C4_Deployment.puml

title IQAS v5 - Despliegue de Producción (Microservicio de Embeddings Aislado)

' ==================== EXTERNO / NUBE PÚBLICA ====================
Deployment_Node(cloudflare, "Cloudflare CDN", "Red global de borde") {
    Container(cdn_proxy, "Proxy Inverso / WAF", "Terminación SSL, WebSocket Support")
}

Deployment_Node(external_services, "Servicios Cloud Externos", "APIs de Terceros") {
    System_Ext(llm_apis, "Proveedores LLM", "DeepSeek, Gemma 31B, GLM-5V, Nemotron")
    System_Ext(cms_api, "CMS Headless & Registro", "Strapi / Contentful")
}

' ==================== INFRAESTRUCTURA PROPIA (VPS) ====================
Deployment_Node(vps_frontend, "VPS1 - Frontend (2 vCPU, 2GB RAM)", "Nginx") {
    Container(nginx, "Nginx Reverse Proxy", "Balanceador y servidor de estáticos")
    Container(static_files, "Rsbuild SPA", "Archivos estáticos UI")
}

Deployment_Node(vps_api, "VPS2 - Core API & Collab (8 vCPU, 16GB)", "FastAPI + Node.js") {
    Container(api, "FastAPI (Orquestador Principal)", "Uvicorn --workers 4", "Endpoints REST, Auth")
    Container(collab, "Hocuspocus (Node.js)", "Yjs server", "WebSocket (Lienzo y Memos en vivo)")
    Container(guidance, "Servicio Orientación", "Python", "Observador de eventos y Tooltips")
}

Deployment_Node(vps_workers, "VPS3 - AI Layer & Workers (8 vCPU, 24GB+)", "Celery + LangGraph + TEI") {
    Container(ai_layer, "LangGraph / AI-Q (drb2)", "Python", "Gestor CWD, Enrutador, Agente Crítico")
    Container(worker_nlp, "Celery Worker (Rápido)", "Python", "RAG, Extracción Atómica")
    Container(worker_heavy, "Celery Worker (Pesado)", "Python", "OCR, Tareas Deep Research")
    Container(redis, "Redis 7.x", "Broker, Pub/Sub, Caché", "Sincroniza Hocuspocus y Celery")
    
    ' [NUEVO] El microservicio aislado asume el control absoluto de la RAM de los modelos
    Container(tei_service, "API Embeddings (TEI/Infinity)", "Microservicio Docker", "Carga F2LLM-v2 en RAM UNA vez. Expone puerto interno 8080 para batching dinámico.")
}

Deployment_Node(vps_db, "VPS4 - Base de Datos (8 vCPU, 16GB NVMe)", "PostgreSQL 16") {
    Container(db_primary, "PostgreSQL + pgvector", "Escritura/Lectura crítica", "Estado CWD y Vectores")
    Container(db_replica, "Réplica Síncrona", "Lectura", "Reportes")
}

Deployment_Node(vps_storage, "VPS5 - Almacenamiento (4 vCPU, 8GB)", "MinIO + ClamAV") {
    Container(minio, "MinIO", "S3-compatible", "Documentos PDF/Imágenes")
    Container(clamav, "ClamAV", "Antivirus", "Escaneo previo")
}

' ==================== CONEXIONES ====================
Boundary(internet, "Internet") {
    Actor_Ext(usuario, "Investigadores (Colaboradores)", "Navegador Web")
}

Rel(usuario, cloudflare, "HTTPS / WSS")
Rel(cloudflare, nginx, "HTTPS / WSS")

Rel(nginx, api, "Proxy /api/*")
Rel(nginx, collab, "Proxy /collab/* (WSS)")

Rel(api, redis, "Encola tareas / PubSub")
Rel(collab, redis, "Sincroniza Yjs vía PubSub")
Rel(collab, db_primary, "Persistencia CRDT (Memos)")

Rel(redis, ai_layer, "Desencola intenciones metodológicas")
Rel(redis, worker_nlp, "Desencola tareas")
Rel(redis, worker_heavy, "Desencola tareas")

' [ACTUALIZADO] Las llamadas ahora son locales por HTTP, no por memoria RAM compartida
Rel(ai_layer, tei_service, "Solicita vectores contexto", "HTTP (localhost:8080)")
Rel(worker_nlp, tei_service, "Genera embeddings en lote", "HTTP (localhost:8080)")

Rel(ai_layer, llm_apis, "Inferencia Dinámica (Factory)", "HTTPS")
Rel(guidance, cms_api, "Consulta tooltips/plantillas", "HTTPS")

Rel(worker_nlp, db_primary, "Lee/Escribe SQL y Vectores")
Rel(worker_heavy, minio, "Lee imágenes/PDF para OCR")
Rel(api, minio, "Sube documentos")
Rel(api, clamav, "Escaneo TCP")

@enduml
```

![](assets/3YLuL1rFhJVoCWPx2uweZKGeEO9tuA3j9Wk7bZcGg2w=.png)
