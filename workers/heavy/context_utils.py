"""
Context injection utilities for agent variables.

Conditionally injects chosen_concern, chosen_population, research_question, and
population_context from the project's HITL gate decisions and population data
into agent variables dicts before passing them to llm_client.run_agent().
"""

from __future__ import annotations

from sqlalchemy import text


def inject_chosen_context(project_id: str, session, base_variables: dict) -> dict:
    """
    Conditionally injects chosen_concern, chosen_population, research_question,
    and population_context into agent variables.

    Only injects non-empty values if the researcher has made a decision in the
    HITL gate and stored it in proyectos. Falls back to empty strings so agents
    can detect "not chosen yet."

    Args:
        project_id: UUID del proyecto.
        session: SQLAlchemy session activa.
        base_variables: dict base de variables para el agente.

    Returns:
        Copia de base_variables con chosen_concern, chosen_population,
        research_question, y population_context inyectados.
    """
    proyecto = session.execute(
        text(
            "SELECT chosen_concern, chosen_population, supuesto_poblacional, "
            "population_assumption FROM proyectos WHERE id = :pid"
        ),
        {"pid": project_id},
    ).fetchone()

    variables = dict(base_variables)

    # chosen_concern (condicional)
    variables["chosen_concern"] = (
        proyecto.chosen_concern if proyecto and proyecto.chosen_concern else ""
    )

    # chosen_population (condicional)
    variables["chosen_population"] = (
        proyecto.chosen_population if proyecto and proyecto.chosen_population else ""
    )

    # research_question (siempre disponible del supuesto_poblacional)
    variables["research_question"] = (
        proyecto.supuesto_poblacional
        if proyecto and proyecto.supuesto_poblacional
        else ""
    )

    # population_context (desde el último population_contexts)
    if proyecto:
        pop_ctx = session.execute(
            text(
                "SELECT surprising_details, language_patterns, data_production_context "
                "FROM population_contexts WHERE proyecto_id = :pid "
                "ORDER BY version DESC LIMIT 1"
            ),
            {"pid": project_id},
        ).fetchone()
        if pop_ctx:
            variables["population_context"] = (
                f"Surprising details: {pop_ctx.surprising_details}\n"
                f"Language patterns: {pop_ctx.language_patterns}\n"
                f"Data production context: {pop_ctx.data_production_context}"
            )
        else:
            variables["population_context"] = ""
    else:
        variables["population_context"] = ""

    return variables
