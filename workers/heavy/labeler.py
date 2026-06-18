"""
B2 — Pattern Labeler (PRO + SelfRefinement loop).

Recibe grupos de incidentes intercambiables del comparator (B1).
Propone etiquetas (gerundios) + definiciones para cada grupo.

Usa un bucle de auto-refinamiento: generate → critic → refine.
Máx 3 iteraciones. PRO para generar, FLASH para criticar.

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
    """Propone etiquetas para grupos de incidentes usando SelfRefinement.

    1. Lee incident_groups con status='open' (sin etiqueta).
    2. Bucle Generate (pattern_labeler, PRO) → Critic (label_critic, FLASH).
    3. Máx 3 iteraciones. Converge cuando all_valid=True.
    4. Persiste etiquetas aprobadas en incident_groups y categorias.

    Args:
        proyecto_id: UUID del proyecto.

    Returns:
        dict con:
          - groups_processed: int
          - labels_created: int
          - labels_approved: int
          - labels_modified: int
          - labels_forced: int
          - iterations: int (total del bucle)
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

        # ── SelfRefinement Loop ────────────────────────────────────
        groups_json = json.dumps(groups, indent=2, ensure_ascii=False)
        history: list[dict] = []

        max_iterations = 3
        all_valid = False
        final_labels: list[dict] = []
        total_iterations = 0

        for iteration in range(1, max_iterations + 1):
            total_iterations = iteration

            # 1. GENERATE (PRO)
            gen_vars = {
                "groups_json": groups_json,
                "object_of_study": object_of_study,
                "existing_labels": existing_labels,
                "operational_question": operational_question or "(not yet generated)",
            }

            # Si hay feedback de iteración anterior, añadirlo
            if history:
                feedback_msgs = [
                    m["content"]
                    for m in history
                    if m.get("role") == "user" and "issues" in m.get("content", "")
                ]
                if feedback_msgs:
                    gen_vars["groups_json"] = (
                        groups_json
                        + "\n\n[FEEDBACK DE ITERACIÓN ANTERIOR]\n"
                        + feedback_msgs[-1]
                    )

            gen_response = llm.run_agent(
                agent_id="fb_pattern_labeler",
                variables=gen_vars,
            )

            gen_text = json.dumps(gen_response, ensure_ascii=False)
            history.append(_build_assistant_message(gen_text, gen_response))

            proposed_labels = gen_response.get("proposed_labels", [])
            if not proposed_labels:
                logger.warning("B2 iter %d: No labels proposed", iteration)
                break

            # 2. CRITIC (FLASH)
            critic_response = llm.run_agent(
                agent_id="fb_label_critic",
                variables={
                    "output_to_evaluate": gen_text,
                    "source_incidents": groups_json,
                },
                temperature=0.1,
            )

            all_valid = critic_response.get("all_valid", False)
            issues = critic_response.get("issues", [])

            logger.info(
                "B2 iter %d: %d labels, all_valid=%s, issues=%d",
                iteration,
                len(proposed_labels),
                all_valid,
                len(issues),
            )

            if all_valid:
                final_labels = proposed_labels
                break

            # 3. FEEDBACK para siguiente iteración
            if issues and iteration < max_iterations:
                feedback = (
                    f"Iteration {iteration} issues:\n"
                    f"{json.dumps(issues, ensure_ascii=False)[:800]}\n"
                    "Refiná las etiquetas con problemas."
                )
                history.append(
                    {
                        "role": "user",
                        "content": feedback,
                    }
                )
                final_labels = proposed_labels  # Guardar por si es la última
            else:
                final_labels = proposed_labels

        # ── Si no convergió, usar últimos labels ───────────────────
        if not all_valid and final_labels:
            logger.info("B2: Using labels from final iteration (not fully converged)")

        # ── Persistir etiquetas ────────────────────────────────────
        labels_created = 0
        labels_approved = 0
        labels_modified = 0
        labels_forced = 0

        # Clasificar por veredicto (del último critic si existe)
        verdict_map: dict[str, str] = {}
        if not all_valid:
            # Último critic issues para clasificar
            critic_check = llm.run_agent(
                agent_id="fb_label_critic",
                variables={
                    "output_to_evaluate": json.dumps(
                        {"proposed_labels": final_labels}, ensure_ascii=False
                    ),
                    "source_incidents": groups_json,
                },
                temperature=0.1,
            )
            for issue in critic_check.get("issues", []):
                label_name = issue.get("label", "")
                verdict = issue.get("verdict", "MOD")
                if label_name:
                    verdict_map[label_name] = verdict

        for label_info in final_labels:
            label = label_info.get("label", "").strip()
            definition = label_info.get("definition", "").strip()
            group_index = label_info.get("group_index", -1)

            if not label or not definition:
                continue

            # Obtener el group_id correspondiente
            group_id = None
            if 0 <= group_index < len(groups):
                group_id = groups[group_index]["group_id"]

            if not group_id:
                continue

            verdict = verdict_map.get(label, "SAT")

            # Actualizar incident_group
            session.execute(
                text(
                    "UPDATE incident_groups "
                    "SET label = :label, definition = :definition, "
                    "    status = CASE WHEN :status = 'SAT' THEN 'labeled' ELSE 'open' END, "
                    "    labeled_by_agent = 'pattern_labeler', "
                    "    critic_verdict = :verdict::jsonb "
                    "WHERE id = :gid AND proyecto_id = :pid"
                ),
                {
                    "label": label,
                    "definition": definition,
                    "status": "SAT" if verdict == "SAT" else "MOD",
                    "verdict": json.dumps({"verdict": verdict}),
                    "gid": group_id,
                    "pid": proyecto_id,
                },
            )

            # Si SAT, crear categoría
            if verdict == "SAT":
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
                        "name": label,
                        "def": definition,
                    },
                )
                labels_approved += 1
            elif verdict == "MOD":
                labels_modified += 1
            else:
                labels_forced += 1

            labels_created += 1

        session.commit()

        logger.info(
            "B2 complete: %d labels (%d SAT, %d MOD, %d FORCED) in %d iterations",
            labels_created,
            labels_approved,
            labels_modified,
            labels_forced,
            total_iterations,
        )

        return {
            "groups_processed": len(rows),
            "labels_created": labels_created,
            "labels_approved": labels_approved,
            "labels_modified": labels_modified,
            "labels_forced": labels_forced,
            "iterations": total_iterations,
        }

    except Exception:
        session.rollback()
        logger.exception("B2 label_groups failed for project %s", proyecto_id)
        raise
    finally:
        session.close()
