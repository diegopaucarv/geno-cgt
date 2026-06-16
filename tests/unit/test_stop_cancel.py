"""Tests para el sistema de stop/cancel/restart/resume."""


# ═══════════════════════════════════════════════════════════════════════
# Model tests (no Celery needed)
# ═══════════════════════════════════════════════════════════════════════


def test_pipeline_run_model_fields():
    """PipelineRun tiene los campos correctos."""
    from app.models.domain.pipeline_run import PipelineRun

    assert hasattr(PipelineRun, "__tablename__")
    assert PipelineRun.__tablename__ == "pipeline_runs"
    assert hasattr(PipelineRun, "project_id")
    assert hasattr(PipelineRun, "status")
    assert hasattr(PipelineRun, "triggered_by")
    assert hasattr(PipelineRun, "summary")


def test_pipeline_task_model_fields():
    """PipelineTask tiene campos para tracking y rollback."""
    from app.models.domain.pipeline_run import PipelineTask

    assert PipelineTask.__tablename__ == "pipeline_tasks"
    assert hasattr(PipelineTask, "celery_task_id")
    assert hasattr(PipelineTask, "doc_estado_before")
    assert hasattr(PipelineTask, "segments_before")
    assert hasattr(PipelineTask, "codes_before")
    assert hasattr(PipelineTask, "status")
    assert hasattr(PipelineTask, "queue")


def test_task_step_checkpoint_model_fields():
    """TaskStepCheckpoint permite resume por paso."""
    from app.models.domain.pipeline_run import TaskStepCheckpoint

    assert TaskStepCheckpoint.__tablename__ == "task_step_checkpoints"
    assert hasattr(TaskStepCheckpoint, "step_name")
    assert hasattr(TaskStepCheckpoint, "status")
    assert hasattr(TaskStepCheckpoint, "affected_rows")
    assert hasattr(TaskStepCheckpoint, "pipeline_task_id")
    assert hasattr(TaskStepCheckpoint, "document_id")


# ═══════════════════════════════════════════════════════════════════════
# Exception tests
# ═══════════════════════════════════════════════════════════════════════


def test_agent_aborted_error():
    from app.agents.exceptions import AgentAbortedError

    err = AgentAbortedError("test abort")
    assert str(err) == "test abort"
    assert err.message == "test abort"


def test_task_cancelled_error():
    from app.agents.exceptions import TaskCancelledError

    err = TaskCancelledError(task_id="task-123")
    assert err.task_id == "task-123"
    assert "Task cancelled" in str(err)


# ═══════════════════════════════════════════════════════════════════════
# TogetherLLM chat_stream tests
# ═══════════════════════════════════════════════════════════════════════


def test_together_llm_has_chat_stream():
    """TogetherLLM tiene el método chat_stream."""
    from app.core.together_client import TogetherLLM

    client = TogetherLLM()
    assert hasattr(client, "chat_stream")
    assert callable(client.chat_stream)


def test_chat_stream_signature():
    """chat_stream acepta abort_event."""
    import inspect

    from app.core.together_client import TogetherLLM

    sig = inspect.signature(TogetherLLM.chat_stream)
    params = list(sig.parameters.keys())
    assert "abort_event" in params
    assert "model" in params
    assert "messages" in params
    assert "stream" not in params  # stream=True se setea internamente


# ═══════════════════════════════════════════════════════════════════════
# Admin router structure tests
# ═══════════════════════════════════════════════════════════════════════


def test_admin_router_has_required_endpoints():
    """El admin router expone todos los endpoints necesarios."""
    from app.api.v1.admin import router

    paths = {r.path for r in router.routes}

    required = {
        "/api/v1/admin/workers/{worker_name}/stop",
        "/api/v1/admin/workers/status",
        "/api/v1/admin/workers/kill-all",
        "/api/v1/admin/projects/{project_id}/stop",
        "/api/v1/admin/tasks/{task_id}/cancel",
        "/api/v1/admin/tasks/{task_id}/restart",
        "/api/v1/admin/tasks/{task_id}/resume",
        "/api/v1/admin/projects/{project_id}/pipeline/restart-failed",
    }

    missing = required - paths
    assert not missing, f"Missing endpoints: {missing}"


# ═══════════════════════════════════════════════════════════════════════
# Main.py integration test
# ═══════════════════════════════════════════════════════════════════════


def test_main_registers_admin_router():
    """main.py incluye el admin router."""
    from app.main import app

    admin_routes = [r for r in app.routes if hasattr(r, "path") and "/admin" in r.path]
    assert len(admin_routes) > 0, "Admin router not registered in main.py"
    paths = {r.path for r in admin_routes}
    assert "/api/v1/admin/workers/{worker_name}/stop" in paths
