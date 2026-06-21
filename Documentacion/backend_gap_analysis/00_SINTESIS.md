# 🚨 Backend ↔ Frontend Gap Analysis — Informe de Síntesis

> **Metodología**: Auditoría estructurada de flujos de datos  
> **Alcance**: 46 tablas DB, 117 endpoints API, ~90 agentes, 4166 líneas de frontend  
> **Fecha**: 2026-06-21  
> **Sub-análisis**: [DB Schema](db_schema_analysis.md) | [API Endpoints](api_endpoints_analysis.md) | [Agent Data](agent_data_production_analysis.md) | [Frontend Consumption](frontend_data_consumption.md)  
> **Diagramas**: [`diagrams/`](diagrams/)

---

## 📊 Executive Summary

| Métrica | Valor |
|----------|-------|
| **Tablas en la base de datos** | 46 |
| **Endpoints API documentados** | 117 |
| **Endpoints consumidos por el frontend** | 58 (50%) |
| **Endpoints sin consumidor frontend** | 55 (47%) |
| **Funciones `client.ts` sin uso** | 19 |
| **Agentes en el pipeline** | ~90 |
| **Prompt templates** | ~30 archivos `.md` |
| **Desperdicio de datos promedio por response** | ~45% |
| **Interfaces TS con 100% de campos desperdiciados** | 4 (PipelineStatus, EcosystemLayout, TheoreticalCode[], ModelSummary) |

---

## 🔥 10 Gaps Identificados (ordenados por severidad)

### GAP-1 🔴 CRÍTICO — Categorías invisibles en Project.tsx
**El problema**: `listCategories(id)` devuelve 6 campos por categoría (nombre, definicion, estado_saturacion, es_central, etc.) pero en `Project.tsx` **solo se usa `cats.length`** para mostrarlo en el badge del navbar. El 83% de los datos de categorías se descargan y se ignoran.

**Impacto**: El usuario no puede ver qué categorías se han generado sin ir al playground. Si el pipeline produce 50 categorías pero solo 3 son centrales, el usuario no lo sabe hasta que abre el playground.

**Recomendación**: Añadir una sección "Categorías" colapsable en la sidebar del pipeline o en el área principal que liste nombres + badges de estado de saturación.

---

### GAP-2 🔴 HIGH — DocPipelineLog.steps completamente ignorado
**El problema**: `getPipelineLog()` devuelve, por cada documento, 6 booleanos (`text_extracted`, `punctuation_fixed`, `segmented`, `coded`, `agents_done`, `synthesis_done`) más `codes_count`. **Ninguno de estos 7 campos se renderiza** en ninguna parte del frontend. Esto representa el **75% de desperdicio** en `DocPipelineLog`, multiplicado por N documentos en cada refresh del pipeline log.

**Impacto**: Transferencia de datos innecesaria en cada poll del pipeline. Si hay 100 documentos, son 700 campos booleanos + numéricos descargados y descartados cada 5 segundos durante la ejecución del pipeline.

**Recomendación**:
- **Opción A**: Añadir indicadores de progreso por paso en cada documento expandido (mini checkmarks: ✂️ segmentado, 🏷️ codificado, etc.)
- **Opción B**: Eliminar `steps.*` y `codes_count` del endpoint `pipeline/log` si no se van a usar (optimización de backend)

---

### GAP-3 🔴 HIGH — Persistencia de layout del ecosistema no implementada
**El problema**: El backend soporta `GET/PUT /elaboration/ecosystem/layout` con `blob_positions`, `ghost_positions`, `fog_zones`, y `physics_params`. `getEcosystem()` incluye este layout en la respuesta. Pero el frontend:
1. **Ignora completamente** los datos de layout recibidos
2. **Recalcula posiciones** cada vez que se monta el canvas (client-side force layout)
3. **Nunca llama** a `saveEcosystemLayout()` para persistir las posiciones que el usuario ajusta con drag & drop

**Impacto**: El usuario pierde todo el layout manual cada vez que recarga la página del playground.

**Recomendación**:
1. En `PlaygroundContext.refreshEcosystem()`: si `eco.layout.blob_positions` existe, usarlo como posición inicial
2. En `EcosystemCanvas`: al terminar un drag (onDragEnd), llamar a `saveEcosystemLayout()` con las nuevas posiciones

---

### GAP-4 🔴 HIGH — TheoreticalCode[] es un round-trip muerto
**El problema**: `PlaygroundContext.refreshEcosystem()` hace `getTheoreticalCodes(projectId)` y guarda el resultado en `pg.theoreticalCodes`. Pero **ningún componente en todo el frontend lee este estado**. Es un array de objetos que se descarga, se almacena en memoria, y se descarta en el siguiente refresh.

**Impacto**: Cada refresh del ecosistema incluye una llamada HTTP + transferencia de datos que no sirve para nada.

**Recomendación**:
- **Opción A**: Crear un componente `TheoreticalCodesPanel` en el playground que muestre los códigos teóricos disponibles
- **Opción B**: Eliminar `getTheoreticalCodes()` del refresh del ecosistema hasta que haya UI

---

### GAP-5 🟠 MEDIUM — Detalles de segmentos ignorados
**El problema**: Los segmentos tienen `parafrasis`, `posicion`, `conteo_tokens`, y `es_anomalia` — pero el frontend solo muestra `texto`. El 71% de los campos de `Segment` nunca se renderizan.

**Impacto**: Oportunidad perdida de mostrar información útil (paráfrasis ayuda a entender el significado; `es_anomalia` podría señalar outliers importantes).

**Recomendación**: Añadir tooltip o expand en la vista de segmentos mostrando paráfrasis y flag de anomalía. Mostrar `[posicion]` como prefijo en el textarea de segmentos (ya se hace parcialmente: `[${s.posicion}] ${s.texto}` en L2962).

---

### GAP-6 🟠 MEDIUM — saturation-gaps + theoretical-model sin consumir
**El problema**: El backend tiene `GET /analysis/saturation-gaps` y `GET /elaboration/model` listos, con datos de gaps de saturación y resumen del modelo teórico. Pero el frontend **nunca llama** a `getSaturationGaps()` ni a `getTheoreticalModel()`.

**Impacto**: Dos paneles de análisis que el backend ya calcula y que aportarían valor al investigador no tienen UI.

**Recomendación**: Añadir componentes `SaturationPanel` y `ModelSummaryCard` al playground, consumiendo estos endpoints.

---

### GAP-7 🟠 MEDIUM — Relación detail descartada
**El problema**: `RelationshipTendril.tsx` (L47) hace `const detail = await getRelationship(rel.id)` al hacer click, pero **descarta el resultado**. La llamada HTTP se ejecuta pero los datos nunca se usan.

**Impacto**: Llamada HTTP innecesaria en cada click sobre un tendril.

**Recomendación**: Usar el resultado para mostrar un modal/popover con detalles de la relación (status, fit, layer, tension, elaboration_history).

---

### GAP-8 🟡 LOW — 55 endpoints backend sin consumidor frontend
**El problema**: De 117 endpoints API, 55 (47%) no tienen un consumidor conocido en el frontend. Algunos son infraestructura (auth, workers), pero muchos son funcionalidad completa que nunca se expuso en la UI:
- **RAG search** (`/rag/search`, `/rag/context/{code_id}`)
- **Hypothesis CRUD** completo (list, accept, modify, reject, split)
- **Population context standalone** (get, versions)
- **Coding styles** (list, set)
- **Research question** (preview standalone, preview project, update, get)
- **Modification flow** (P5: request + apply)
- **Individual memo CRUD** (patch, delete)
- **Individual theoretical code CRUD** (get, update)
- **Document download + presigned URL**
- **SSE event stream**
- **Config global** (system-wide, no project)

**Recomendación**: Auditoría de endpoints:
1. Marcar como `@deprecated` los que son dead code real
2. Priorizar implementación de UI para: RAG search, hypothesis review, research question

---

### GAP-9 🟡 LOW — 19 funciones client.ts sin uso
**El problema**: Funciones definidas en `client.ts` pero nunca llamadas desde ningún componente:

| Función | Probable razón |
|---------|---------------|
| `createCategory` | Categorías se crean por agentes, no manualmente |
| `segmentDocument` | Segmentación va por pipeline, no individual |
| `saveTaskSegments` | Endpoint interno de workers |
| `processDocument` | Reemplazado por pipeline orchestrator |
| `getPipelineStatus` | Reemplazado por `getPipelineLog` |
| `stopWorker` | No expuesto en UI |
| `killAllWorkers` | No expuesto en UI |
| `cancelTask` | Solo usado vía `fetch` directo en punctuate |
| `restartTask`, `resumeTask` | No expuesto en UI |
| `createTheoreticalCode` | No implementado en UI |
| `saveEcosystemLayout` | Layout no persistido (GAP-3) |
| `resolveDivergence` | No implementado en UI |
| `absorbGhost` | No implementado en UI |
| `getTheoreticalModel` | No implementado en UI (GAP-6) |
| `getSaturationGaps` | No implementado en UI (GAP-6) |
| `refreshSaturationGaps` | No implementado en UI (GAP-6) |
| `previewResearchQuestion` | No implementado en UI |
| `getPresignedUrl` | No implementado en UI |
| `restartFailedTasks` | Importado en Project.tsx pero nunca invocado |

**Recomendación**: Limpiar `client.ts` eliminando las 19 funciones no usadas (o comentarlas con `// TODO: planned for v2`).

---

### GAP-10 🟡 INFO — Interfaces TypeScript sobre-declaradas
**El problema**: Varias interfaces TS incluyen campos que el backend envía pero el frontend nunca consume:

| Interfaz | Campos fantasma |
|----------|----------------|
| `Project` | `config_segmentacion`, `coding_style_instruction`, `config_mutation_policy` (pertenecen a `ProjectConfig`, no a `Project`) |
| `Document` | `proyecto_id`, `tipo_de_fuente`, `size_bytes`, `creado_en` |
| `PipelineLog.summary` | `sintetizados` (declarado, nunca leído) |

**Recomendación**: Refactorizar interfaces:
- `BaseProject` (campos core) + `ProjectDetail` (con counts) + `ProjectConfig` (config fields)
- Eliminar `sintetizados` de `PipelineLog` si no se usa

---

## 📈 Plan de Acción — Priorizado por Impacto/Esfuerzo

### Fase 1: Quick Wins (1-2 semanas, bajo esfuerzo, alto impacto)

| # | Acción | Archivos | Esfuerzo |
|---|--------|----------|----------|
| 1 | **Eliminar 19 funciones unused de `client.ts`** | `api/client.ts` | 30 min |
| 2 | **Eliminar `sintetizados` de `PipelineLog` interface** | `api/client.ts` | 5 min |
| 3 | **Eliminar `steps.*` de `DocPipelineLog` o marcar como opcional** | `api/client.ts` + backend `pipeline.py` | 1h |
| 4 | **Eliminar `getTheoreticalCodes()` del refresh del ecosistema** | `PlaygroundContext.tsx` | 15 min |
| 5 | **Separar `config_segmentacion`, `coding_style_instruction`, `config_mutation_policy` de `Project`** | `api/client.ts` | 30 min |
| 6 | **Fix: usar `detail` en `RelationshipTendril.tsx` en vez de descartarlo** | `RelationshipTendril.tsx` | 1h |

### Fase 2: Valor Visible (2-4 semanas, esfuerzo medio, alto impacto)

| # | Acción | Archivos | Esfuerzo |
|---|--------|----------|----------|
| 7 | **Añadir lista de categorías en sidebar de Project.tsx** (nombre + badge saturación) | `Project.tsx` | 4h |
| 8 | **Implementar persistencia de layout del ecosistema** (cargar posiciones + guardar en drag-end) | `PlaygroundContext.tsx`, `EcosystemCanvas.tsx` | 4h |
| 9 | **Añadir indicadores de progreso por paso en documentos** (mini checkmarks) | `Project.tsx` | 3h |
| 10 | **Añadir tooltip de segmento** (paráfrasis + flag anomalía) | `Project.tsx` | 2h |
| 11 | **Implementar `TheoreticalCodesPanel` en playground** | Nuevo componente + `Playground.tsx` | 6h |

### Fase 3: Features Nuevas (4-8 semanas, esfuerzo alto, alto valor)

| # | Acción | Archivos | Esfuerzo |
|---|--------|----------|----------|
| 12 | **Implementar `SaturationPanel`** (consumir `getSaturationGaps`) | Nuevo componente + `Playground.tsx` | 8h |
| 13 | **Implementar `ModelSummaryCard`** (consumir `getTheoreticalModel`) | Nuevo componente + `Playground.tsx` | 6h |
| 14 | **Implementar panel de hypotheses** (listar + accept/reject) | Nuevo componente + `Project.tsx` o `Playground.tsx` | 12h |
| 15 | **Implementar RAG search UI** (búsqueda semántica de segmentos) | Nuevo componente | 16h |
| 16 | **Implementar Research Question panel** (preview + save en ProjectConfigPanel) | `ProjectConfigPanel.tsx` | 8h |
| 17 | **Implementar Modal de detalle de relación** (usar `getRelationship` descartado) | `RelationshipTendril.tsx` + nuevo modal | 6h |

### Fase 4: Refactoring Estructural (8-12 semanas)

| # | Acción | Descripción |
|---|--------|-------------|
| 18 | **Descomponer `Project.tsx` (4166 líneas)** | Extraer hooks: `useProjectData`, `usePipeline`, `useDocuments`, `useAgentMonitoring`, `useHITL`, `useMemoHistory` |
| 19 | **Migrar estilos inline a CSS Modules o Tailwind** | Los ~200 objetos `style={...}` inline hacen el código muy denso |
| 20 | **Auditar y deprecar endpoints backend no utilizados** | 55 endpoints sin consumidor → decidir cuáles mantener, cuáles eliminar |
| 21 | **Lazy-load de datos de configuración** | `ProjectConfig` no debería venir en `GET /projects/{id}` |
| 22 | **Normalizar nomenclatura** | `supuesto_poblacional` vs `population_assumption.population_description` — unificar |

---

## 📁 Archivos Entregables

```
Documentacion/backend_gap_analysis/
├── 00_SINTESIS.md                          ← Este archivo
├── db_schema_analysis.md                   ← Catálogo completo de 46 tablas
├── api_endpoints_analysis.md               ← 117 endpoints documentados
├── agent_data_production_analysis.md       ← ~90 agentes + servicios
├── frontend_data_consumption.md            ← Auditoría de consumo de datos
└── diagrams/
    ├── 01_db_schema_er.mermaid             ← Diagrama ER completo
    ├── 02_pipeline_data_production.mermaid ← Flujo de datos por etapa
    ├── 03_frontend_consumption.mermaid     ← Qué se renderiza vs ignora
    ├── 04_gap_cross_reference.mermaid      ← Matriz de gaps DB→API→UI
    ├── 05_api_endpoint_map.mermaid         ← Mapa de 117 endpoints
    └── 06_data_waste_heatmap.mermaid       ← Heatmap de desperdicio
```

---

## 🏁 Conclusión

El sistema GT tiene una **arquitectura backend muy completa** (46 tablas, 117 endpoints, ~90 agentes con prompts detallados) pero el **frontend solo consume ~50% de la capacidad del backend**. El 47% de los endpoints no tienen consumidor frontend, y aproximadamente el **45% de los datos transferidos en cada respuesta HTTP nunca se renderizan**.

Las brechas más críticas son:
1. **Categorías invisibles** en la página principal del proyecto
2. **75% de desperdicio** en `DocPipelineLog` por campo
3. **Layout del ecosistema no persistido** — el usuario pierde su trabajo
4. **TheoreticalCode[] es un round-trip muerto** completo

El plan de acción propuesto prioriza **quick wins de bajo esfuerzo** (Fase 1: ~4h total) seguido de **features de alto valor visible** (Fase 2-3) y **refactoring estructural** a largo plazo (Fase 4).
