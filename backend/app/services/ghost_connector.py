"""T26 — ghost_connector.py

Conecta el Memo_Bank con el Theoretical Playground.
Al entrar al Playground, clasifica memos de hipótesis no conectados
como ghost-blobs que el investigador puede arrastrar hacia categorías.

Usa f6b_ghost_blob_mapper.md (PRO) para sugerir mapeos.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class GhostConnector:
    """Vincula memos huérfanos con categorías para el Playground."""

    def __init__(self, db_session: Session, llm_client):
        self.db = db_session
        self.llm = llm_client

    def generate_ghost_blobs(self, project_id: UUID) -> list[dict]:
        """
        Carga memos de hipótesis no conectados y los clasifica.

        Returns:
            Lista de ghost-blobs con posición sugerida y target_category.
        """
        # 1. Memos no absorbidos aún
        rows = self.db.execute(
            text("""
                SELECT m.id, m.contenido, m.tipo
                FROM memos m
                WHERE m.proyecto_id = :pid
                  AND m.tipo = 'HIPOTESIS'
                  AND m.id NOT IN (
                      SELECT em.memo_id FROM elaboration_memos em
                      WHERE em.memo_id IS NOT NULL AND em.project_id = :pid2
                  )
                LIMIT 30
            """),
            {"pid": project_id, "pid2": project_id},
        ).fetchall()

        if not rows:
            return []

        # 2. Categorías existentes
        cats = self.db.execute(
            text(
                "SELECT id, nombre, definicion FROM categorias "
                "WHERE proyecto_id = :pid AND puntaje_relevancia >= 3 "
                "ORDER BY puntaje_relevancia DESC"
            ),
            {"pid": project_id},
        ).fetchall()

        cats_text = "\n".join(f"[{r[0]}] {r[1]}: {r[2][:200]}" for r in cats)

        # 3. Clasificar memos con f6b_ghost_blob_mapper (PRO)
        memos_text = "\n---\n".join(f"[{r[0]}] {r[1][:500]}" for r in rows)

        response = self.llm.run_agent(
            "f6b_ghost_blob_mapper",
            variables={
                "memos_to_map": memos_text[:8000],
                "existing_categories": cats_text[:4000],
                "core_concern": self._get_core_concern(project_id),
            },
            temperature=0.3,
        )

        # 4. Construir ghost-blobs
        mappings = response.get("mappings", [])
        ghosts = []

        for i, mapping in enumerate(mappings):
            memo_id = mapping.get("memo_id", "")
            disposition = mapping.get("disposition", "unmapped")

            ghost = {
                "id": memo_id,
                "disposition": disposition,
                "content_preview": "",
                "target_category_ids": mapping.get("target_category_ids", []),
                "what_it_adds": mapping.get("what_it_adds", ""),
                "suggested_new_category": None,
                "position": {
                    "x": 100 + (i % 5) * 80,
                    "y": 500 + (i // 5) * 60,
                },
            }

            if disposition == "suggest_new":
                ghost["suggested_new_category"] = {
                    "name": mapping.get("suggested_new_category_name", ""),
                    "definition": mapping.get("suggested_new_category_definition", ""),
                }

            ghosts.append(ghost)

        return ghosts

    def absorb_ghost(
        self, memo_id: UUID, target_category_id: UUID, project_id: UUID
    ) -> dict:
        """
        Absorbe un ghost-blob en una categoría.
        Usa ElaborationEngine para registrar la absorción.
        """
        from app.services.elaboration_engine import ElaborationEngine

        engine = ElaborationEngine(self.db, self.llm)
        result = engine.absorb_ghost_blob(memo_id, target_category_id, project_id)

        # Verificar si corresponde sugerir renombre
        from app.services.rename_detector import should_suggest_rename

        if should_suggest_rename(target_category_id, self.db):
            result["rename_suggested"] = True

        return result

    def _get_core_concern(self, project_id: UUID) -> str:
        row = self.db.execute(
            text("SELECT supuesto_poblacional FROM proyectos WHERE id = :pid"),
            {"pid": project_id},
        ).fetchone()
        return row[0] if row and row[0] else "(no definido aún)"
