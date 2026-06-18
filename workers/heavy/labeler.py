"""
B2 — Pattern Labeler (PRO + SelfRefinement loop por concepto).

Itera CONCEPTO POR CONCEPTO: para cada grupo de incidentes,
propone UNA etiqueta, la evalúa con el critic, y refina si es necesario.
Máx 3 iteraciones por grupo. PRO para generar, FLASH para criticar.

See AGENTES.md §pattern_labeler for I/O spec.
"""

from __future__ import annotations

import json
import logging

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def _build_assistant_message(content: str, response: dict) -> dict:
    """Preserva reasoning_content para DeepSeek V4 Pro."""
    msg: dict = {"role": "assistant", "content": content}
    reasoning = response.get("_reasoning_content")
    if reasoning:
        msg["reasoning_content"] = reasoning
    return msg


def b2_label_groups(proyecto_id: str) -> dict:
    """Propone etiquetas para grupos de incidentes — iterando concepto por concepto.

    Para CADA grupo:
    1. Propone UNA etiqueta con el pattern_labeler (PRO).
    2. El label_critic (FLASH) evalúa ESA etiqueta contra los incidentes fuente.
    3. Si el critic no encuentra issues → etiqueta aprobada, siguiente grupo.
    4. Si encuentra issues → feedback al proposer, repetir (máx 3 iteraciones).
    5. Si tras 3 iteraciones aún hay issues → conservar última versión.

    Args:
        proyecto_id: UUID del proyecto.

    Returns:
        dict con:
          - groups_processed: int
          - labels_created: int
          - labels_approved: int
          - labels_modified: int
          - labels_forced: int (siempre 0, sin veredictos)
          - iterations: int (total de iteraciones entre todos los grupos)
    """
    session = SessionLocal()
    try:
        # ── Cargar grupos sin etiqueta ─────────────────────────────
        rows = session.execute(
            text(
                "SELECT id, incident_ids_json "
                "FROM incident_groups "
                "WHERE proyecto_id = :pid AND status = 'open' "
                "ORDER BY creado_en"
            ),
            {"pid": proyecto_id},
        ).fetchall()

        if not rows:
            logger.info("B2: No open groups to label for project %s", proyecto_id)
            return {
                "groups_processed": 0,
                "labels_created": 0,
                "labels_approved": 0,
                "labels_modified": 0,
                "labels_forced": 0,
                "iterations": 0,
            }

        # ── Construir grupos con incidentes ────────────────────────
        groups = []
        for r in rows:
            gid = str(r[0])
            incident_ids = r[1] if r[1] else []

            # Cargar incidentes del grupo
            inc_rows = session.execute(
                text(
                    "SELECT id, jot_text, preguntas_glaser_json "
                    "FROM extracted_incidents "
                    "WHERE id::text = ANY(:ids)"
                ),
                {"ids": incident_ids},
            ).fetchall()

            incidents = []
            for ir in inc_rows:
                glaser = ir[2] or {}
                incidents.append(
                    {
                        "id": str(ir[0]),
                        "jot": ir[1] or "",
                        "what_is_happening": glaser.get("what_is_happening", ""),
                        "what_category": glaser.get("what_category", ""),
                    }
                )

            groups.append(
                {
                    "group_id": gid,
                    "incidents": incidents,
                }
            )

        # ── Obtener códigos existentes para evitar duplicados ──────
        existing = session.execute(
            text("SELECT nombre FROM categorias WHERE proyecto_id = :pid"),
            {"pid": proyecto_id},
        ).fetchall()
        existing_labels = (
            "\n".join(f"- {e[0]}" for e in existing)
            if existing
            else "(sin códigos existentes)"
        )

        # ── Obtener objeto de estudio ──────────────────────────────
        obj_row = session.execute(
            text("SELECT object_of_study FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        object_of_study = (
            obj_row[0] if obj_row and obj_row[0] else "comportamiento humano"
        )

        # Fetch operational question from Nemotron output
        pa_row = session.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": proyecto_id},
        ).fetchone()
        pa_data = pa_row[0] if pa_row and pa_row[0] else {}
        rq_data = (
            pa_data.get("research_question", {}) if isinstance(pa_data, dict) else {}
        )
        operational_question = rq_data.get("operational_question", "")

        # Read coding_style_instruction from project config
        coding_style_instruction = (
            pa_data.get("coding_style_instruction", "")
            if isinstance(pa_data, dict)
            else ""
        )
        if not coding_style_instruction:
            from app.core.coding_styles import get_default_style_instruction

            coding_style_instruction = get_default_style_instruction()

        # ── Iterar CONCEPTO POR CONCEPTO ───────────────────────────
        max_iterations = 3
        total_iterations = 0
        labels_created = 0
        labels_approved = 0
        labels_modified = 0

        for group in groups:
            group_id = group["group_id"]
            # Wrap single group as array — pattern_labeler expects array input
            group_json = json.dumps([group], indent=2, ensure_ascii=False)
            history: list[dict] = []
            previous_labels_json: str = ""
            accumulated_feedback: list[str] = []
            final_label: dict = {}
            label_converged = False

            for iteration in range(1, max_iterations + 1):
                total_iterations += 1

                # 1. PROPOSE (PRO) — ONE group → ONE label
                gen_vars = {
                    "groups_json": group_json,
                    "object_of_study": object_of_study,
                    "existing_labels": existing_labels,
                    "operational_question": operational_question
                    or "(not yet generated)",
                    "coding_style_instruction": coding_style_instruction,
                }

                # G15: Pass own previous output so labeler can do targeted refinement
                if previous_labels_json:
                    gen_vars["previous_labels"] = previous_labels_json

                # G16: Accumulate ALL feedback across iterations, not just last
                if accumulated_feedback:
                    gen_vars["accumulated_feedback"] = "\n\n---\n".join(
                        accumulated_feedback
                    )

                gen_response = llm.run_agent(
                    agent_id="fb_pattern_labeler",
                    variables=gen_vars,
                )

                gen_text = json.dumps(gen_response, ensure_ascii=False)
                history.append(_build_assistant_message(gen_text, gen_response))

                proposed_labels = gen_response.get("proposed_labels", [])
                if not proposed_labels:
                    logger.warning(
                        "B2 group %s iter %d: No labels proposed. Response keys: %s, raw (300 chars): %s",
                        group_id[:8],
                        iteration,
                        list(gen_response.keys())
                        if isinstance(gen_response, dict)
                        else type(gen_response).__name__,
                        str(gen_response)[:300],
                    )
                    break

                # Take the label for THIS group (group_index 0 since single group)
                label_info = proposed_labels[0] if proposed_labels else {}
                final_label = label_info

                # G15: Save own output for next iteration's targeted refinement
                previous_labels_json = json.dumps(
                    {"proposed_labels": [label_info]}, ensure_ascii=False
                )[:4000]

                # 2. CRITIC (FLASH) — ONE label against ONE group's incidents
                label_json = json.dumps(label_info, ensure_ascii=False)
                critic_response = llm.run_agent(
                    agent_id="fb_label_critic",
                    variables={
                        "output_to_evaluate": label_json,
                        "source_incidents": group_json,
                    },
                    temperature=0.1,
                )

                issues = critic_response.get("issues", [])

                logger.info(
                    "B2 group=%s iter=%d: label=%s, issues=%d",
                    group_id[:8],
                    iteration,
                    label_info.get("label", "?"),
                    len(issues),
                )

                if not issues:
                    # Label is good — move to next group
                    label_converged = True
                    break

                # Log first 3 issues to understand critic's concerns
                for iss in issues[:3]:
                    logger.info(
                        "B2 critic issue: label=%s desc=%s",
                        iss.get("label", "?"),
                        str(iss.get("description", ""))[:120],
                    )

                # 3. FEEDBACK para siguiente iteración
                if iteration < max_iterations:
                    feedback_parts = [f"=== Iteration {iteration} Critic Review ==="]
                    for issue in issues:
                        label = issue.get("label", "(unnamed)")
                        description = issue.get("description", "")
                        suggestion = issue.get("suggestion", "")
                        feedback_parts.append(f"Issue with '{label}': {description}")
                        if suggestion:
                            feedback_parts.append(f"  → Suggestion: {suggestion}")
                    feedback = "\n".join(feedback_parts)

                    history.append({"role": "user", "content": feedback})
                    accumulated_feedback.append(feedback)  # G16: accumulate all
                # If last iteration with issues, keep final_label as-is

            # ── Persist label for this group ────────────────────────
            if final_label:
                label_name = final_label.get("label", "").strip()
                definition = final_label.get("definition", "").strip()

                if label_name and definition:
                    status = "labeled" if label_converged else "open"

                    # Update incident_group
                    session.execute(
                        text(
                            "UPDATE incident_groups "
                            "SET label = :label, definition = :definition, "
                            "    status = :status, "
                            "    labeled_by_agent = 'pattern_labeler' "
                            "WHERE id = :gid AND proyecto_id = :pid"
                        ),
                        {
                            "label": label_name,
                            "definition": definition,
                            "status": status,
                            "gid": group_id,
                            "pid": proyecto_id,
                        },
                    )

                    if label_converged:
                        # Create category for approved labels
                        session.execute(
                            text(
                                "INSERT INTO categorias "
                                "(id, proyecto_id, nombre, definicion, version, "
                                " estado_saturacion, puntaje_relevancia, es_central) "
                                "VALUES (gen_random_uuid(), :pid, :name, :def, "
                                " 1, 'ABIERTO', 1.0, false)"
                            ),
                            {
                                "pid": proyecto_id,
                                "name": label_name,
                                "def": definition,
                            },
                        )
                        labels_approved += 1
                    else:
                        labels_modified += 1

                    labels_created += 1

            # Commit per group so partial progress is saved
            session.commit()

        logger.info(
            "B2 complete: %d groups → %d labels (%d approved, %d modified) in %d total iterations",
            len(rows),
            labels_created,
            labels_approved,
            labels_modified,
            total_iterations,
        )

        return {
            "groups_processed": len(rows),
            "labels_created": labels_created,
            "labels_approved": labels_approved,
            "labels_modified": labels_modified,
            "labels_forced": 0,
            "iterations": total_iterations,
        }

    except Exception:
        session.rollback()
        logger.exception("B2 label_groups failed for project %s", proyecto_id)
        raise
    finally:
        session.close()
