# GT System — Complete API Endpoint Analysis

> Generated from reading 17 route files and `main.py` router registration.
> Total endpoints documented: **117**

---

## Section 1: Complete Endpoint Catalog

### 1. Projects (`projects.py`) — prefix `/api/v1/projects`, tag `projects`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/projects` | `list_projects` | ✅ `get_current_user` |
| 2 | `POST` | `/api/v1/projects` | `create_project` | ✅ `get_current_user` |
| 3 | `GET` | `/api/v1/projects/{project_id}` | `get_project` | ✅ |
| 4 | `PUT` | `/api/v1/projects/{project_id}` | `update_project` | ✅ |
| 5 | `DELETE` | `/api/v1/projects/{project_id}` | `delete_project` | ✅ |
| 6 | `DELETE` | `/api/v1/projects/{project_id}/documents` | `delete_all_documents` | ✅ |
| 7 | `PUT` | `/api/v1/projects/{project_id}/config/population-assumption` | `update_population_assumption` | ✅ |
| 8 | `POST` | `/api/v1/projects/{project_id}/config/population-assumption/generalize` | `generalize_population` | ✅ |
| 9 | `POST` | `/api/v1/projects/research-question/preview` | `preview_research_question_standalone` | ❌ *no auth* |
| 10 | `POST` | `/api/v1/projects/{project_id}/research-question/preview` | `preview_research_question` | ✅ |
| 11 | `PUT` | `/api/v1/projects/{project_id}/research-question` | `update_research_question` | ✅ |
| 12 | `GET` | `/api/v1/projects/{project_id}/research-question` | `get_research_question` | ✅ |
| 13 | `GET` | `/api/v1/projects/{project_id}/config` | `get_project_config` | ✅ |
| 14 | `GET` | `/api/v1/projects/{project_id}/config/history` | `get_project_config_history` | ✅ |
| 15 | `PUT` | `/api/v1/projects/{project_id}/config/mutation-policy` | `update_mutation_policy` | ✅ |

#### Endpoint Details

---

**1. `GET /api/v1/projects`**

- **Path params**: none
- **Query params**: none
- **Request body**: none
- **Response**: `list[ProjectResponse]` — list of `Proyecto` model fields serialized via factory
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (WHERE creador_id = current_user.id)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**2. `POST /api/v1/projects`**

- **Path params**: none
- **Query params**: none
- **Request body**: `ProjectCreate` (factory-generated from `Proyecto` model, + optional `custom_label: str | None`)
  - Fields from `Proyecto` columns (excludes `estado`, `creador_id`)
  - Extra: `custom_label` (for spaCy validation when object_of_study="custom")
- **Response**: `ProjectResponse`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (for validation)
- **DB tables written**: `proyectos` (INSERT), `population_assumption` JSONB
- **Services**: spaCy validation for custom labels
- **Status codes**: 201, 400 (invalid object_of_study)

---

**3. `GET /api/v1/projects/{project_id}`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `ProjectResponse` (merged with `num_documentos`, `num_categorias` counts)
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`, `documentos` (COUNT), `categorias` (COUNT)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**4. `PUT /api/v1/projects/{project_id}`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — updatable keys: `nombre`, `supuesto_poblacional`, `object_of_study`, `custom_label`, `processing_verb`, `processing_gerund`
- **Response**: `{status, id, nombre, estado, object_of_study, supuesto_poblacional, population_assumption}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`
- **DB tables written**: `proyectos` (UPDATE), `population_assumption` JSONB
- **Services**: spaCy custom_label validation, optional pipeline state reset
- **Status codes**: 200, 400, 404

---

**5. `DELETE /api/v1/projects/{project_id}`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "deleted", nombre, id}`
- **Auth**: `get_current_user` + ownership check
- **DB tables read**: `proyectos`
- **DB tables written**: `proyectos` (DELETE, cascading)
- **Services**: none
- **Status codes**: 200, 403, 404

---

**6. `DELETE /api/v1/projects/{project_id}/documents`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "deleted", count, project_id}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos` (COUNT)
- **DB tables written**: `codigos_segmento`, `segmentos`, `documentos` (DELETE); `proyectos` (estado → "collecting")
- **Services**: none
- **Status codes**: 200, 404

---

**7. `PUT /api/v1/projects/{project_id}/config/population-assumption`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — allowed keys: `object_of_study`, `temporal_frame`, `spatial_frame`, `population_description`, `gerundio_esperado`, `custom_label`
- **Response**: `{status: "updated", population_assumption, supuesto_poblacional}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`
- **DB tables written**: `proyectos` (population_assumption JSONB), `project_config_history` (INSERT via `_record_config_change`)
- **Services**: spaCy validation, config history recording
- **Status codes**: 200, 400, 404

---

**8. `POST /api/v1/projects/{project_id}/config/population-assumption/generalize`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "generalized", population_assumption, supuesto_poblacional}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`
- **DB tables written**: `proyectos` (population_assumption JSONB)
- **Services**: TogetherLLM (FLASH model), `f0_population_generalizer` prompt, JSON parsing
- **Status codes**: 200, 400, 404, 500

---

**9. `POST /api/v1/projects/research-question/preview`**

- **Path params**: none
- **Query params**: none
- **Request body**: `dict` — `{population, object_of_study, processing_verb, custom_label?}`
- **Response**: `{research_question, operational_question, oq_discovery, oq_selective, oq_theoretical, population_number, conjugated_verb, language}`
- **Auth**: ❌ **None** (standalone, no-project/no-auth)
- **DB tables read**: none
- **DB tables written**: none
- **Services**: spaCy conjugation, pattern language resolution
- **Status codes**: 200, 400

---

**10. `POST /api/v1/projects/{project_id}/research-question/preview`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — same as #9
- **Response**: `{project_id, research_question, operational_question, oq_discovery, oq_selective, oq_theoretical, pronoun, conjugated_verb, language, ...}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: none
- **Services**: spaCy conjugation, pattern language resolution
- **Status codes**: 200, 400

---

**11. `PUT /api/v1/projects/{project_id}/research-question`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — `{research_question?, operational_question?}`
- **Response**: `{project_id, research_question, operational_question}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`
- **DB tables written**: `proyectos` (population_assumption JSONB)
- **Services**: none
- **Status codes**: 200, 404

---

**12. `GET /api/v1/projects/{project_id}/research-question`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{project_id, research_question?, operational_question?, rationale?, key_dimensions?, generated_at?, message?}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (population_assumption JSONB)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**13. `GET /api/v1/projects/{project_id}/config`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{project_id, nombre, estado, ruta_de_codificacion, supuesto_poblacional, object_of_study, population_assumption, coding_style_instruction, config_segmentacion, mutation_policy, pending_suggestions}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`, `project_config_history` (pending suggestions)
- **DB tables written**: none
- **Services**: `_get_pending_suggestions()`
- **Status codes**: 200, 404

---

**14. `GET /api/v1/projects/{project_id}/config/history`**

- **Path params**: `project_id: UUID`
- **Query params**:
  - `field: str | None` — filter by specific config field
  - `limit: int` = 50 (range 1-200)
- **Request body**: none
- **Response**: `{project_id, total, entries: [{id, field, old_value, new_value, triggered_by, agent_run_id, mutation_level, rationale, confidence, context, timestamp}]}`
- **Auth**: `get_current_user`
- **DB tables read**: `project_config_history`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**15. `PUT /api/v1/projects/{project_id}/config/mutation-policy`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — e.g. `{"population_description": "auto", "object_of_study": "require_approval"}`
  - Valid keys from `DEFAULT_MUTATION_POLICY`
  - Valid levels: `auto`, `suggest`, `require_approval`, `locked`
- **Response**: `{status: "updated", message, mutation_policy}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos`
- **DB tables written**: `proyectos` (config_mutation_policy JSONB), `project_config_history` (INSERT)
- **Services**: `_record_config_change()`
- **Status codes**: 200, 404

---

### 2. Documents (`documents.py`) — prefix `/api/v1/documents`, tag `documents`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `POST` | `/api/v1/documents/upload/{project_id}` | `upload_document` | ✅ |
| 2 | `GET` | `/api/v1/documents/download/{document_id}` | `download_document` | ✅ |
| 3 | `GET` | `/api/v1/documents/presigned/{document_id}` | `get_presigned_url` | ✅ |
| 4 | `POST` | `/api/v1/documents/{document_id}/segment` | `segment_document` | ✅ |
| 5 | `GET` | `/api/v1/documents` | `list_documents` | ✅ |
| 6 | `GET` | `/api/v1/documents/tasks/{task_id}` | `get_task_status` | ❌ |
| 7 | `POST` | `/api/v1/documents/{document_id}/segments-from-task` | `save_task_segments` | ✅ |
| 8 | `POST` | `/api/v1/documents/{document_id}/punctuate` | `punctuate_document` | ✅ |
| 9 | `POST` | `/api/v1/documents/{document_id}/process` | `process_document` | ✅ |
| 10 | `POST` | `/api/v1/documents/{document_id}/undo-punctuate` | `undo_punctuate` | ✅ |
| 11 | `DELETE` | `/api/v1/documents/{document_id}` | `delete_document` | ✅ |
| 12 | `DELETE` | `/api/v1/documents/project/{project_id}/segments` | `delete_all_segments` | ✅ |
| 13 | `DELETE` | `/api/v1/documents/{document_id}/segments` | `delete_document_segments` | ✅ |
| 14 | `POST` | `/api/v1/documents/{document_id}/restore-original` | `restore_document_original` | ✅ |
| 15 | `POST` | `/api/v1/documents/project/{project_id}/reset-to-crudo` | `reset_all_docs_to_crudo` | ✅ |
| 16 | `POST` | `/api/v1/documents/project/{project_id}/reorder` | `reorder_documents` | ✅ |

#### Endpoint Details

---

**1. `POST /api/v1/documents/upload/{project_id}`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `UploadFile` (multipart file)
- **Response**: `{id, storage_key, filename, estado: "crudo", needs_punctuation}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `documentos` (INSERT with sort_order)
- **Services**: MinIO (upload), PyMuPDF/pdf extraction, python-docx/docx extraction, encoding detection
- **Status codes**: 200, 400 (bad MIME), 413 (file too large)
- **Allowed MIME types**: `application/pdf`, `text/plain`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- **Max size**: 50 MB

---

**2. `GET /api/v1/documents/download/{document_id}`**

- **Path params**: `document_id: int`
- **Query params**: none
- **Request body**: none
- **Response**: binary file (StreamingResponse with Content-Disposition)
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: none
- **Services**: MinIO (download)
- **Status codes**: 200, 404

---

**3. `GET /api/v1/documents/presigned/{document_id}`**

- **Path params**: `document_id: int`
- **Query params**: none
- **Request body**: none
- **Response**: `{url: string}` — presigned MinIO URL (10 min expiry)
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: none
- **Services**: MinIO (presigned URL generation)
- **Status codes**: 200, 404

---

**4. `POST /api/v1/documents/{document_id}/segment`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: 
  - `{status: "dispatched", task_id}` (progressive mode via Celery)
  - `{status: "done", num_segmentos}` (spaCy direct)
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`, `segmentos` (existing)
- **DB tables written**: `segmentos` (DELETE old, INSERT new)
- **Services**: spaCy (sentence segmentation), Celery (`segmentar_documento` task)
- **Status codes**: 200, 400, 404

---

**5. `GET /api/v1/documents`**

- **Path params**: none
- **Query params**: `proyecto_id: UUID` (required)
- **Request body**: none
- **Response**: list of `DocumentResponse` + extra fields (`texto_extraido`, `texto_preprocesado`, `texto_original`, `preprocess_warning`)
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**6. `GET /api/v1/documents/tasks/{task_id}`**

- **Path params**: `task_id: str`
- **Query params**: none
- **Request body**: none
- **Response**: `{task_id, status, result?}`
- **Auth**: ❌ **None**
- **DB tables read**: none
- **DB tables written**: none
- **Services**: Celery `AsyncResult`
- **Status codes**: 200

---

**7. `POST /api/v1/documents/{document_id}/segments-from-task`**

- **Path params**: `document_id: UUID`
- **Query params**: `task_id: str` (required)
- **Request body**: none
- **Response**: `{num_segmentos: int}`
- **Auth**: `get_current_user`
- **DB tables read**: `segmentos` (existing)
- **DB tables written**: `segmentos` (DELETE old, INSERT new)
- **Services**: Celery `AsyncResult`
- **Status codes**: 201, 400

---

**8. `POST /api/v1/documents/{document_id}/punctuate`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "dispatched", task_id}` or `{status: "ok", punctuation_fix: false, message}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: none
- **Services**: Celery (`punctuate_text` task on "fast" queue), `_needs_punctuation()` heuristic
- **Status codes**: 200, 400, 404

---

**9. `POST /api/v1/documents/{document_id}/process`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: `dict | None` — `{steps: ["punctuate", "segment", "agents"]}` (default: all 3)
- **Response**: `{document_id, steps: {step_name: {task_id/status}}}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: `documentos` (UPDATE estado)
- **Services**: Celery tasks on "fast", "nlp", "heavy" queues
- **Status codes**: 200, 400, 404

---

**10. `POST /api/v1/documents/{document_id}/undo-punctuate`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: `dict` — `{original_text: str}`
- **Response**: `{status: "restored"}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: `documentos` (UPDATE metadatos JSONB)
- **Services**: none
- **Status codes**: 200, 400, 404

---

**11. `DELETE /api/v1/documents/{document_id}`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: 204 No Content
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: `task_step_checkpoints`, `pipeline_tasks`, `extracted_incidents`, `codigos_segmento`, `segmentos` (DELETE), `documentos` (DELETE)
- **Services**: MinIO (delete file)
- **Status codes**: 204, 404

---

**12. `DELETE /api/v1/documents/project/{project_id}/segments`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "ok", message}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `extracted_incidents`, `codigos_segmento`, `segmentos` (DELETE), `documentos` (UPDATE estado → "crudo")
- **Services**: none
- **Status codes**: 200

---

**13. `DELETE /api/v1/documents/{document_id}/segments`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "ok", message}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `segmentos` (DELETE), `documentos` (UPDATE estado, metadatos)
- **Services**: none
- **Status codes**: 200

---

**14. `POST /api/v1/documents/{document_id}/restore-original`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "ok", message}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `documentos` (UPDATE estado, metadatos), `extracted_incidents`, `codigos_segmento`, `segmentos` (DELETE)
- **Services**: none
- **Status codes**: 200

---

**15. `POST /api/v1/documents/project/{project_id}/reset-to-crudo`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "ok", message}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `documentos` (UPDATE estado + metadatos)
- **Services**: none
- **Status codes**: 200

---

**16. `POST /api/v1/documents/project/{project_id}/reorder`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — `{order: [{id: str, sort_order: float}, ...]}`
- **Response**: `{status: "ok", count}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `documentos` (UPDATE sort_order)
- **Services**: none
- **Status codes**: 200, 400

---

### 3. Pipeline (`pipeline.py`) — prefix `/api/v1`, tag `pipeline`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `POST` | `/api/v1/projects/{project_id}/pipeline/run-stage/{stage_name}` | `run_pipeline_stage` | ✅ |
| 2 | `GET` | `/api/v1/projects/{project_id}/pipeline/log` | `get_pipeline_log` | ✅ |
| 3 | `GET` | `/api/v1/projects/{project_id}/pipeline/decisions` | `get_pipeline_decisions` | ✅ |
| 4 | `GET` | `/api/v1/projects/{project_id}/pipeline/status` | `get_pipeline_status` | ✅ |
| 5 | `POST` | `/api/v1/projects/{project_id}/pipeline/run` | `run_pipeline_orchestrated` | ✅ |
| 6 | `GET` | `/api/v1/projects/{project_id}/pipeline/tail` | `tail_pipeline_logs` | ❌ |
| 7 | `GET` | `/api/v1/projects/{project_id}/agent-logs` | `get_agent_logs` | ❌ |
| 8 | `GET` | `/api/v1/projects/{project_id}/agent-memos` | `get_agent_memos` | ✅ |
| 9 | `DELETE` | `/api/v1/agent-outputs/{memo_id}` | `delete_agent_output` | ✅ |
| 10 | `PATCH` | `/api/v1/agent-outputs/{memo_id}` | `patch_agent_output` | ✅ |
| 11 | `PATCH` | `/api/v1/documents/{document_id}/text` | `patch_document_text` | ✅ |
| 12 | `POST` | `/api/v1/projects/{project_id}/pipeline/run-agent/{agent_id}` | `run_single_agent` | ✅ |
| 13 | `PATCH` | `/api/v1/projects/{project_id}/pipeline/pause-config` | `update_pause_config` | ✅ |
| 14 | `PATCH` | `/api/v1/projects/{project_id}/pipeline/context-window` | `update_context_window` | ✅ |

#### Endpoint Details

---

**1. `POST /api/v1/projects/{project_id}/pipeline/run-stage/{stage_name}`**

- **Path params**: `project_id: UUID`, `stage_name: str`
  - Valid stages: `upload`, `precoding`, `open_coding`, `cross_doc`, `pattern_of_interest`, `selective`, `saturation`, `find_cc`, `reduce`, `saturate`, `build_db`, `playground`
- **Query params**: none
- **Request body**: none
- **Response**: `{stage, project_id, task_ids: [], status: "dispatched"|"checking"|"ready"}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: none (dispatches Celery tasks)
- **Services**: Celery tasks (`segmentar_documento`, `process_document_agents_a`, `process_synthesis_agents_b`, `selective_coding_coordinator`, `invoke_graph`)
- **Status codes**: 200, 400

---

**2. `GET /api/v1/projects/{project_id}/pipeline/log`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{project_id, documents: [{document_id, filename, estado, steps, segments_count, codes_count, next_action}], summary: {total, need_segment, need_agents, need_synthesis, sintetizados, done, failed, failed_tasks, errors, categories, project_state, playground_ready}}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`, `segmentos` (COUNT), `codigos_segmento` (COUNT), `categorias` (COUNT), `pipeline_tasks` + `pipeline_runs` (failed task count), `proyectos` (estado)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**3. `GET /api/v1/projects/{project_id}/pipeline/decisions`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{project_id, decisions: [{gate, proposal, critic_verdict, status, decision, note, decided_at}], saturation: {category: {no_expansion_count, saturated}}}`
- **Auth**: `get_current_user`
- **DB tables read**: `hitl_decisions`, `categorias` + `paradigm_states`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**4. `GET /api/v1/projects/{project_id}/pipeline/status`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{project_id, documents, segments, categories, hypotheses, stages: {upload, precoding, open_coding, cross_doc, pattern_of_interest, selective, saturation}}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`, `segmentos` (COUNT), `categorias` (COUNT), `hipotesis` (COUNT)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**5. `POST /api/v1/projects/{project_id}/pipeline/run`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict | None` — `{force: bool}`
- **Response**: `{status, message, ...}` (from PipelineOrchestrator)
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`, `segmentos` (COUNT), `codigos_segmento` (COUNT)
- **DB tables written**: none
- **Services**: Redis (clear pipeline_logs), PipelineOrchestrator (sync DB session)
- **Status codes**: 200

---

**6. `GET /api/v1/projects/{project_id}/pipeline/tail`**

- **Path params**: `project_id: UUID`
- **Query params**: `since: float` = 0 (timestamp filter)
- **Request body**: none
- **Response**: `{logs: [...], count}`
- **Auth**: ❌ **None**
- **DB tables read**: none
- **DB tables written**: none
- **Services**: Redis (LRANGE from `pipeline_logs:{project_id}`)
- **Status codes**: 200

---

**7. `GET /api/v1/projects/{project_id}/agent-logs`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: list of JSON agent prompt/response log entries
- **Auth**: ❌ **None**
- **DB tables read**: none
- **DB tables written**: none
- **Services**: Redis (LRANGE from `agent_logs:{project_id}`)
- **Status codes**: 200

---

**8. `GET /api/v1/projects/{project_id}/agent-memos`**

- **Path params**: `project_id: UUID`
- **Query params**: `include_intermediate: bool` = False
- **Request body**: none
- **Response**: `{memos: [...], total, families: [{key, label, icon, description}]}`
  - Memo types: A1 population contexts, A2 document processes, B2 categories
- **Auth**: `get_current_user`
- **DB tables read**: `agent_families`, `population_contexts`, `document_processes` + `documentos`, `categorias`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**9. `DELETE /api/v1/agent-outputs/{memo_id}`**

- **Path params**: `memo_id: str` — format `{prefix}-{uuid}` (e.g. `pc-xxx`, `dp-xxx`, `cat-xxx`)
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "deleted", id}`
- **Auth**: `get_current_user`
- **DB tables read**: `categorias` (source_memo_id lookup)
- **DB tables written**: `population_contexts` / `document_processes` / `categorias` (DELETE), `memos` (UPDATE estado)
- **Services**: none
- **Status codes**: 200, 400, 404

---

**10. `PATCH /api/v1/agent-outputs/{memo_id}`**

- **Path params**: `memo_id: str` — format `{prefix}-{uuid}`
- **Query params**: none
- **Request body**: `dict` — `{field: value, ...}` (allowed fields per prefix: pc: surprising_details/language_patterns/data_production_context; dp: process_description/similarity_to_previous/difference_from_previous/prime_mover; cat: nombre/definicion)
- **Response**: `{status: "updated", id}`
- **Auth**: `get_current_user`
- **DB tables read**: `categorias` (for sync)
- **DB tables written**: respective agent output table (UPDATE), `memos` (UPDATE on cat sync)
- **Services**: Memo↔Entity sync (P4)
- **Status codes**: 200, 400

---

**11. `PATCH /api/v1/documents/{document_id}/text`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: `dict` — `{texto_original?, texto_preprocesado?}`
- **Response**: `{status: "updated", id}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`
- **DB tables written**: `documentos` (UPDATE metadatos JSONB)
- **Services**: none
- **Status codes**: 200, 400, 404

---

**12. `POST /api/v1/projects/{project_id}/pipeline/run-agent/{agent_id}`**

- **Path params**: `project_id: UUID`, `agent_id: str`
- **Query params**: none
- **Request body**: `dict | None` — `{document_id: str}`
- **Response**: `{status: "dispatched", agent_id, task_id}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos` (if document_id provided)
- **DB tables written**: none
- **Services**: Celery tasks on "nlp" / "fast" / "heavy" queues
- **Status codes**: 200, 404

---

**13. `PATCH /api/v1/projects/{project_id}/pipeline/pause-config`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `PauseConfigRequest` — `{mode: "auto"|"manual"}`
- **Response**: `{status: "ok", pause_mode}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `proyectos` (UPDATE pause_mode)
- **Services**: none
- **Status codes**: 200, 400

---

**14. `PATCH /api/v1/projects/{project_id}/pipeline/context-window`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `ContextWindowRequest` — `{context_window_real: int}` (10,000–250,000)
- **Response**: `{status: "ok", context_window_real, model_max_context_tokens, effective_window, available_for_data}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (current context_window_real)
- **DB tables written**: `proyectos` (UPDATE context_window_real)
- **Services**: `context_config`
- **Status codes**: 200, 400, 404

---

### 4. Coding (`coding.py`) — prefix `/api/v1`, tag `coding`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/documents/{document_id}/segments` | `list_segments` | ✅ |
| 2 | `POST` | `/api/v1/categories` | `create_category` | ✅ |
| 3 | `GET` | `/api/v1/categories` | `list_categories` | ✅ |
| 4 | `POST` | `/api/v1/code-assignments` | `assign_code` | ✅ |
| 5 | `GET` | `/api/v1/segments/{segment_id}/recommendations` | `recommend_codes` | ✅ |

#### Endpoint Details

---

**1. `GET /api/v1/documents/{document_id}/segments`**

- **Path params**: `document_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `list[SegmentResponse]`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos`, `segmentos` (ordered by posicion)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**2. `POST /api/v1/categories`**

- **Path params**: none
- **Query params**: none
- **Request body**: `CategoryCreate` — factory-generated from `Categoria` model (excludes `embedding_centroide`, `estado_saturacion`, `puntaje_relevancia`, `version`)
- **Response**: `CategoryResponse`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `categorias` (INSERT)
- **Services**: none
- **Status codes**: 201

---

**3. `GET /api/v1/categories`**

- **Path params**: none
- **Query params**: `proyecto_id: UUID` (required)
- **Request body**: none
- **Response**: `list[enriched CategoryResponse]` — each with `segment_count` added
- **Auth**: `get_current_user`
- **DB tables read**: `categorias`, `codigos_segmento` (COUNT via raw SQL)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**4. `POST /api/v1/code-assignments`**

- **Path params**: none
- **Query params**: none
- **Request body**: `CodeAssignRequest` — factory-generated from `CodigoSegmento` model (fields: segmento_id, categoria_id, etc.)
- **Response**: `CodeAssignResponse`
- **Auth**: `get_current_user`
- **DB tables read**: `segmentos`, `categorias` (validation)
- **DB tables written**: `codigos_segmento` (INSERT)
- **Services**: none
- **Status codes**: 201, 404

---

**5. `GET /api/v1/segments/{segment_id}/recommendations`**

- **Path params**: `segment_id: UUID`
- **Query params**: `limit: int` = 5 (range 1-20)
- **Request body**: none
- **Response**: `list[RecommendationItem]` — `{categoria, score, definicion}`
- **Auth**: `get_current_user`
- **DB tables read**: `segmentos`, `documentos`, `categorias`
- **DB tables written**: none
- **Services**: `RAGService.search_similar_codes()` — HNSW embedding similarity
- **Status codes**: 200, 404

---

### 5. HITL (`hitl.py`) — prefix `/api/v1`, tag `hitl`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/projects/{project_id}/hitl/{gate_name}/detail` | `get_hitl_detail` | ✅ |
| 2 | `GET` | `/api/v1/projects/{project_id}/hitl/pending` | `get_pending_decisions` | ✅ |
| 3 | `POST` | `/api/v1/projects/{project_id}/hitl/{gate_name}/decide` | `decide_hitl` | ✅ |
| 4 | `POST` | `/api/v1/projects/{project_id}/hitl/reset` | `reset_hitl_decisions` | ✅ |
| 5 | `GET` | `/api/v1/projects/{project_id}/hitl/open-coding/status` | `get_open_coding_hitl_status` | ✅ |
| 6 | `POST` | `/api/v1/projects/{project_id}/hitl/open-coding/decide` | `decide_open_coding_hitl` | ✅ |

#### Endpoint Details

---

**1. `GET /api/v1/projects/{project_id}/hitl/{gate_name}/detail`**

- **Path params**: `project_id: UUID`, `gate_name: str`
- **Query params**: none
- **Request body**: none
- **Response**: `{id, gate_name, proposal, critic_verdict, status, created_at}` — full decision detail for modal
- **Auth**: `get_current_user`
- **DB tables read**: `hitl_decisions`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**2. `GET /api/v1/projects/{project_id}/hitl/pending`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `list[HitlPendingItem]` — `{id, gate_name, proposal_summary, critic_verdict, created_at}`
- **Auth**: `get_current_user`
- **DB tables read**: `hitl_decisions` (WHERE status='pending')
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**3. `POST /api/v1/projects/{project_id}/hitl/{gate_name}/decide`**

- **Path params**: `project_id: UUID`, `gate_name: str`
- **Query params**: none
- **Request body**: `HitlDecisionRequest` — `{decision: "accept"|"modify"|"reject", note: str, feedback: str|null}`
- **Response**: `HitlDecisionResponse` — `{id, project_id, gate_name, status, researcher_decision, researcher_note, decided_at}`
- **Auth**: `get_current_user`
- **DB tables read**: `hitl_decisions`
- **DB tables written**: `hitl_decisions` (UPDATE status, decision, note, feedback, decided_at)
- **Services**: Celery (`selective_coding_coordinator` re-dispatch on accept/modify)
- **Status codes**: 200, 404

---

**4. `POST /api/v1/projects/{project_id}/hitl/reset`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "ok"}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `hitl_decisions` (DELETE WHERE status='pending')
- **Services**: none
- **Status codes**: 200

---

**5. `GET /api/v1/projects/{project_id}/hitl/open-coding/status`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `OpenCodingHITLStatusResponse` — `{docs_processed, total_docs, batch_number, concern_candidates, population_proposals, unified_categories, unified_hypotheses, chosen_concern, chosen_population, can_proceed}`
- **Auth**: `get_current_user`
- **DB tables read**: `documentos` (COUNT), `proyectos` (batch_number/chosen_concern/chosen_population), `concerns`, `categorias` (supporting codes), `population_contexts`, `categorias`, `hypotheses` + `categorias`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**6. `POST /api/v1/projects/{project_id}/hitl/open-coding/decide`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `OpenCodingHITLDecision` — `{chosen_concern, chosen_population, core_category_ids: [], confirmed: bool, researcher_note}`
- **Response**: `{status: "confirmed"|"saved", chosen_concern, chosen_population, core_categories_set, confirmed}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (batch_number)
- **DB tables written**: `proyectos` (UPDATE chosen_concern/ chosen_population), `categorias` (UPDATE es_central/concern_label/population_label), `hitl_decisions` (INSERT)
- **Services**: Celery (`generalize_population` on "fast", `selective_coding_coordinator` on "heavy"), Redis (`publish_event` "hitl_resolved")
- **Status codes**: 200, 404

---

### 6. Memos (`memos.py`) — prefix `/api/v1`, tag `memos`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/projects/{project_id}/available-memo-types` | `get_available_memo_types` | ✅ |
| 2 | `POST` | `/api/v1/projects/{project_id}/memos` | `create_user_memo` | ✅ |
| 3 | `PATCH` | `/api/v1/projects/{project_id}/memos/{memo_id}` | `patch_user_memo` | ✅ |
| 4 | `DELETE` | `/api/v1/projects/{project_id}/memos/{memo_id}` | `delete_user_memo` | ✅ |
| 5 | `GET` | `/api/v1/projects/{project_id}/stale-user-entities` | `get_stale_user_entities` | ✅ |
| 6 | `GET` | `/api/v1/entity-type-colors` | `get_entity_type_colors` | ❌ |
| 7 | `DELETE` | `/api/v1/projects/{project_id}/memos` | `delete_memos_by_type` | ✅ |

#### Endpoint Details

---

**1. `GET /api/v1/projects/{project_id}/available-memo-types`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{stage, pipeline_running, can_add_memo, available_types, all_types}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (estado), `pipeline_runs` (active run check), `agent_loop_logs` (for two-level gating)
- **DB tables written**: none
- **Services**: `get_types_for_stage()`, `get_all_types()`
- **Status codes**: 200, 404

---

**2. `POST /api/v1/projects/{project_id}/memos`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `CreateMemoRequest` — `{tipo: str, contenido: str, es_confidencial: bool = false, structured_fields: dict|null}`
- **Response**: `{id, tipo, stage, user_created: true}`
- **Auth**: `get_current_user`
- **DB tables read**: `proyectos` (FOR UPDATE), `pipeline_runs` (FOR UPDATE)
- **DB tables written**: `memos` (INSERT), `categorias` (INSERT if CATEGORIA type), `theoretical_codes` (INSERT if TEORICO type)
- **Services**: Memo↔Entity side effects
- **Status codes**: 200, 400, 404, 409 (pipeline running)

---

**3. `PATCH /api/v1/projects/{project_id}/memos/{memo_id}`**

- **Path params**: `project_id: UUID`, `memo_id: UUID`
- **Query params**: none
- **Request body**: `PatchMemoRequest` — `{contenido?, es_confidencial?, tipo?}`
- **Response**: `{status: "updated", id}`
- **Auth**: `get_current_user`
- **DB tables read**: `memos` (FOR UPDATE), `proyectos` (estado)
- **DB tables written**: `memos` (UPDATE + version++), `categorias` (UPDATE sync), `theoretical_codes` (UPDATE sync)
- **Services**: Memo↔Entity sync (P4)
- **Status codes**: 200, 400, 404

---

**4. `DELETE /api/v1/projects/{project_id}/memos/{memo_id}`**

- **Path params**: `project_id: UUID`, `memo_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "deleted", id, orphaned_categorias, orphaned_theoretical_codes}`
- **Auth**: `get_current_user`
- **DB tables read**: `memos` (FOR UPDATE)
- **DB tables written**: `categorias` (UPDATE source_memo_id=NULL), `theoretical_codes` (UPDATE source_memo_id=NULL), `memos` (DELETE)
- **Services**: none
- **Status codes**: 200, 404

---

**5. `GET /api/v1/projects/{project_id}/stale-user-entities`**

- **Path params**: `project_id: UUID`
- **Query params**: `current_stage: str` (required)
- **Request body**: none
- **Response**: `{count, affected_stages, earliest_stage}`
- **Auth**: `get_current_user`
- **DB tables read**: `memos` (GROUP BY stage_at_creation)
- **DB tables written**: none
- **Services**: `STAGE_ORDER` from memo_types
- **Status codes**: 200

---

**6. `GET /api/v1/entity-type-colors`**

- **Path params**: none
- **Query params**: none
- **Request body**: none
- **Response**: `{types: [...]}` — all memo types with colors and metadata
- **Auth**: ❌ **None**
- **DB tables read**: none
- **DB tables written**: none
- **Services**: `get_all_types()`
- **Status codes**: 200

---

**7. `DELETE /api/v1/projects/{project_id}/memos`**

- **Path params**: `project_id: UUID`
- **Query params**: `tipo: str` = "all" — specific type or "all"
- **Request body**: none
- **Response**: `{deleted: int, tipo}`
- **Auth**: `get_current_user`
- **DB tables read**: `pipeline_runs` (active run check), `memos` (COUNT)
- **DB tables written**: `categorias` (DELETE by source_memo_id), `theoretical_codes` (DELETE by source_memo_id or name pattern), `memos` (DELETE)
- **Services**: none
- **Status codes**: 200, 409 (pipeline running)

---

### 7. Admin (`admin.py`) — prefix `/api/v1/admin`, tag `admin`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `POST` | `/api/v1/admin/workers/{worker_name}/stop` | `stop_worker` | ❌ |
| 2 | `GET` | `/api/v1/admin/workers/status` | `worker_status` | ❌ |
| 3 | `POST` | `/api/v1/admin/workers/kill-all` | `kill_all_workers` | ✅ |
| 4 | `POST` | `/api/v1/admin/projects/{project_id}/stop` | `stop_project_pipeline` | ✅ |
| 5 | `POST` | `/api/v1/admin/tasks/{task_id}/cancel` | `cancel_task` | ✅ |
| 6 | `POST` | `/api/v1/admin/tasks/{task_id}/restart` | `restart_task` | ✅ |
| 7 | `POST` | `/api/v1/admin/tasks/{task_id}/resume` | `resume_task` | ✅ |
| 8 | `POST` | `/api/v1/admin/projects/{project_id}/pipeline/restart-failed` | `restart_failed_tasks` | ✅ |

#### Endpoint Details

---

**1. `POST /api/v1/admin/workers/{worker_name}/stop`**

- **Path params**: `worker_name: str` — `fast` | `heavy` | `nlp`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "stopped", worker, tasks_revoked}`
- **Auth**: ❌ **None**
- **DB tables read**: none
- **DB tables written**: none
- **Services**: Redis (DELETE queue key), Celery (revoke active tasks)
- **Status codes**: 200

---

**2. `GET /api/v1/admin/workers/status`**

- **Path params**: none
- **Query params**: none
- **Request body**: none
- **Response**: `{active: {...}, reserved: {...}, scheduled: {...}}` — Celery inspector data
- **Auth**: ❌ **None**
- **DB tables read**: none
- **DB tables written**: none
- **Services**: Celery inspector
- **Status codes**: 200

---

**3. `POST /api/v1/admin/workers/kill-all`**

- **Path params**: none
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "killed", workers_shutdown: true, tasks_revoked, warning}`
- **Auth**: ✅ `get_current_user`
- **DB tables read**: none
- **DB tables written**: none
- **Services**: Celery (purge + broadcast shutdown + SIGKILL revoke)
- **Status codes**: 200

---

**4. `POST /api/v1/admin/projects/{project_id}/stop`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "stopped", run_id?, tasks_cancelled, details: [...]}`
- **Auth**: `get_current_user`
- **DB tables read**: `pipeline_runs` (active run), `pipeline_tasks` (by run_id)
- **DB tables written**: `pipeline_tasks` (UPDATE status="cancelled"), `pipeline_runs` (UPDATE status="cancelled"), `processing_states` (DELETE), `documentos` (UPDATE estado rollback)
- **Services**: Redis (clear pipeline_logs, purge queues), Celery (revoke tasks)
- **Status codes**: 200

---

**5. `POST /api/v1/admin/tasks/{task_id}/cancel`**

- **Path params**: `task_id: str`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "cancelled", task_id, document_rolled_back?, previous_state?}`
- **Auth**: `get_current_user`
- **DB tables read**: `pipeline_tasks` (by celery_task_id)
- **DB tables written**: `pipeline_tasks` (UPDATE status="cancelled"), `documentos` (UPDATE estado rollback)
- **Services**: Celery (revoke with SIGTERM)
- **Status codes**: 200, 404

---

**6. `POST /api/v1/admin/tasks/{task_id}/restart`**

- **Path params**: `task_id: str`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "restarted", old_task_id, new_task_id}`
- **Auth**: `get_current_user`
- **DB tables read**: `pipeline_tasks` (by celery_task_id)
- **DB tables written**: `task_step_checkpoints` (DELETE), `pipeline_tasks` (INSERT new record)
- **Services**: Celery (re-send task)
- **Status codes**: 200, 404

---

**7. `POST /api/v1/admin/tasks/{task_id}/resume`**

- **Path params**: `task_id: str`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "resumed", old_task_id, new_task_id, resume_from_step, note}`
- **Auth**: `get_current_user`
- **DB tables read**: `pipeline_tasks` (by celery_task_id), `task_step_checkpoints` (last completed)
- **DB tables written**: `pipeline_tasks` (INSERT new record with resume_from_step)
- **Services**: Celery (re-send task with resume kwarg)
- **Status codes**: 200, 404

---

**8. `POST /api/v1/admin/projects/{project_id}/pipeline/restart-failed`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{status: "restarted", count, tasks: [{old_task_id, new_task_id}]}`
- **Auth**: `get_current_user`
- **DB tables read**: `pipeline_runs` (latest run), `pipeline_tasks` (failed/cancelled)
- **DB tables written**: none
- **Services**: Celery (re-send failed tasks)
- **Status codes**: 200, 404

---

### 8. Theoretical Codes (`theoretical_codes.py`) — prefix `/api/v1`, tag `theoretical-codes`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/projects/{project_id}/theoretical/codes` | `list_theoretical_codes` | ✅ |
| 2 | `GET` | `/api/v1/projects/{project_id}/theoretical/codes/{code_id}` | `get_theoretical_code` | ✅ |
| 3 | `POST` | `/api/v1/projects/{project_id}/theoretical/codes` | `create_theoretical_code` | ✅ |
| 4 | `PUT` | `/api/v1/projects/{project_id}/theoretical/codes/{code_id}` | `update_theoretical_code` | ✅ |

#### Endpoint Details

---

**1. `GET /api/v1/projects/{project_id}/theoretical/codes`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: list of `{id, name, family, description, glaserian, user_defined, evaluation_logic, compatible_with, layer, visualization_hint}`
- **Auth**: `get_current_user`
- **DB tables read**: `theoretical_codes` (WHERE project_id IS NULL OR project_id = :pid)
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200

---

**2. `GET /api/v1/projects/{project_id}/theoretical/codes/{code_id}`**

- **Path params**: `project_id: UUID`, `code_id: UUID`
- **Query params**: none
- **Request body**: none
- **Response**: `{id, name, family, description, glaserian, user_defined, evaluation_logic, output_schema, compatible_with, layer, visualization_hint}`
- **Auth**: `get_current_user`
- **DB tables read**: `theoretical_codes`
- **DB tables written**: none
- **Services**: none
- **Status codes**: 200, 404

---

**3. `POST /api/v1/projects/{project_id}/theoretical/codes`**

- **Path params**: `project_id: UUID`
- **Query params**: none
- **Request body**: `dict` — `{name, family, description, evaluation_logic, output_schema, compatible_with, layer, visualization_hint}`
- **Response**: `{status: "created"}`
- **Auth**: `get_current_user`
- **DB tables read**: none
- **DB tables written**: `theoretical_codes` (INSERT with gen_random_uuid())
- **Services**: none
- **Status codes**: 201

---

**4. `PUT /api/v1/projects/{project_id}/theoretical/codes/{code_id}`**

- **Path params**: `project_id: UUID`, `code_id: UUID`
- **Query params**: none
- **Request body**: `dict` — `{name?, description?, evaluation_logic?, compatible_with?, layer?, visualization_hint?}`
- **Response**: `{status: "updated"}`
- **Auth**: `get_current_user`
- **DB tables read**: `theoretical_codes` (must be user_defined=true)
- **DB tables written**: `theoretical_codes` (UPDATE with COALESCE)
- **Services**: none
- **Status codes**: 200, 404

---

### 9. Elaboration (`elaboration.py`) — prefix `/api/v1`, tag `elaboration`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `POST` | `/api/v1/projects/{project_id}/elaboration/relationships` | `elaborate_relationship` | ✅ |
| 2 | `GET` | `/api/v1/projects/{project_id}/elaboration/relationships` | `list_relationships` | ✅ |
| 3 | `GET` | `/api/v1/projects/{project_id}/elaboration/relationships/{rel_id}` | `get_relationship` | ✅ |
| 4 | `PUT` | `/api/v1/projects/{project_id}/elaboration/relationships/{rel_id}/diverge` | `resolve_divergence` | ✅ |
| 5 | `GET` | `/api/v1/projects/{project_id}/elaboration/ghosts` | `list_ghosts` | ✅ |
| 6 | `POST` | `/api/v1/projects/{project_id}/elaboration/ghosts/{memo_id}/absorb` | `absorb_ghost` | ✅ |
| 7 | `GET` | `/api/v1/projects/{project_id}/elaboration/rename-suggestions/{category_id}` | `get_rename_suggestions` | ✅ |
| 8 | `POST` | `/api/v1/projects/{project_id}/elaboration/rename` | `apply_rename` | ✅ |
| 9 | `GET` | `/api/v1/projects/{project_id}/elaboration/categories/{category_id}/definition-history` | `get_definition_history` | ✅ |
| 10 | `GET` | `/api/v1/projects/{project_id}/elaboration/ecosystem` | `get_ecosystem` | ✅ |
| 11 | `PUT` | `/api/v1/projects/{project_id}/elaboration/ecosystem/layout` | `save_ecosystem_layout` | ✅ |
| 12 | `GET` | `/api/v1/projects/{project_id}/elaboration/recommendations` | `get_recommendations` | ✅ |
| 13 | `GET` | `/api/v1/projects/{project_id}/elaboration/model` | `get_theoretical_model` | ✅ |
| 14 | `POST` | `/api/v1/projects/{project_id}/modification/request` | `request_modification` | ✅ |
| 15 | `POST` | `/api/v1/projects/{project_id}/modification/apply` | `apply_modification` | ✅ |

#### Endpoint Details

---

**1–6: Relationships & Ghosts (T15)**

- **1. `POST .../elaboration/relationships`**: Body `{category_ids, theoretical_code_id, researcher_question}`. Dispatches `elaborate_relationship` Celery task. Response: `{status: "processing", task_id}`.
- **2. `GET .../elaboration/relationships`**: Lists conceptual_relationships joined with theoretical_codes. Returns list of `{id, category_ids, theoretical_code_id, elaboration_status, direction, converging_docs, diverging_docs, conceptual_fit, layer, position_tension, question, code_name}`.
- **3. `GET .../elaboration/relationships/{rel_id}`**: Full relationship detail with traceability. Path: `rel_id: UUID`.
- **4. `PUT .../elaboration/relationships/{rel_id}/diverge`**: Body `{divergence_resolution}`. Updates diverging_doc_count and elaboration_status="expanded". Path: `rel_id: UUID`.
- **5. `GET .../elaboration/ghosts`**: Lists unconnected HIPOTESIS memos not yet in elaboration_memos. Response: `[{id, content, type}]`.
- **6. `POST .../elaboration/ghosts/{memo_id}/absorb`**: Body `{target_category_id}`. Dispatches `absorb_ghost` Celery task. Path: `memo_id: UUID`.

All require auth. DB tables: `conceptual_relationships`, `theoretical_codes`, `memos`.

---

**7–9: Rename API (T16)**

- **7. `GET .../elaboration/rename-suggestions/{category_id}`**: Path: `category_id: UUID`. Checks `should_suggest_rename()`, dispatches `suggest_rename` Celery task if needed. Response: `{needs_rename, status?, task_id?, suggestions: []}`.
- **8. `POST .../elaboration/rename`**: Body `{category_id, new_name, rationale}`. Calls `apply_rename()` synchronously. Response: `{status: "renamed", category_id, new_name}`.
- **9. `GET .../elaboration/categories/{category_id}/definition-history`**: Path: `category_id: UUID`. Lists `category_definition_versions` ordered by version. Response: `[{version, name, definition, trigger, detail, created_at}]`.

Services: `rename_detector.py`

---

**10–13: Ecosystem & Recommendations (T17)**

- **10. `GET .../elaboration/ecosystem`**: Returns `{blobs, tendrils, layout: {blob_positions, ghost_positions, fog_zones, physics_params}}`. Reads `categorias`, `conceptual_relationships`, `ecosystem_layouts`.
- **11. `PUT .../elaboration/ecosystem/layout`**: Body `{blob_positions, ghost_positions, fog_zones, physics_params}`. Upserts `ecosystem_layouts`. Response: `{status: "saved"}`.
- **12. `GET .../elaboration/recommendations`**: Uses `RecommendationEngine`. Response: `[{category, title, description, action_type, category_ids, suggested_code, impact_score}]`.
- **13. `GET .../elaboration/model`**: Returns `{relationships, orphan_categories, layers_coverage}`.

---

**14–15: HITL Modification (T20 / P5)**

- **14. `POST .../modification/request`**: Body `{agent_id, user_request, current_memo, memo_id?, original_prompt?}`. Invokes `HITLModificationAgent.process_request()`. Response: `{valid_request, filter_reason, suggested_questions, recommended, recommendation_reason, recommendation_confidence, evidence_sufficient, modified_memo, impact_summary, missing_evidence}`.
- **15. `POST .../modification/apply`**: Body `{agent_id, memo_id, new_content, agent_output_id?}`. Invokes `HITLModificationAgent.apply_modification()`. Writes to `output_modifications` table via sync DB session. Response: `{status: "applied", wiped_tables, restart_from, invalidated_outputs}`.

No auth for these two? Yes, `get_current_user` required. DB tables written: `output_modifications`.

---

### 10. Analysis (`analysis.py`) — prefix `/api/v1`, tag `analysis`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/projects/{project_id}/analysis/saturation-gaps` | `get_saturation_gaps` | ✅ |
| 2 | `POST` | `/api/v1/projects/{project_id}/analysis/saturation-gaps/refresh` | `refresh_saturation_gaps` | ✅ |
| 3 | `GET` | `/api/v1/projects/{project_id}/population-context` | `get_population_context` | ✅ |
| 4 | `GET` | `/api/v1/projects/{project_id}/population-context/versions` | `get_population_context_versions` | ✅ |
| 5 | `GET` | `/api/v1/coding-styles` | `list_coding_styles` | ❌ |
| 6 | `PUT` | `/api/v1/projects/{project_id}/config/coding-styles` | `set_coding_styles` | ✅ |
| 7 | `GET` | `/api/v1/projects/{project_id}/saturation-panel` | `get_saturation_panel` | ✅ |

#### Details

- **1, 2**: Use `SaturationGapAnalyzer.full_analysis()`. #1 returns `{project_id, generated_at, critical, warnings, saturated}`. #2 returns `{status: "refreshed", gaps_found}`.
- **3, 4**: Read from `population_contexts` table.
- **5**: Returns `{styles: [...], default}` — Saldaña coding styles library. No auth.
- **6**: Query `styles: str` (comma-separated keys). Writes to `proyectos.population_assumption` JSONB.
- **7**: Query `refresh: bool = False`. Reads `categorias.saturation_panel_json`. Returns per-category 4-signal panel (matematica, cualitativa, cobertura, integracion).

---

### 11. Hypotheses (`hypotheses.py`) — prefix `/api/v1/hypotheses`, tag `hypotheses`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/hypotheses/candidates` | `list_candidates` | ✅ |
| 2 | `POST` | `/api/v1/hypotheses/{hypothesis_id}/accept` | `accept_hypothesis` | ✅ |
| 3 | `POST` | `/api/v1/hypotheses/{hypothesis_id}/modify` | `modify_hypothesis` | ✅ |
| 4 | `POST` | `/api/v1/hypotheses/{hypothesis_id}/reject` | `reject_hypothesis` | ✅ |
| 5 | `POST` | `/api/v1/hypotheses/{hypothesis_id}/split` | `split_hypothesis` | ✅ |

#### Details

- **1**: Query `proyecto_id: UUID` (required), `status: str = "candidate"`. Returns `list[HypothesisCandidate]`.
- **2**: Body `AcceptRequest` — `{justification: str}`. Sets status="accepted", confidence=1.0.
- **3**: Body `ModifyRequest` — `{new_text: str, new_level?: "general"|"specific"|"emergent", justification: str}`. Sets status back to "candidate", penalizes confidence -0.2.
- **4**: Body `RejectRequest` — `{reason: str}`. Sets status="rejected", confidence=0.0.
- **5**: Body `SplitRequest` — `{children: [str, ...] (2-5), justification: str}`. Marks original as "split", creates N child hypotheses with status="candidate".

All read/write `hypotheses` table (model: `Hypothesis`).

---

### 12. Auth (`auth.py`) — prefix `/api/v1/auth`, tag `auth`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `POST` | `/api/v1/auth/register` | `register` | ❌ |
| 2 | `POST` | `/api/v1/auth/login` | `login` | ❌ |
| 3 | `POST` | `/api/v1/auth/logout` | `logout` | ✅ `get_current_user` + token |
| 4 | `POST` | `/api/v1/auth/refresh` | `refresh_access_token` | ❌ |

#### Details

- **1**: Body `RegisterBody` — `{nombre: str, correo: str, password: str}`. Returns `{id, nombre, correo, access_token, refresh_token, token_type}`. DB: `usuarios` (INSERT).
- **2**: Body params: `email: str, password: str`. Returns `{access_token, refresh_token, token_type}`. DB: `usuarios` (SELECT).
- **3**: Requires auth dependency. Blacklists JWT `jti` in Redis. DB: none. Response: `{msg: "Logged out"}`.
- **4**: Query/body param: `refresh_token: str`. Validates token type="refresh" and not blacklisted. Returns `{access_token, token_type}`. DB: none.

---

### 13. RAG (`rag.py`) — prefix `/api/v1/rag`, tag `rag`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/rag/search` | `search_segments` | ✅ |
| 2 | `GET` | `/api/v1/rag/context/{code_id}` | `get_code_context` | ✅ |

#### Details

- **1**: Query params: `q: str` (min 2), `proyecto_id: UUID`, `top_k: int` = 5 (1-20), `fusion: "rrf"|"semantic"|"lexical"` = "rrf", `diversify: bool` = False, `lambda_mmr: float` = 0.7 (0-1), `documento_id: UUID|null`. Uses `RAGService.search()`.
- **2**: Path `code_id: UUID`. Query: `proyecto_id: UUID`, `top_k: int` = 10, `lambda_mmr: float` = 0.6. Uses `RAGService.search_context_for_code()`.

Both use TEI embeddings + HNSW + BM25 + RRF fusion + optional MMR diversification.

---

### 14. Config Info (`config_info.py`) — prefix `/api/v1`, tag `config`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/config` | `get_config` | ❌ |
| 2 | `PUT` | `/api/v1/config` | `save_config` | ✅ |

#### Details

- **1**: Returns full runtime config: `{llm, segmentation, cgt, system, auth, _runtime_overrides}`. Reads from `runtime.json` + env vars.
- **2**: Body `RuntimeConfigUpdate` — nested model with `{llm?, segmentation?, cgt?, system?}`. Persists to `runtime.json`. Returns `{status, updated_fields, blocked_by_env}`.

---

### 15. Events (`events.py`) — prefix `/api/v1/events`, tag `events`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/events/stream` | `stream_events` | ❌ *token via query* |

- Query: `proyecto_id: UUID`, `token: str|null`. Returns `StreamingResponse` (text/event-stream). Subscribes to Redis pub/sub channel `project:{id}:events`. Sends heartbeat every 30s.

---

### 16. Ping & Worker Lifecycle (`ping.py`) — prefix `/api/v1`, tag `system`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/ping` | `ping` | ✅ |
| 2 | `POST` | `/api/v1/admin/workers/{worker}/start` | `start_worker` | ✅ |
| 3 | `POST` | `/api/v1/admin/workers/{worker}/stop` | `stop_worker` | ✅ *(Docker-level)* |

- **1**: Returns `{status: "ok", user_id, message: "Authenticated"}`.
- **2–3**: Path `worker: str` (`fast`|`heavy`|`nlp`). Use Docker socket (`/var/run/docker.sock`) to start/stop containers. Response: `{ok, status/error}`.

---

### 17. Setup (`setup.py`) — prefix `/api/v1`, tag `setup`

| # | Method | Full Path | Handler | Auth |
|---|--------|-----------|---------|------|
| 1 | `GET` | `/api/v1/setup/status` | `get_setup_status` | ❌ |
| 2 | `POST` | `/api/v1/setup/initialize` | `initialize_setup` | ❌ |
| 3 | `GET` | `/api/v1/setup/progress` | `get_setup_progress` | ❌ |

- **1**: Returns `{language, spacy_ready, stanza_ready, models_downloaded, models_pending, progress, message}`.
- **2**: Body `{language: str}`. Starts background thread for `warmup_language()`. Returns `{status: "started"|"already_running", language}`.
- **3**: Returns module-level `_download_progress` dict `{status, progress, message, language}`.

---

## Section 2: API Coverage Matrix

| Domain Area | CRUD Operations Present | Missing Operations |
|---|---|---|
| **Projects** | Create (POST /projects), Read (GET /projects, GET /projects/{id}), Update (PUT /projects/{id}), Delete (DELETE /projects/{id}) | — *Full CRUD* |
| **Documents** | Create (upload), Read (list, download, presigned), Update (process, reorder, patch text, undo-punctuate), Delete (single doc, all docs, segments) | — *Full CRUD* |
| **Segments** | Read (GET list), Delete (clear per-doc, per-project), Create (via segment_document, save_task_segments) | Update (no PATCH for segment text/metadata) |
| **Categories** | Create (POST /categories), Read (GET /categories) | Update (no PUT/PATCH), Delete (no DELETE) |
| **Code Assignments** | Create (POST /code-assignments) | Read, Update, Delete missing |
| **Recommendations** | Read (GET /segments/{id}/recommendations) | Create, Update, Delete (N/A — computed) |
| **Pipeline** | Read (log, status, decisions, tail), Execute (run, run-stage, run-agent), Configure (pause-config, context-window) | Delete/Cancel run (handled via admin) |
| **HITL Decisions** | Read (pending, detail, open-coding-status), Update (decide, open-coding-decide), Delete (reset) | — *Full CRUD* |
| **Memos** | Create (POST /memos), Read (available-types, stale-entities), Update (PATCH memo), Delete (single, by-type) | — *Full CRUD* |
| **Admin Tasks** | Read (worker status), Update (stop, kill, cancel, restart, resume, restart-failed) | Delete (N/A) |
| **Theoretical Codes** | Create, Read (list, single), Update (PUT) | Delete missing |
| **Elaboration — Relationships** | Create (elaborate), Read (list, single), Update (resolve divergence) | Delete missing |
| **Elaboration — Ghosts** | Read (list), Update (absorb) | Create, Delete (N/A — ghosts are existing memos) |
| **Elaboration — Renames** | Read (suggestions), Create (apply) | Update, Delete (N/A) |
| **Elaboration — Ecosystem** | Read (ecosystem, model), Update (layout) | Create (auto), Delete missing |
| **Elaboration — Recommendations** | Read | — (computed) |
| **Elaboration — Modification** | Create (request, apply) | Read, Update, Delete missing |
| **Analysis** | Read (saturation-gaps, population-context, saturation-panel), Refresh (POST refresh) | — (analysis endpoints, not entity CRUD) |
| **Hypotheses** | Read (candidates), Update (accept, modify, reject, split) | Create, Delete missing |
| **Auth** | Register, Login, Logout, Refresh | Password reset/change, email verification missing |
| **RAG Search** | Read (search, context) | — (search endpoints) |
| **Runtime Config** | Read (GET /config), Update (PUT /config) | — (app-level config) |
| **Events** | Read (SSE stream) | — (event streaming) |
| **Setup** | Read (status, progress), Create/Execute (initialize) | — (one-time setup) |
| **Docker Workers** | Create (start), Update (stop) | Read (status handled by admin), Delete |

---

## Section 3: Endpoint-to-Frontend Mapping

Based on the known `client.ts` functions listed in the task brief.

| client.ts Function | Expected Endpoint | Mapped Endpoint | Status |
|---|---|---|---|
| `getProject` | GET `/api/v1/projects/{id}` | ✅ `/api/v1/projects/{project_id}` | ✅ CONSUMED |
| `listDocuments` | GET `/api/v1/documents` | ✅ `/api/v1/documents?proyecto_id=` | ✅ CONSUMED |
| `uploadDocument` | POST upload | ✅ `/api/v1/documents/upload/{project_id}` | ✅ CONSUMED |
| `punctuateDocument` | POST punctuate | ✅ `/api/v1/documents/{document_id}/punctuate` | ✅ CONSUMED |
| `getTaskStatus` | GET task status | ✅ `/api/v1/documents/tasks/{task_id}` | ✅ CONSUMED |
| `deleteDocument` | DELETE document | ✅ `/api/v1/documents/{document_id}` | ✅ CONSUMED |
| `deleteAllDocuments` | DELETE all docs | ✅ `/api/v1/projects/{project_id}/documents` | ✅ CONSUMED |
| `deleteDocumentSegments` | DELETE segments | ✅ `/api/v1/documents/{document_id}/segments` | ✅ CONSUMED |
| `resetDocsToCrudo` | POST reset to crudo | ✅ `/api/v1/documents/project/{project_id}/reset-to-crudo` | ✅ CONSUMED |
| `restoreDocumentOriginal` | POST restore original | ✅ `/api/v1/documents/{document_id}/restore-original` | ✅ CONSUMED |
| `getPipelineLog` | GET pipeline log | ✅ `/api/v1/projects/{project_id}/pipeline/log` | ✅ CONSUMED |
| `getAgentMemos` | GET agent memos | ✅ `/api/v1/projects/{project_id}/agent-memos` | ✅ CONSUMED |
| `getPendingHitl` | GET pending HITL | ✅ `/api/v1/projects/{project_id}/hitl/pending` | ✅ CONSUMED |
| `decideHitl` | POST hitl decide | ✅ `/api/v1/projects/{project_id}/hitl/{gate_name}/decide` | ✅ CONSUMED |
| `ping` | GET /ping | ✅ `/api/v1/ping` | ✅ CONSUMED |
| `clearToken` | POST /logout | ✅ `/api/v1/auth/logout` | ✅ CONSUMED |
| `stopProjectPipeline` | POST stop | ✅ `/api/v1/admin/projects/{project_id}/stop` | ✅ CONSUMED |
| `restartFailedTasks` | POST restart failed | ✅ `/api/v1/admin/projects/{project_id}/pipeline/restart-failed` | ✅ CONSUMED |
| `updateProject` | PUT project | ✅ `/api/v1/projects/{project_id}` | ✅ CONSUMED |
| `updatePopulationAssumption` | PUT pop assumption | ✅ `/api/v1/projects/{project_id}/config/population-assumption` | ✅ CONSUMED |
| `generatePopulationGeneralization` | POST generalize | ✅ `/api/v1/projects/{project_id}/config/population-assumption/generalize` | ✅ CONSUMED |
| `getStaleUserEntities` | GET stale entities | ✅ `/api/v1/projects/{project_id}/stale-user-entities?current_stage=` | ✅ CONSUMED |
| `getAgentLogs` | GET agent logs | ✅ `/api/v1/projects/{project_id}/agent-logs` | ✅ CONSUMED |
| `listCategories` | GET categories | ✅ `/api/v1/categories?proyecto_id=` | ✅ CONSUMED |
| `listSegments` | GET segments | ✅ `/api/v1/documents/{document_id}/segments` | ✅ CONSUMED |
| `segmentDocument` | POST segment | ✅ `/api/v1/documents/{document_id}/segment` | ✅ CONSUMED |
| `getProjectConfig` | GET project config | ✅ `/api/v1/projects/{project_id}/config` | ✅ CONSUMED |
| `getProjectConfigHistory` | GET config history | ✅ `/api/v1/projects/{project_id}/config/history` | ✅ CONSUMED |
| `updateMutationPolicy` | PUT mutation policy | ✅ `/api/v1/projects/{project_id}/config/mutation-policy` | ✅ CONSUMED |
| `getPresignedUrl` | GET presigned URL | ✅ `/api/v1/documents/presigned/{document_id}` | ✅ CONSUMED |
| `getTheoreticalCodes` | GET theoretical codes | ✅ `/api/v1/projects/{project_id}/theoretical/codes` | ✅ CONSUMED |
| `createTheoreticalCode` | POST theoretical code | ✅ `/api/v1/projects/{project_id}/theoretical/codes` | ✅ CONSUMED |
| `getEcosystem` | GET ecosystem | ✅ `/api/v1/projects/{project_id}/elaboration/ecosystem` | ✅ CONSUMED |
| `saveEcosystemLayout` | PUT ecosystem layout | ✅ `/api/v1/projects/{project_id}/elaboration/ecosystem/layout` | ✅ CONSUMED |
| `elaborateRelationship` | POST elaborate rel | ✅ `/api/v1/projects/{project_id}/elaboration/relationships` | ✅ CONSUMED |
| `getRelationships` | GET relationships | ✅ `/api/v1/projects/{project_id}/elaboration/relationships` | ✅ CONSUMED |
| `getRelationship` | GET relationship | ✅ `/api/v1/projects/{project_id}/elaboration/relationships/{rel_id}` | ✅ CONSUMED |
| `resolveDivergence` | PUT resolve divergence | ✅ `/api/v1/projects/{project_id}/elaboration/relationships/{rel_id}/diverge` | ✅ CONSUMED |
| `getGhosts` | GET ghosts | ✅ `/api/v1/projects/{project_id}/elaboration/ghosts` | ✅ CONSUMED |
| `absorbGhost` | POST absorb ghost | ✅ `/api/v1/projects/{project_id}/elaboration/ghosts/{memo_id}/absorb` | ✅ CONSUMED |
| `getRenameSuggestions` | GET rename suggestions | ✅ `/api/v1/projects/{project_id}/elaboration/rename-suggestions/{category_id}` | ✅ CONSUMED |
| `applyRename` | POST apply rename | ✅ `/api/v1/projects/{project_id}/elaboration/rename` | ✅ CONSUMED |
| `getDefinitionHistory` | GET definition history | ✅ `/api/v1/projects/{project_id}/elaboration/categories/{category_id}/definition-history` | ✅ CONSUMED |
| `getRecommendations` | GET recommendations | ✅ `/api/v1/projects/{project_id}/elaboration/recommendations` | ✅ CONSUMED |
| `getTheoreticalModel` | GET theoretical model | ✅ `/api/v1/projects/{project_id}/elaboration/model` | ✅ CONSUMED |
| `getSaturationGaps` | GET saturation gaps | ✅ `/api/v1/projects/{project_id}/analysis/saturation-gaps` | ✅ CONSUMED |
| `refreshSaturationGaps` | POST refresh sat gaps | ✅ `/api/v1/projects/{project_id}/analysis/saturation-gaps/refresh` | ✅ CONSUMED |
| `stopWorker` | POST stop worker | ✅ `/api/v1/admin/workers/{worker_name}/stop` | ✅ CONSUMED |
| `killAllWorkers` | POST kill all workers | ✅ `/api/v1/admin/workers/kill-all` | ✅ CONSUMED |
| `cancelTask` | POST cancel task | ✅ `/api/v1/admin/tasks/{task_id}/cancel` | ✅ CONSUMED |
| `restartTask` | POST restart task | ✅ `/api/v1/admin/tasks/{task_id}/restart` | ✅ CONSUMED |
| `resumeTask` | POST resume task | ✅ `/api/v1/admin/tasks/{task_id}/resume` | ✅ CONSUMED |
| `getHitlDetail` | GET hitl detail | ✅ `/api/v1/projects/{project_id}/hitl/{gate_name}/detail` | ✅ CONSUMED |
| `getAvailableMemoTypes` | GET memo types | ✅ `/api/v1/projects/{project_id}/available-memo-types` | ✅ CONSUMED |
| `getEntityTypeColors` | GET entity colors | ✅ `/api/v1/entity-type-colors` | ✅ CONSUMED |
| `createMemo` | POST create memo | ✅ `/api/v1/projects/{project_id}/memos` | ✅ CONSUMED |
| `deleteMemosByType` | DELETE memos by type | ✅ `/api/v1/projects/{project_id}/memos?tipo=` | ✅ CONSUMED |
| `getPipelineDecisions` | GET pipeline decisions | ✅ `/api/v1/projects/{project_id}/pipeline/decisions` | ✅ CONSUMED |
| `getSetupStatus` | GET setup status | ✅ `/api/v1/setup/status` | ✅ CONSUMED |
| `initializeSetup` | POST setup initialize | ✅ `/api/v1/setup/initialize` | ✅ CONSUMED |
| `getSetupProgress` | GET setup progress | ✅ `/api/v1/setup/progress` | ✅ CONSUMED |

### Endpoints with NO known client.ts consumer

These backend endpoints exist but were NOT mentioned in the client.ts function list:

| Full Path | Method | Handler | Likely Gap |
|---|---|---|---|
| `/api/v1/projects` (list) | GET | `list_projects` | ❌ NOT CONSUMED |
| `/api/v1/projects` (create) | POST | `create_project` | ❌ NOT CONSUMED (separate from getProject) |
| `/api/v1/projects/research-question/preview` | POST | `preview_research_question_standalone` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/research-question/preview` | POST | `preview_research_question` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/research-question` (update) | PUT | `update_research_question` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/research-question` (get) | GET | `get_research_question` | ❌ NOT CONSUMED |
| `/api/v1/documents/download/{document_id}` | GET | `download_document` | ❌ NOT CONSUMED |
| `/api/v1/documents/{document_id}/segments-from-task` | POST | `save_task_segments` | ❌ NOT CONSUMED |
| `/api/v1/documents/{document_id}/process` | POST | `process_document` | ❌ NOT CONSUMED |
| `/api/v1/documents/{document_id}/undo-punctuate` | POST | `undo_punctuate` | ❌ NOT CONSUMED |
| `/api/v1/documents/project/{project_id}/segments` | DELETE | `delete_all_segments` | ❌ NOT CONSUMED |
| `/api/v1/documents/project/{project_id}/reorder` | POST | `reorder_documents` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/run-stage/{stage_name}` | POST | `run_pipeline_stage` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/status` | GET | `get_pipeline_status` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/run` | POST | `run_pipeline_orchestrated` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/tail` | GET | `tail_pipeline_logs` | ❌ NOT CONSUMED |
| `/api/v1/agent-outputs/{memo_id}` | DELETE | `delete_agent_output` | ❌ NOT CONSUMED |
| `/api/v1/agent-outputs/{memo_id}` | PATCH | `patch_agent_output` | ❌ NOT CONSUMED |
| `/api/v1/documents/{document_id}/text` | PATCH | `patch_document_text` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/run-agent/{agent_id}` | POST | `run_single_agent` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/pause-config` | PATCH | `update_pause_config` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/pipeline/context-window` | PATCH | `update_context_window` | ❌ NOT CONSUMED |
| `/api/v1/categories` (create) | POST | `create_category` | ❌ NOT CONSUMED |
| `/api/v1/code-assignments` | POST | `assign_code` | ❌ NOT CONSUMED |
| `/api/v1/segments/{segment_id}/recommendations` | GET | `recommend_codes` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/hitl/reset` | POST | `reset_hitl_decisions` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/hitl/open-coding/status` | GET | `get_open_coding_hitl_status` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/hitl/open-coding/decide` | POST | `decide_open_coding_hitl` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/memos/{memo_id}` | PATCH | `patch_user_memo` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/memos/{memo_id}` | DELETE | `delete_user_memo` | ❌ NOT CONSUMED |
| `/api/v1/admin/workers/status` | GET | `worker_status` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/theoretical/codes/{code_id}` | GET | `get_theoretical_code` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/theoretical/codes/{code_id}` | PUT | `update_theoretical_code` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/population-context` | GET | `get_population_context` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/population-context/versions` | GET | `get_population_context_versions` | ❌ NOT CONSUMED |
| `/api/v1/coding-styles` | GET | `list_coding_styles` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/config/coding-styles` | PUT | `set_coding_styles` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/saturation-panel` | GET | `get_saturation_panel` | ❌ NOT CONSUMED |
| `/api/v1/hypotheses/candidates` | GET | `list_candidates` | ❌ NOT CONSUMED |
| `/api/v1/hypotheses/{hypothesis_id}/accept` | POST | `accept_hypothesis` | ❌ NOT CONSUMED |
| `/api/v1/hypotheses/{hypothesis_id}/modify` | POST | `modify_hypothesis` | ❌ NOT CONSUMED |
| `/api/v1/hypotheses/{hypothesis_id}/reject` | POST | `reject_hypothesis` | ❌ NOT CONSUMED |
| `/api/v1/hypotheses/{hypothesis_id}/split` | POST | `split_hypothesis` | ❌ NOT CONSUMED |
| `/api/v1/auth/register` | POST | `register` | ❌ NOT CONSUMED |
| `/api/v1/auth/login` | POST | `login` | ❌ NOT CONSUMED |
| `/api/v1/auth/refresh` | POST | `refresh_access_token` | ❌ NOT CONSUMED |
| `/api/v1/rag/search` | GET | `search_segments` | ❌ NOT CONSUMED |
| `/api/v1/rag/context/{code_id}` | GET | `get_code_context` | ❌ NOT CONSUMED |
| `/api/v1/config` (get) | GET | `get_config` | ❌ NOT CONSUMED |
| `/api/v1/config` (put) | PUT | `save_config` | ❌ NOT CONSUMED |
| `/api/v1/events/stream` | GET | `stream_events` | ❌ NOT CONSUMED |
| `/api/v1/admin/workers/{worker}/start` | POST | `start_worker` | ❌ NOT CONSUMED |
| `/api/v1/admin/workers/{worker}/stop` | POST | `stop_worker` (Docker) | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/modification/request` | POST | `request_modification` | ❌ NOT CONSUMED |
| `/api/v1/projects/{project_id}/modification/apply` | POST | `apply_modification` | ❌ NOT CONSUMED |

### Summary Statistics

- **Total endpoints documented**: 117
- **Mapped to known client.ts functions**: 58 (✅ CONSUMED)
- **No known frontend consumer**: 55 (❌ NOT CONSUMED)
- **Partially consumed**: 0 (⚠️)

**Note**: The "NOT CONSUMED" endpoints may still be used by the frontend via functions not named in the provided list, or via direct `fetch`/`axios` calls that bypass the named `client.ts` functions. For example, `login` and `register` are almost certainly called by the frontend's auth pages. The 55 "NOT CONSUMED" figure should be verified against the actual frontend source.

---

*Report generated from reading all 17 route files + main.py. All paths confirmed against router prefixes.*
