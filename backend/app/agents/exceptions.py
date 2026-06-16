"""Excepciones para la capa agencial."""


class AgentAbortedError(Exception):
    """El agente fue abortado por el usuario (abort_event.is_set())."""

    def __init__(self, message: str = "Agent aborted by user"):
        super().__init__(message)
        self.message = message


class TaskCancelledError(Exception):
    """La tarea Celery fue cancelada (SIGTERM recibido)."""

    def __init__(self, task_id: str = "", message: str = "Task cancelled"):
        super().__init__(message)
        self.task_id = task_id
        self.message = message
