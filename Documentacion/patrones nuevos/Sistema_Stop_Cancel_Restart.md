# Sistema de Stop / Cancel / Restart — Diseño Integral

> **Control granular del pipeline: desde abortar una llamada LLM hasta detener todos los workers.**
>
> Fecha: 2026-06-16

---

## 1. Los 4 niveles de control

```
NIVEL 4: ☠️  KILL ALL        ──▶ mata workers a nivel OS (SIGKILL)
         ─────────────────────────────────────────────────
NIVEL 3: ⏹  STOP PROJECT     ──▶ revoca TODAS las tareas de un proyecto
         ─────────────────────────────────────────────────
NIVEL 2: ⏸  CANCEL TASK      ──▶ revoca UNA tarea Celery + limpia side-effects
         ─────────────────────────────────────────────────
NIVEL 1: ✂️  ABORT LLM CALL   ──▶ corta streaming LLM mid-generación (abort_event)
         ─────────────────────────────────────────────────
```

---

## 2. Nivel 1 — ✂️ Abort LLM Call (streaming)

### 2.1 Qué hace

Corta una llamada LLM en curso **a mitad de generación**. Together.ai detecta la
desconexión TCP y deja de facturar tokens. Es la más quirúrgica y la que más
dinero ahorra.

### 2.2 Mecanismo

```python
# backend/app/core/together_client.py — NUEVO

import asyncio
from typing import AsyncGenerator, Optional

class TogetherLLM:
    # ... existing code ...

    async def chat_stream(
        self,
        model: str | ModelEndpoint,
        messages: list[dict[str, str]],
        abort_event: Optional[asyncio.Event] = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        response_format: Optional[dict] = None,
    ) -> dict[str, Any]:
        """
        Streaming con soporte de abort.
        
        Si abort_event.is_set() → cierra stream → TCP disconnect →
        Together detiene inferencia inmediatamente.
        """
        endpoint = self._resolve_endpoint(model)

        kwargs = {
            "model": endpoint.model_id,
            "messages": messages,
            "max_tokens": max_tokens or endpoint.max_tokens_default,
            "temperature": temperature or endpoint.temperature_default,
            "stream": True,
        }
        if response_format:
            kwargs["response_format"] = response_format

        stream = self._client.chat.completions.create(**kwargs)

        full_content = ""
        aborted = False
        try:
            for chunk in stream:
                if abort_event and abort_event.is_set():
                    aborted = True
                    stream.close()
                    break
                if chunk.choices[0].delta.content:
                    full_content += chunk.choices[0].delta.content
        finally:
            stream.close()

        return {
            "content": full_content,
            "model": endpoint.model_id,
            "tier": endpoint.tier,
            "aborted": aborted,
        }
```

### 2.3 Integración con el bucle agencial

Cada agente (`BaseAgent`) recibe un `abort_event` que propaga a todas las
llamadas LLM internas:

```python
# backend/app/agents/base.py — modificar

class BaseAgent:
    def __init__(self, ..., abort_event: Optional[asyncio.Event] = None):
        ...
        self.abort_event = abort_event

    def _check_abort(self):
        """Llamar antes de cada step costoso."""
        if self.abort_event and self.abort_event.is_set():
            raise AgentAbortedError("Agent aborted by user")

    def run(self, project_id: str, **kwargs) -> AgentResult:
        for iteration in range(1, self.max_iterations + 1):
            self._check_abort()  # ← check antes de cada iteración
            ...
```

### 2.4 Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `backend/app/core/together_client.py` | `chat_stream()` con `abort_event` |
| `backend/app/agents/base.py` | `abort_event` + `_check_abort()` |
| `backend/app/agents/self_refiner.py` | Propagar `abort_event` a `_step()` |
| `backend/app/agents/react_runner.py` | Propagar `abort_event` a `_step()` |
| `backend/app/agents/plan_executor.py` | Propagar `abort_event` a `_step()` |
| `workers/heavy/llm_client.py` | `run_agent()` → `run_agent_stream()` con abort |
| `workers/fast/llm_client.py` | Ídem |

---

## 3. Nivel 2 — ⏸ Cancel Task (Celery revoke + cleanup)

### 3.1 Qué hace

Revoca una tarea Celery específica. Si está en cola (no empezó), se cancela
limpiamente. Si ya está ejecutándose, se le envía SIGTERM y la tarea debe
manejar la limpieza.

### 3.2 Modelo de tracking: `PipelineRun`

Necesitamos persistir qué se ejecutó y en qué estado quedó, para poder hacer
rollback y restart.

```python
# backend/app/models/domain/pipeline_run.py — NUEVO

class PipelineRun(Base, TimestampMixin):
    """Una ejecución del pipeline. Agrupa todas las tareas disparadas."""

    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("proyectos.id"))
    status: Mapped[str] = mapped_column(String(20), default="running")
    # running | completed | cancelled | failed

    triggered_by: Mapped[str] = mapped_column(String(50), default="user")
    # "user" | "auto" (triggered by _maybe_trigger_phase_b)

    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    # {total_docs, need_segment, need_agents, already_done}


class PipelineTask(Base, TimestampMixin):
    """Una tarea individual dentro de un PipelineRun."""

    __tablename__ = "pipeline_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_runs.id"))
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documentos.id"), nullable=True)

    celery_task_id: Mapped[str] = mapped_column(String(100), unique=True)
    task_name: Mapped[str] = mapped_column(String(100))
    # "segmentar_documento" | "process_document_agents_a" | etc.

    status: Mapped[str] = mapped_column(String(20), default="queued")
    # queued | running | completed | cancelled | failed

    doc_estado_before: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Estado del documento ANTES de ejecutar (para rollback)
    # "crudo" | "segmentando" | "segmentado" | "listo"

    segments_before: Mapped[int] = mapped_column(Integer, default=0)
    codes_before: Mapped[int] = mapped_column(Integer, default=0)
```

### 3.3 Endpoint de cancelación por tarea

```python
# backend/app/api/v1/admin.py — NUEVO

@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    Cancela UNA tarea específica y limpia sus side-effects.
    
    Si la tarea ya empezó:
    - Envía SIGTERM al worker
    - Revierte el documento a su estado anterior
    - Elimina segmentos/códigos creados por esta tarea
    """
    from app.models.domain.pipeline_run import PipelineTask
    from app.core.celery_app import celery_app

    # 1. Buscar la tarea en nuestro tracking
    task_record = await db.get(PipelineTask, task_id)  # usar celery_task_id
    
    if not task_record:
        # Fallback: revocar sin limpiar
        celery_app.control.revoke(task_id, terminate=True)
        return {"status": "revoked", "cleanup": "unknown"}

    # 2. Revocar en Celery
    celery_app.control.revoke(task_id, terminate=True, signal='SIGTERM')

    # 3. Rollback: restaurar estado del documento
    if task_record.document_id and task_record.doc_estado_before:
        await db.execute(
            text("UPDATE documentos SET estado = :estado WHERE id = :did"),
            {"estado": task_record.doc_estado_before, "did": task_record.document_id}
        )

    # 4. Marcar como cancelada
    task_record.status = "cancelled"
    await db.commit()

    return {
        "status": "cancelled",
        "task_id": task_id,
        "document_rolled_back": str(task_record.document_id) if task_record.document_id else None,
        "previous_state": task_record.doc_estado_before,
    }
```

### 3.4 Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `backend/app/models/domain/pipeline_run.py` | **NUEVO** — PipelineRun + PipelineTask |
| `backend/app/api/v1/admin.py` | **NUEVO** — endpoints de cancel/restart |
| `backend/app/api/v1/pipeline.py` | `run_pipeline_orchestrated()` → crear `PipelineRun` + `PipelineTask` records |
| `workers/heavy/tasks.py` | `process_document_agents_a()` → guardar `doc_estado_before` al empezar |
| `workers/nlp/tasks.py` | `segmentar_documento()` → guardar `doc_estado_before` al empezar |
| `workers/fast/tasks.py` | `punctuate_text()` → guardar `doc_estado_before` al empezar |

---

## 4. Nivel 3 — ⏹ Stop Project (todas las tareas de un proyecto)

### 4.1 Qué hace

Revoca **TODAS** las tareas activas y pendientes de un proyecto. Limpia los
side-effects de cada una (rollback por tarea). Ideal cuando el usuario quiere
"empezar de cero" en un proyecto.

### 4.2 Endpoint

```python
# backend/app/api/v1/admin.py

@router.post("/projects/{project_id}/stop")
async def stop_project_pipeline(project_id: UUID):
    """
    Detiene TODAS las tareas del pipeline de un proyecto.
    
    1. Busca el PipelineRun activo
    2. Revoca todas sus PipelineTasks (activas + pendientes)
    3. Rollback de cada tarea
    4. Limpia logs de Redis
    """
    from app.core.celery_app import celery_app

    # 1. Buscar run activo
    run = await db.execute(
        select(PipelineRun).where(
            PipelineRun.project_id == project_id,
            PipelineRun.status == "running"
        )
    ).scalar_one_or_none()

    if not run:
        # Sin run activo, pero revocamos cualquier tarea suelta
        inspector = celery_app.control.inspect()
        active = inspector.active() or {}
        revoked = 0
        for worker, tasks in active.items():
            for task in tasks:
                celery_app.control.revoke(task['id'], terminate=True)
                revoked += 1
        return {"status": "stopped", "active_run": None, "tasks_revoked": revoked}

    # 2. Revocar todas las tareas del run
    tasks = await db.execute(
        select(PipelineTask).where(PipelineTask.run_id == run.id)
    ).scalars().all()

    results = []
    for task in tasks:
        if task.status in ("queued", "running"):
            celery_app.control.revoke(task.celery_task_id, terminate=True)
            task.status = "cancelled"

            # Rollback si corresponde
            if task.document_id and task.doc_estado_before:
                await db.execute(
                    text("UPDATE documentos SET estado = :estado WHERE id = :did"),
                    {"estado": task.doc_estado_before, "did": task.document_id}
                )
            results.append({
                "task_id": task.celery_task_id,
                "status": "cancelled",
                "doc_rolled_back": str(task.document_id) if task.document_id else None,
            })

    # 3. Marcar run como cancelado
    run.status = "cancelled"
    await db.commit()

    # 4. Limpiar logs de Redis
    try:
        import redis.asyncio as _aredis, os as _os
        r = _aredis.from_url(_os.getenv("REDIS_URL", "redis://redis:6379/0"))
        await r.delete(f"pipeline_logs:{project_id}")
        await r.close()
    except Exception:
        pass

    return {
        "status": "stopped",
        "run_id": str(run.id),
        "tasks_cancelled": len(results),
        "details": results,
    }
```

### 4.3 Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `backend/app/api/v1/admin.py` | `stop_project_pipeline()` |
| `backend/app/api/v1/pipeline.py` | `run_pipeline_orchestrated()` → crear `PipelineRun` |

---

## 5. Nivel 4 — ☠️ Kill All Workers

### 5.1 Qué hace

Fuerza bruta. Detiene todos los workers Celery. Solo para emergencias (workers
colgados, memory leak, loop infinito).

### 5.2 Endpoint

```python
# backend/app/api/v1/admin.py

@router.post("/workers/kill-all")
async def kill_all_workers():
    """
    ☠️ Emergencia: detiene TODOS los workers Celery.
    
    Envía broadcast de shutdown a todos los workers.
    docker-compose los reiniciará automáticamente (restart: unless-stopped).
    """
    from app.core.celery_app import celery_app

    # 1. Purge queues (tareas pendientes)
    celery_app.control.purge()

    # 2. Shutdown broadcast (SIGTERM a todos los workers)
    celery_app.control.broadcast('shutdown')

    # 3. Revocar tareas activas
    inspector = celery_app.control.inspect()
    active = inspector.active() or {}
    revoked = 0
    for worker, tasks in active.items():
        for task in tasks:
            celery_app.control.revoke(task['id'], terminate=True, signal='SIGKILL')
            revoked += 1

    return {
        "status": "killed",
        "workers_shutdown": True,
        "tasks_revoked": revoked,
        "warning": "Los workers se reiniciarán automáticamente (docker restart policy)",
    }
```

---

## 6. 🔄 Restart — Reiniciar tareas (desde cero y resumible)

### 6.1 Dos modos de restart

| Modo | Cuándo | Comportamiento |
|------|--------|---------------|
| **Reset** | El usuario quiere re-ejecutar desde cero | Limpia todo lo de la tarea anterior y empieza de nuevo |
| **Resume** | La tarea fue cancelada a mitad, DB no se actualizó completamente | Detecta dónde se quedó, limpia el paso parcial, continúa desde ahí |

### 6.2 El problema del estado parcial

Cuando cancelás una tarea a mitad de ejecución, la DB puede quedar así:

```
process_document_agents_a(doc_id="abc"):
  ✅ Step 1: a1_build_population_context  → INSERT population_contexts  (OK)
  ✅ Step 2: _ensure_segmented            → segmentos verificados       (OK)
  ✅ Step 3: _anchor_segments             → first_10, start_char, end_char  (OK)
  ⚠️ Step 4: a2_identify_process          → parafrasis PARCIAL         (3 de 15 segs)
  ❌ Step 5: _extract_prime_mover         → NO ejecutado
  ❌ Step 6: a3_make_sense                → NO ejecutado
  ❌ Step 7: _mark_doc_ready              → NO ejecutado

Resultado: documento en estado "procesando", 3 segmentos con parafrasis,
           el resto sin parafrasis. La DB es inconsistente.
```

### 6.3 Estrategia: TaskCheckpoint + limpieza por paso

Cada paso de la tarea escribe un checkpoint **antes** de ejecutarse:
- `status="in_progress"` al empezar
- `status="completed"` al terminar

Si la tarea se cancela, los pasos `in_progress` son los que quedaron a medias.
Al resumir, se limpian esos pasos y se re-ejecutan.

```python
# backend/app/models/domain/pipeline_run.py — añadir

class TaskStepCheckpoint(Base, TimestampMixin):
    """Checkpoint por paso dentro de una tarea. Permite resumir tras cancel."""

    __tablename__ = "task_step_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    pipeline_task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pipeline_tasks.id"))
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documentos.id"))

    step_name: Mapped[str] = mapped_column(String(100))
    # "a1_population_context" | "segmentation" | "a2_identify_process" |
    # "a3_make_sense" | "b2_open_code" | "b3_hypotheses" | etc.

    status: Mapped[str] = mapped_column(String(20), default="in_progress")
    # "in_progress" | "completed" | "failed"

    # Snapshot de lo que se insertó en este paso (para limpieza)
    affected_rows: Mapped[dict] = mapped_column(JSONB, default=dict)
    # Ej: {"segmentos_inserted": ["id1", "id2", ...], "table": "segmentos"}
```

### 6.4 Lógica de resume en el worker

```python
# workers/heavy/tasks.py — modificar process_document_agents_a

def process_document_agents_a(
    self, doc_id: str, project_id: str,
    resume_from_step: str | None = None  # ← NUEVO parámetro
) -> dict:
    """
    Procesa un documento con agentes A.
    Si resume_from_step != None, salta los pasos ya completados
    y limpia los pasos que quedaron in_progress antes de re-ejecutarlos.
    """
    s = SessionLocal()
    try:
        # ── Detectar punto de resume ──
        completed_steps = set()
        dirty_steps = set()  # pasos que estaban in_progress → hay que limpiar

        if resume_from_step:
            # Cargar checkpoints existentes para esta tarea+documento
            checkpoints = s.execute(
                text(
                    "SELECT step_name, status, affected_rows "
                    "FROM task_step_checkpoints "
                    "WHERE document_id = :did "
                    "ORDER BY creado_en"
                ),
                {"did": doc_id},
            ).fetchall()

            for cp in checkpoints:
                if cp[1] == "completed":
                    completed_steps.add(cp[0])
                elif cp[1] == "in_progress":
                    dirty_steps.add(cp[0])
                    # Limpiar datos parciales de este paso
                    _cleanup_step(s, cp[0], cp[2], doc_id)

        # ── Step 1: Population Context ──
        step = "a1_population_context"
        if step not in completed_steps:
            _checkpoint(s, doc_id, step, "in_progress")
            a1_build_population_context(s, doc_id, project_id)
            _checkpoint(s, doc_id, step, "completed")

        # ── Step 2: Segmentation ──
        step = "segmentation"
        if step not in completed_steps:
            _checkpoint(s, doc_id, step, "in_progress")
            _ensure_segmented(s, doc_id)
            _checkpoint(s, doc_id, step, "completed")

        # ── Step 3: Anchoring ──
        step = "anchoring"
        if step not in completed_steps:
            _checkpoint(s, doc_id, step, "in_progress")
            _anchor_segments(s, doc_id)
            _checkpoint(s, doc_id, step, "completed")

        # ── Step 4: Process Identification ──
        step = "a2_identify_process"
        if step not in completed_steps:
            _checkpoint(s, doc_id, step, "in_progress")
            a2_identify_process(s, doc_id, project_id)
            _checkpoint(s, doc_id, step, "completed")

        # ── Step 5: Prime Mover ──
        step = "extract_prime_mover"
        if step not in completed_steps:
            _checkpoint(s, doc_id, step, "in_progress")
            _extract_prime_mover(s, doc_id, project_id)
            _checkpoint(s, doc_id, step, "completed")

        # ── Step 6: Sense Making ──
        step = "a3_make_sense"
        if step not in completed_steps:
            _checkpoint(s, doc_id, step, "in_progress")
            a3_make_sense(s, doc_id, project_id)
            _checkpoint(s, doc_id, step, "completed")

        # ── Step 7: Mark Ready ──
        _mark_doc_ready(s, doc_id)

        s.commit()
        return {"status": "completed", "doc_id": doc_id}

    except Exception as e:
        s.rollback()
        _mark_doc_error(s, doc_id, str(e))
        raise
    finally:
        s.close()


def _checkpoint(session, doc_id: str, step: str, status: str):
    """Escribe un checkpoint de paso."""
    session.execute(
        text(
            "INSERT INTO task_step_checkpoints "
            "(id, document_id, step_name, status) "
            "VALUES (gen_random_uuid(), :did, :step, :status)"
        ),
        {"did": doc_id, "step": step, "status": status},
    )
    session.commit()  # commit inmediato para que sea visible tras crash


def _cleanup_step(session, step: str, affected_rows: dict, doc_id: str):
    """Limpia datos parciales de un paso que quedó in_progress."""
    if step == "segmentation":
        # Eliminar segmentos insertados parcialmente
        session.execute(
            text("DELETE FROM segmentos WHERE documento_id = :did"),
            {"did": doc_id},
        )
    elif step == "a2_identify_process":
        # Limpiar parafrasis parciales
        session.execute(
            text("UPDATE segmentos SET parafrasis = NULL WHERE documento_id = :did"),
            {"did": doc_id},
        )
    elif step == "a3_make_sense":
        # Limpiar document_processes parciales
        session.execute(
            text("DELETE FROM document_processes WHERE documento_id = :did"),
            {"did": doc_id},
        )
    session.commit()
```

### 6.5 Endpoint de resume

```python
# backend/app/api/v1/admin.py

@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str):
    """
    Reanuda una tarea cancelada desde donde se quedó.
    
    A diferencia de restart (que empieza de cero), resume:
    - Detecta los pasos ya completados (vía TaskStepCheckpoint)
    - Limpia los pasos que quedaron in_progress
    - Continúa desde el primer paso no completado
    - Sobrescribe cualquier dato parcial del intento anterior
    """
    from app.models.domain.pipeline_run import PipelineTask, TaskStepCheckpoint
    from app.core.celery_app import celery_app

    task_record = await db.execute(
        select(PipelineTask).where(PipelineTask.celery_task_id == task_id)
    ).scalar_one_or_none()

    if not task_record:
        raise HTTPException(404, "Task not found")

    # Encontrar el último paso completado
    last_checkpoint = await db.execute(
        select(TaskStepCheckpoint).where(
            TaskStepCheckpoint.pipeline_task_id == task_record.id,
            TaskStepCheckpoint.status == "completed"
        ).order_by(TaskStepCheckpoint.creado_en.desc()).limit(1)
    ).scalar_one_or_none()

    resume_from = last_checkpoint.step_name if last_checkpoint else None

    # Re-disparar la tarea en modo resume
    new_task = celery_app.send_task(
        task_record.task_name,
        args=[str(task_record.document_id), str(task_record.run_id)],
        kwargs={"resume_from_step": resume_from},
        queue="heavy",
    )

    return {
        "status": "resumed",
        "old_task_id": task_id,
        "new_task_id": new_task.id,
        "resume_from_step": resume_from,
        "note": "La tarea continuará desde el paso '{}' y sobrescribirá datos parciales".format(
            resume_from or "inicio"
        ),
    }
```

### 6.6 Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `backend/app/models/domain/pipeline_run.py` | Añadir `TaskStepCheckpoint` |
| `workers/heavy/tasks.py` | `process_document_agents_a()` → soporte `resume_from_step` + checkpoints |
| `workers/nlp/tasks.py` | `segmentar_documento()` → soporte `resume_from_step` + checkpoints |
| `workers/fast/tasks.py` | `punctuate_text()` → soporte `resume_from_step` + checkpoints |
| `backend/app/api/v1/admin.py` | Nuevo endpoint `POST /tasks/{task_id}/resume` |
| `backend/app/api/v1/pipeline.py` | `run_pipeline_orchestrated()` → aceptar `resume_from_step` |

---

## 7. Frontend: Overlay de Pipeline rediseñado

### 7.1 Estado actual

El overlay muestra:
- 7 stages con íconos (workers → segment → agents → categories → saturate → playground → done)
- Un botón "⏹ Detener todos los workers"
- Un panel de live logs a la derecha

### 7.2 Rediseño propuesto

```
┌─────────────────────────────────────────────────────────────────────┐
│  🎯 Pipeline — Proyecto "Entrevistas Rappi"                         │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  ┌─────────────────────────────┐  ┌──────────────────────────────┐  │
│  │  STAGES                     │  │  LIVE LOG                    │  │
│  │                             │  │                               │  │
│  │  ✅ Workers        0.5s     │  │  14:32:01  [nlp] Segmentando │  │
│  │  ✅ Segment        12.3s    │  │  doc_03... 45 segmentos      │  │
│  │  ⏳ Agents         45.2s ←  │  │  14:32:15  [heavy] Agente A1 │  │
│  │  ⬜ Categories              │  │  doc_03... pop. context     │  │
│  │  ⬜ Saturate                │  │  14:32:28  [heavy] Agente A2 │  │
│  │  ⬜ Playground              │  │  doc_03... identificando... │  │
│  │  ⬜ Done                    │  │  14:32:45  [fast] Punctuator │  │
│  │                             │  │  doc_01... mejorando punct. │  │
│  └─────────────────────────────┘  └──────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  DOCUMENTOS                                                  │   │
│  │  ┌──────────────────────────────────────────────────────────┐│   │
│  │  │ entrevista_01.txt  ⏳ Agentes    12 seg · 3 códigos      ││   │
│  │  │ entrevista_02.txt  ✅ Listo      45 seg · 8 códigos      ││   │
│  │  │ entrevista_03.txt  ⏳ Segmentando 0 seg · 0 códigos      ││   │
│  │  └──────────────────────────────────────────────────────────┘│   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  ⏹ DETENER PIPELINE    ⏸ CANCELAR TAREA    🔄 REINTENTAR    │   │
│  │  (detiene todo)         (tarea actual)      (fallidas)       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  [Cerrar]                                                           │
└─────────────────────────────────────────────────────────────────────┘
```

### 7.3 Estados visuales por documento

```
🟢 Listo       — doc.estado === "listo" y tiene códigos
🟡 Procesando  — doc.estado === "segmentando" | "procesando"
⚪ Pendiente   — doc.estado === "segmentado" | "crudo" (con texto)
🔴 Error       — doc.estado === "error"
⏹ Cancelado   — doc.estado === "crudo" (rolled back)
```

### 7.4 Botones nuevos en el overlay

```typescript
// frontend/src/pages/Project.tsx — modificaciones

const [runningTasks, setRunningTasks] = useState<PipelineTask[]>([]);
const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);

// Botón: Detener Pipeline (Nivel 3)
async function handleStopPipeline() {
    abortRef.current = true;
    setStoppingWorkers(true);
    await fetch(`/api/v1/admin/projects/${id}/stop`, { method: "POST", headers: authHeader() });
    setStoppingWorkers(false);
    refreshAll();
}

// Botón: Cancelar tarea actual (Nivel 2)
async function handleCancelCurrentTask() {
    if (!currentTaskId) return;
    await fetch(`/api/v1/admin/tasks/${currentTaskId}/cancel`, { method: "POST", headers: authHeader() });
    setCurrentTaskId(null);
    refreshAll();
}

// Botón: Reintentar fallidas (Restart)
async function handleRestartFailed() {
    await fetch(`/api/v1/admin/projects/${id}/pipeline/restart-failed`, { method: "POST", headers: authHeader() });
    refreshAll();
}
```

### 7.5 Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `frontend/src/pages/Project.tsx` | Overlay rediseñado + 3 botones nuevos + tracking de tasks |
| `frontend/src/api/client.ts` | Nuevos métodos: `stopPipeline()`, `cancelTask()`, `restartFailed()` |

---

## 8. Spillover Effects (efectos colaterales)

### 8.1 Base de datos

| Acción | Efecto en DB | Mitigación |
|--------|-------------|------------|
| Cancelar `segmentar_documento` | Segmentos parcialmente insertados | La tarea hace DELETE + INSERT en una transacción. Si se cancela → rollback automático |
| Cancelar `process_document_agents_a` | Categorías parcialmente creadas, `document_processes` a medias | Guardar `doc_estado_before`. Si cancelado → restaurar estado y eliminar inserts de esta tarea |
| Cancelar `punctuate_text` | `metadatos.texto_puntuado` a medias | Guardar `metadatos` antes de modificar. Restaurar si cancelado |
| Cancelar LangGraph `invoke_graph` | Checkpoint corrupto | LangGraph PostgresSaver maneja transacciones. Si se corta → checkpoint se descarta |

### 8.2 Celery

| Acción | Efecto | Mitigación |
|--------|--------|------------|
| `revoke(task_id, terminate=True)` | El worker recibe SIGTERM | La tarea debe capturar la señal y hacer cleanup en `finally` |
| `control.purge()` | Tareas pendientes eliminadas | Las tareas no empezaron → sin side-effects. Solo limpiar tracking. |
| `control.broadcast('shutdown')` | Workers se detienen | docker-compose `restart: unless-stopped` los reinicia |

### 8.3 LangGraph

| Acción | Efecto | Mitigación |
|--------|--------|------------|
| Cancelar mid-graph | Checkpoint parcial | El `PostgresSaver` wrappea en transacción. Si se interrumpe → no se commitea |
| Reanudar después de cancel | Estado inconsistente | `invoke_graph()` verifica `thread_id` existente y reanuda desde último checkpoint válido |

### 8.4 Redis

| Acción | Efecto | Mitigación |
|--------|--------|------------|
| Cancelar proyecto | Logs en `pipeline_logs:{pid}` | `stop_project_pipeline()` hace `DELETE` de la key |
| Cancelar todo | Pub/sub channels activos | Los workers publican heartbeats. Si el subscriber se va → Redis limpia solo |

### 8.5 Agentes (bucles agentic)

| Acción | Efecto | Mitigación |
|--------|--------|------------|
| Abort durante SelfRefinement | LLM generando, bucle activo | `abort_event.is_set()` → `raise AgentAbortedError` → `finally` limpia |
| Abort durante ReAct | Tool en ejecución, pasos pendientes | `_check_abort()` antes de cada step y tool call |
| Abort durante PlanExecutor | Plan a medio ejecutar | Guardar `executed_steps` en el estado. Si abort → se sabe qué pasos se completaron |

---

## 9. Plan de Implementación

### Fase A: Infraestructura (Día 1-2)

```
[ ] Crear backend/app/models/domain/pipeline_run.py
[ ] Crear backend/app/api/v1/admin.py (esqueleto con stop/kill/restart)
[ ] Crear migración Alembic para PipelineRun + PipelineTask
[ ] Registrar admin router en main.py
[ ] Test: POST /api/v1/admin/workers/heavy/stop → 200 OK
```

### Fase B: Streaming + Abort LLM (Día 2-3)

```
[ ] Añadir chat_stream() a TogetherLLM
[ ] Añadir abort_event a BaseAgent
[ ] Propagar abort_event a SelfRefinementLoop, ReactRunner, PlanExecutor
[ ] Modificar workers LLMClient para soportar streaming + abort
[ ] Test unitario: abort_event.is_set() → stream.close() → ahorro de tokens
[ ] Test integración: iniciar tarea, abortar a los 2s, verificar DB limpia
```

### Fase C: Tracking + Rollback (Día 3-4)

```
[ ] Modificar run_pipeline_orchestrated() → crear PipelineRun + PipelineTask
[ ] Modificar process_document_agents_a() → guardar doc_estado_before
[ ] Modificar segmentar_documento() → guardar doc_estado_before
[ ] Implementar cancel_task() con rollback
[ ] Implementar stop_project_pipeline() con rollback masivo
[ ] Test: correr pipeline, cancelar a mitad, verificar docs en estado original
```

### Fase D: Restart (Día 4-5)

```
[ ] Implementar restart_task()
[ ] Implementar restart_failed_tasks()
[ ] Test: cancelar tarea → restart → verificar que se completa
[ ] Test: simular fallo → restart_failed → verificar que solo reintenta fallidas
```

### Fase E: Frontend (Día 5-6)

```
[ ] Rediseñar overlay con sección de documentos + live tasks
[ ] Añadir botones: Detener Pipeline, Cancelar Tarea, Reintentar Fallidas
[ ] Añadir currentTaskId tracking
[ ] Test E2E: clickear Detener → verificar workers limpios → reintentar → completar
```

---

## 10. Tests

### 10.1 Unitarios

```python
# tests/unit/test_admin.py

async def test_stop_project_revokes_tasks():
    """POST /admin/projects/{pid}/stop → revoca tareas + rollback"""
    ...

async def test_cancel_task_rollback():
    """POST /admin/tasks/{tid}/cancel → doc vuelve a estado anterior"""
    ...

async def test_restart_failed_only_retries_failed():
    """POST /admin/projects/{pid}/pipeline/restart-failed → solo failed/cancelled"""
    ...

async def test_kill_all_workers_broadcasts_shutdown():
    """POST /admin/workers/kill-all → purge + broadcast shutdown"""
    ...
```

### 10.2 Integración

```python
# tests/test_integration.py

async def test_abort_llm_mid_generation():
    """Iniciar chat_stream, set abort_event a los 100ms → aborted=True"""
    ...

async def test_pipeline_cancel_midway_db_clean():
    """Pipeline con 3 docs, cancelar después de 1 completado → DB consistente"""
    ...

async def test_agent_abort_propagates_to_sub_agents():
    """SelfRefinementLoop con abort_event → AgentAbortedError → cleanup"""
    ...
```

### 10.3 E2E (frontend)

```bash
# Cypress o Playwright
it('detiene el pipeline y limpia el estado', () => {
    cy.visit('/projects/test-id')
    cy.get('[data-testid="run-pipeline"]').click()
    cy.wait(3000)  # dejar que empiece
    cy.get('[data-testid="stop-pipeline"]').click()
    cy.contains('⏹ Pipeline cancelado')
    cy.get('[data-testid="doc-status"]').should('not.contain', '⏳')
})
```

---

## 11. Resumen de archivos

### Nuevos (4)

| Archivo | Descripción |
|---------|-------------|
| `backend/app/models/domain/pipeline_run.py` | PipelineRun + PipelineTask models |
| `backend/app/api/v1/admin.py` | Endpoints stop/cancel/kill/restart |
| `backend/app/agents/exceptions.py` | AgentAbortedError |
| `migrations/versions/xxxx_pipeline_run.py` | Migración Alembic |

### Modificados (11)

| Archivo | Cambio |
|---------|--------|
| `backend/app/core/together_client.py` | `chat_stream()` |
| `backend/app/agents/base.py` | `abort_event` + `_check_abort()` |
| `backend/app/agents/self_refiner.py` | Propagar abort_event |
| `backend/app/agents/react_runner.py` | Propagar abort_event |
| `backend/app/agents/plan_executor.py` | Propagar abort_event |
| `backend/app/api/v1/pipeline.py` | Crear PipelineRun + PipelineTask |
| `backend/app/main.py` | Registrar admin router |
| `workers/heavy/tasks.py` | `doc_estado_before` + `AbortableTask` |
| `workers/nlp/tasks.py` | `doc_estado_before` + `AbortableTask` |
| `workers/fast/tasks.py` | `doc_estado_before` + `AbortableTask` |
| `frontend/src/pages/Project.tsx` | Overlay + 3 botones + task tracking |
