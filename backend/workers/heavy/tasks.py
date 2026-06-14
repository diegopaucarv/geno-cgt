@celery_app.task(queue="heavy", time_limit=3600)
def run_full_qualitative_analysis(project_id: int):
    # Orquesta múltiples sub-tareas, llama a LangGraph, etc.
    return {"project_id": project_id, "status": "completed"}
