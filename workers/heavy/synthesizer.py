"""
Category Synthesizer — Merges new categories with previous ones after each 3-document batch.

Runs AFTER B2/B3 completes. Receives ALL categories from the project, separates them into
"previous" (from earlier documents) and "new" (from the current batch), and calls the AI
to merge duplicates, resolve overlaps, and produce a unified deduplicated set.

The AI agent_id is `fd_category_synthesizer` (PRO tier).
"""

from __future__ import annotations

import json
import logging

from database import SessionLocal
from llm_client import LLMClient
from sqlalchemy import text

logger = logging.getLogger(__name__)
llm = LLMClient()


def _get_docs_ordered(session, proyecto_id: str) -> list[dict]:
    """Returns all documents ordered by creation time, with their positional index (1-based)."""
    rows = session.execute(
        text(
            "SELECT id, original_filename, estado "
            "FROM documentos "
            "WHERE proyecto_id = :pid "
            "ORDER BY creado_en"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    docs = []
    for idx, row in enumerate(rows, start=1):
        docs.append(
            {
                "doc_index": idx,
                "doc_id": str(row[0]),
                "filename": row[1] or f"doc_{idx}",
                "estado": row[2],
            }
        )
    return docs


def _get_categories_with_docs(session, proyecto_id: str) -> list[dict]:
    """Returns all categories with their incident count and associated document indices.

    For each category:
      - Finds its matching incident_group by label name
      - Counts incidents from incident_ids_json
      - Finds documents via codigos_segmento → segmentos → documentos
    """
    cats = session.execute(
        text(
            "SELECT id, nombre, definicion, version, puntaje_relevancia "
            "FROM categorias "
            "WHERE proyecto_id = :pid "
            "ORDER BY creado_en"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    # Get all incident groups for this project
    groups = session.execute(
        text(
            "SELECT label, incident_ids_json "
            "FROM incident_groups "
            "WHERE proyecto_id = :pid"
        ),
        {"pid": proyecto_id},
    ).fetchall()

    group_by_label = {}
    for g in groups:
        label = (g[0] or "").strip()
        if label:
            group_by_label[label] = g[1] if isinstance(g[1], list) else []

    # Get document indices for each category via codigos_segmento → segmentos → documentos
    categories = []
    for cat_row in cats:
        cat_id = str(cat_row[0])
        cat_name = (cat_row[1] or "").strip()
        cat_def = (cat_row[2] or "").strip()

        # Incident count from matching incident_group
        incident_count = 0
        group_incident_ids = group_by_label.get(cat_name, [])
        incident_count = len(group_incident_ids)

        # Document indices via codigos_segmento
        doc_rows = session.execute(
            text(
                "SELECT d.id "
                "FROM codigos_segmento cs "
                "JOIN segmentos s ON cs.segmento_id = s.id "
                "JOIN documentos d ON s.documento_id = d.id "
                "WHERE cs.categoria_id = :cid "
                "AND d.proyecto_id = :pid "
                "GROUP BY d.id "
                "ORDER BY d.creado_en"
            ),
            {"cid": cat_id, "pid": proyecto_id},
        ).fetchall()

        # Map doc UUIDs to indices
        category_doc_ids = [str(r[0]) for r in doc_rows]

        categories.append(
            {
                "id": cat_id,
                "label": cat_name,
                "definition": cat_def,
                "incident_count": incident_count,
                "doc_ids": category_doc_ids,
                "version": cat_row[3],
                "relevance": cat_row[4],
            }
        )

    return categories


def _format_categories_compact(
    categories: list[dict], doc_index_map: dict[str, int]
) -> str:
    """Format categories in compact token-saving format.

    Example output:
    [cat_1] Label: "Sobreviviendo a la avalancha" | Docs: 1,2,3 | Incidents: 13 | Def: "proceso de..."
    [cat_2] Label: "Performando para la observación" | Docs: 2,3 | Incidents: 6 | Def: "adaptación de..."
    """
    lines = []
    for idx, cat in enumerate(categories, start=1):
        # Map doc UUIDs to indices
        doc_indices = sorted(
            doc_index_map.get(did, 0)
            for did in cat["doc_ids"]
            if doc_index_map.get(did, 0) > 0
        )
        docs_str = ",".join(str(d) for d in doc_indices) if doc_indices else "?"

        label = cat["label"]
        definition = cat["definition"]
        # Truncate definition to ~200 chars to save tokens
        if len(definition) > 200:
            definition = definition[:197] + "..."

        incident_count = cat.get("incident_count", 0)

        lines.append(
            f'[cat_{idx}] ID: {cat["id"]} | Label: "{label}" | Docs: {docs_str} '
            f'| Incidents: {incident_count} | Def: "{definition}"'
        )

    return "\n".join(lines)


def synthesize_categories(proyecto_id: str, batch_start_doc_index: int) -> dict:
    """Merge new categories from the current 3-doc batch with previous categories.

    Args:
        proyecto_id: Project UUID.
        batch_start_doc_index: 1-based index of the first document in the current batch.
            For the first batch (docs 1-3), this is 1 (no previous categories exist).
            For the second batch (docs 4-6), this is 4.
            For the third batch (docs 7-9), this is 7.

    Returns:
        dict with:
          - previous_count: number of previous categories
          - new_count: number of new categories
          - unified_count: number of unified categories after merging
          - merges: number of merge actions performed
          - renames: number of rename actions performed
          - keeps: number of keep actions performed
    """
    session = SessionLocal()
    try:
        logger.info(
            "Synthesizer: project=%s batch_start=%d",
            proyecto_id[:8],
            batch_start_doc_index,
        )

        # ── 1. Load ordered documents ──
        docs = _get_docs_ordered(session, proyecto_id)
        if not docs:
            return {"error": "No documents found", "status": "skipped"}

        doc_index_map = {d["doc_id"]: d["doc_index"] for d in docs}

        # ── 2. Load all categories ──
        all_categories = _get_categories_with_docs(session, proyecto_id)
        if not all_categories:
            logger.info("Synthesizer: No categories found for project %s", proyecto_id)
            return {
                "previous_count": 0,
                "new_count": 0,
                "unified_count": 0,
                "merges": 0,
                "renames": 0,
                "keeps": 0,
            }

        # ── 3. Split into previous and new ──
        previous_categories = []
        new_categories = []

        for cat in all_categories:
            doc_indices = sorted(
                doc_index_map.get(did, 0)
                for did in cat["doc_ids"]
                if doc_index_map.get(did, 0) > 0
            )

            # A category is "new" if it ONLY appears in docs >= batch_start_doc_index
            # and has at least one doc in the current batch range.
            # A category is "previous" if it appears in any doc < batch_start_doc_index.
            has_previous_docs = any(d < batch_start_doc_index for d in doc_indices)
            has_new_docs = any(d >= batch_start_doc_index for d in doc_indices)

            if batch_start_doc_index == 1:
                # First batch: everything is "new"
                new_categories.append(cat)
            elif has_previous_docs and not has_new_docs:
                previous_categories.append(cat)
            elif has_new_docs and not has_previous_docs:
                new_categories.append(cat)
            elif has_previous_docs and has_new_docs:
                # Category spans both batches — treat as "previous" (already known)
                previous_categories.append(cat)
            else:
                # Category with no doc associations — put in new
                new_categories.append(cat)

        logger.info(
            "Synthesizer: %d previous, %d new categories",
            len(previous_categories),
            len(new_categories),
        )

        if not new_categories:
            return {
                "previous_count": len(previous_categories),
                "new_count": 0,
                "unified_count": len(previous_categories),
                "merges": 0,
                "renames": 0,
                "keeps": 0,
                "status": "no_new_categories",
            }

        # ── 4. Format compactly ──
        previous_formatted = _format_categories_compact(
            previous_categories, doc_index_map
        )
        new_formatted = _format_categories_compact(new_categories, doc_index_map)

        if not previous_formatted:
            previous_formatted = "(no previous categories — this is the first batch)"

        # ── 5. Call AI ──
        response = llm.run_agent(
            agent_id="fd_category_synthesizer",
            variables={
                "previous_categories": previous_formatted,
                "new_categories": new_formatted,
            },
        )

        unified = response.get("unified_categories", [])
        if not unified:
            logger.warning(
                "Synthesizer: AI returned no unified_categories. Response keys: %s",
                list(response.keys())
                if isinstance(response, dict)
                else type(response).__name__,
            )
            return {
                "previous_count": len(previous_categories),
                "new_count": len(new_categories),
                "unified_count": 0,
                "merges": 0,
                "renames": 0,
                "keeps": 0,
                "error": "empty_response",
            }

        # ── 6. Persist unified categories ──
        merges = 0
        renames = 0
        keeps = 0

        for uc in unified:
            action = uc.get("action", "keep")
            final_label = uc.get("label", "").strip()
            final_definition = uc.get("definition", "").strip()
            source_ids = uc.get("source_categories", [])
            merged_from = uc.get("merged_from", [])

            if not final_label or not final_definition:
                logger.warning(
                    "Synthesizer: skipping unified category with empty label/def"
                )
                continue

            if action == "keep":
                # Keep existing category — update if renamed
                if source_ids:
                    cat_id = source_ids[0]
                    # Check if label changed (rename case within "keep")
                    existing = session.execute(
                        text("SELECT nombre FROM categorias WHERE id = :cid"),
                        {"cid": cat_id},
                    ).fetchone()
                    if existing and existing[0] != final_label:
                        action = "rename"
                        renames += 1
                        session.execute(
                            text(
                                "UPDATE categorias SET nombre = :name, definicion = :def, "
                                "version = version + 1 "
                                "WHERE id = :cid"
                            ),
                            {
                                "name": final_label,
                                "def": final_definition,
                                "cid": cat_id,
                            },
                        )
                    else:
                        keeps += 1
                else:
                    keeps += 1

            elif action == "rename":
                renames += 1
                if source_ids:
                    cat_id = source_ids[0]
                    session.execute(
                        text(
                            "UPDATE categorias SET nombre = :name, definicion = :def, "
                            "version = version + 1 "
                            "WHERE id = :cid"
                        ),
                        {"name": final_label, "def": final_definition, "cid": cat_id},
                    )

            elif action == "merge":
                merges += 1
                # Strategy: keep the first source category as the "survivor", update its
                # label/definition, merge others into it, then delete superseded ones.
                # Store merge history in the survivor category.

                survivor_id = source_ids[0] if source_ids else None

                if survivor_id:
                    # Update survivor
                    session.execute(
                        text(
                            "UPDATE categorias SET nombre = :name, definicion = :def, "
                            "version = version + 1 "
                            "WHERE id = :cid"
                        ),
                        {
                            "name": final_label,
                            "def": final_definition,
                            "cid": survivor_id,
                        },
                    )

                # For superseded categories (source_ids[1:]), reassign their
                # codigos_segmento and doc_codes to the survivor, then delete them.
                superseded_ids = source_ids[1:] if len(source_ids) > 1 else []

                for old_id in superseded_ids:
                    try:
                        # Reassign codigos_segmento to survivor (avoid duplicates)
                        session.execute(
                            text(
                                "INSERT INTO codigos_segmento (segmento_id, categoria_id, estado, confianza, origen) "
                                "SELECT segmento_id, :survivor, estado, confianza, origen "
                                "FROM codigos_segmento "
                                "WHERE categoria_id = :old "
                                "ON CONFLICT (segmento_id, categoria_id) DO NOTHING"
                            ),
                            {"survivor": survivor_id, "old": old_id},
                        )
                        # Delete old codigos_segmento
                        session.execute(
                            text(
                                "DELETE FROM codigos_segmento WHERE categoria_id = :old"
                            ),
                            {"old": old_id},
                        )
                        # Reassign doc_codes
                        session.execute(
                            text(
                                "INSERT INTO doc_codes (documento_id, categoria_id, estado, resumen_evidencia) "
                                "SELECT documento_id, :survivor, estado, resumen_evidencia "
                                "FROM doc_codes "
                                "WHERE categoria_id = :old "
                                "ON CONFLICT (documento_id, categoria_id) DO NOTHING"
                            ),
                            {"survivor": survivor_id, "old": old_id},
                        )
                        session.execute(
                            text("DELETE FROM doc_codes WHERE categoria_id = :old"),
                            {"old": old_id},
                        )
                        # Delete superseded category
                        session.execute(
                            text("DELETE FROM categorias WHERE id = :old"),
                            {"old": old_id},
                        )
                    except Exception as e:
                        logger.warning(
                            "Synthesizer: failed to reassign/delete superseded category %s: %s",
                            old_id,
                            e,
                        )

                # Merge history: store in saturation_panel_json (temporary; TODO: add merged_from column)
                merge_record = {
                    "merged_from": merged_from,
                    "source_ids": source_ids,
                    "action": "merge",
                    "batch_start_doc_index": batch_start_doc_index,
                }
                if survivor_id:
                    try:
                        existing_panel = session.execute(
                            text(
                                "SELECT saturation_panel_json FROM categorias WHERE id = :cid"
                            ),
                            {"cid": survivor_id},
                        ).fetchone()

                        current_panel = (
                            existing_panel[0]
                            if existing_panel
                            and existing_panel[0]
                            and isinstance(existing_panel[0], dict)
                            else {}
                        )
                        merge_history = current_panel.get("_merge_history", [])
                        if isinstance(merge_history, list):
                            merge_history.append(merge_record)
                        else:
                            merge_history = [merge_record]
                        current_panel["_merge_history"] = merge_history

                        session.execute(
                            text(
                                "UPDATE categorias SET saturation_panel_json = :panel WHERE id = :cid"
                            ),
                            {"panel": json.dumps(current_panel), "cid": survivor_id},
                        )
                    except Exception as e:
                        logger.warning(
                            "Synthesizer: failed to store merge history for %s: %s",
                            survivor_id,
                            e,
                        )

        session.commit()

        logger.info(
            "Synthesizer complete: %d unified (%d keeps, %d merges, %d renames)",
            len(unified),
            keeps,
            merges,
            renames,
        )

        return {
            "previous_count": len(previous_categories),
            "new_count": len(new_categories),
            "unified_count": len(unified),
            "merges": merges,
            "renames": renames,
            "keeps": keeps,
        }

    except Exception:
        session.rollback()
        logger.exception("Synthesizer failed for project %s", proyecto_id)
        raise
    finally:
        session.close()
