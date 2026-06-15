"""T12 — elaboration_engine.py

Motor de elaboración conceptual para el Theoretical Playground.
Orquesta: proponer relaciones, expandir con datos divergentes, absorber ghost-blobs.
Usa conceptual_elaborator.md (PRO) para evaluar relaciones.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ElaborationResult:
    relationship_id: str
    elaboration_status: str  # emerging | densifying | stable | tense | expanded
    conceptual_fit: float
    converging_count: int
    diverging_count: int
    summary: str
    elaboration_note: str
    diverging_incidents: list[dict] = field(default_factory=list)


class ElaborationEngine:
    """Motor de elaboración conceptual para la Fase 6b."""

    def __init__(self, db_session: Session, llm_client):
        self.db = db_session
        self.llm = llm_client

    def elaborate_relationship(
        self,
        project_id: UUID,
        category_ids: list[UUID],
        theoretical_code_id: UUID,
        researcher_question: str,
    ) -> ElaborationResult:
        """
        Elabora una relación conceptual entre 2+ categorías.

        1. Carga categorías con incidentes
        2. Carga el código teórico
        3. Invoca conceptual_elaborator.md (PRO)
        4. Crea ConceptualRelationship + ElaborationMemo
        """
        # 1. Cargar categorías con incidentes
        cat_data = []
        for cid in category_ids:
            cat = self.db.execute(
                text("SELECT nombre, definicion FROM categorias WHERE id = :cid"),
                {"cid": cid},
            ).fetchone()
            if not cat:
                continue

            incidents = self.db.execute(
                text(
                    "SELECT s.texto, d.original_filename "
                    "FROM codigos_segmento cs "
                    "JOIN segmentos s ON cs.segmento_id = s.id "
                    "JOIN documentos d ON s.documento_id = d.id "
                    "WHERE cs.categoria_id = :cid LIMIT 20"
                ),
                {"cid": cid},
            ).fetchall()

            cat_data.append(
                {
                    "id": str(cid),
                    "name": cat[0],
                    "definition": cat[1],
                    "incidents": [
                        {"document": r[1], "text": r[0][:500]} for r in incidents
                    ],
                }
            )

        # 2. Cargar código teórico
        tc = self.db.execute(
            text(
                "SELECT name, evaluation_logic, layer "
                "FROM theoretical_codes WHERE id = :tcid"
            ),
            {"tcid": theoretical_code_id},
        ).fetchone()
        if not tc:
            raise ValueError(f"Código teórico no encontrado: {theoretical_code_id}")

        # 3. Invocar LLM
        response = self.llm.run_agent(
            "conceptual_elaborator",
            variables={
                "categories_with_incidents": json.dumps(cat_data, ensure_ascii=False),
                "theoretical_code_name": tc[0],
                "evaluation_logic": json.dumps(tc[1], ensure_ascii=False),
                "researcher_question": researcher_question,
                "related_memos": self._load_related_memos(project_id, category_ids),
                "lens_instruction": self._get_lens_instruction(tc[1]),
            },
            temperature=0.3,
        )

        # 4. Procesar respuesta
        conv_evidence = response.get("converging_evidence", [])
        div_evidence = response.get("diverging_evidence", [])
        conv_count = len(conv_evidence)
        div_count = len(div_evidence)
        conceptual_fit = response.get("conceptual_fit", 0.5)
        summary = response.get("relationship_summary", "")
        note = response.get("elaboration_note", "")

        # Determinar estado
        if conv_count == 0 and div_count == 0:
            status = "emerging"
        elif div_count > 0:
            status = "tense"
        elif conv_count >= 3 and conceptual_fit > 0.7:
            status = "stable"
        else:
            status = "densifying"

        # 5. Persistir
        rel_id = UUID(self.db.execute(text("SELECT gen_random_uuid()")).fetchone()[0])

        self.db.execute(
            text(
                "INSERT INTO conceptual_relationships "
                "(id, project_id, category_ids, theoretical_code_id, "
                "researcher_question, elaboration_status, "
                "converging_doc_count, diverging_doc_count, "
                "conceptual_fit, layer, position_tension) "
                "VALUES (:id, :pid, :cids, :tcid, :q, :status, "
                ":conv, :div, :fit, :layer, :tension)"
            ),
            {
                "id": rel_id,
                "pid": project_id,
                "cids": json.dumps([str(c) for c in category_ids]),
                "tcid": theoretical_code_id,
                "q": researcher_question,
                "status": status,
                "conv": conv_count,
                "div": div_count,
                "fit": conceptual_fit,
                "layer": tc[2],
                "tension": min(div_count * 0.2, 1.0),
            },
        )

        # 6. Crear ElaborationMemo
        self.db.execute(
            text(
                "INSERT INTO elaboration_memos "
                "(id, project_id, elaboration_type, relationship_id, content) "
                "VALUES (gen_random_uuid(), :pid, 'relationship_proposed', :rid, :content)"
            ),
            {
                "pid": project_id,
                "rid": rel_id,
                "content": (
                    f"Relación elaborada con código '{tc[0]}'. "
                    f"Pregunta: '{researcher_question}'. "
                    f"Convergencia: {conv_count} docs. Divergencia: {div_count} docs. "
                    f"Ajuste conceptual: {conceptual_fit}. {note}"
                ),
            },
        )

        self.db.commit()

        return ElaborationResult(
            relationship_id=str(rel_id),
            elaboration_status=status,
            conceptual_fit=conceptual_fit,
            converging_count=conv_count,
            diverging_count=div_count,
            summary=summary,
            elaboration_note=note,
            diverging_incidents=div_evidence,
        )

    def elaborate_divergence(self, relationship_id: UUID, resolution: str) -> None:
        """Expande una relación para acomodar datos divergentes."""
        self.db.execute(
            text(
                "UPDATE conceptual_relationships "
                "SET divergence_resolution = :res, elaboration_status = 'expanded', "
                "position_tension = 0.0 "
                "WHERE id = :rid"
            ),
            {"res": resolution, "rid": relationship_id},
        )

        self.db.execute(
            text(
                "INSERT INTO elaboration_memos "
                "(id, project_id, elaboration_type, relationship_id, content) "
                "VALUES (gen_random_uuid(), "
                "(SELECT project_id FROM conceptual_relationships WHERE id = :rid), "
                "'divergence_expanded', :rid, :content)"
            ),
            {"rid": relationship_id, "content": f"Divergencia expandida: {resolution}"},
        )
        self.db.commit()

    def absorb_ghost_blob(
        self, memo_id: UUID, target_category_id: UUID, project_id: UUID
    ) -> dict:
        """Absorbe un memo en una categoría: expande definición, añade propiedades."""
        memo = self.db.execute(
            text("SELECT contenido FROM memos WHERE id = :mid"),
            {"mid": memo_id},
        ).fetchone()
        cat = self.db.execute(
            text("SELECT nombre, definicion, version FROM categorias WHERE id = :cid"),
            {"cid": target_category_id},
        ).fetchone()

        if not memo or not cat:
            return {"error": "Memo o categoría no encontrados"}

        # Registrar versión
        new_version = (cat[2] or 0) + 1
        self.db.execute(
            text(
                "INSERT INTO category_definition_versions "
                "(id, category_id, project_id, version, name_at_version, "
                "definition_at_version, trigger, trigger_detail) "
                "VALUES (gen_random_uuid(), :cid, :pid, :v, :name, :def, "
                "'ghost_absorbed', :detail)"
            ),
            {
                "cid": target_category_id,
                "pid": project_id,
                "v": new_version,
                "name": cat[0],
                "def": cat[1],
                "detail": f"Memo {memo_id} absorbido. Contenido: {memo[0][:200]}...",
            },
        )

        self.db.execute(
            text(
                "INSERT INTO elaboration_memos "
                "(id, project_id, elaboration_type, category_id, memo_id, content) "
                "VALUES (gen_random_uuid(), :pid, 'ghost_absorbed', :cid, :mid, :content)"
            ),
            {
                "pid": project_id,
                "cid": target_category_id,
                "mid": memo_id,
                "content": f"Ghost-blob absorbido en '{cat[0]}'.",
            },
        )
        self.db.commit()

        return {
            "category_id": str(target_category_id),
            "new_version": new_version,
            "rename_suggested": False,  # rename_detector se ejecuta aparte
        }

    def _load_related_memos(self, project_id: UUID, category_ids: list[UUID]) -> str:
        rows = self.db.execute(
            text(
                "SELECT contenido FROM memos WHERE proyecto_id = :pid "
                "AND tipo IN ('HIPOTESIS', 'RELACION') LIMIT 5"
            ),
            {"pid": project_id},
        ).fetchall()
        return "\n---\n".join(r[0][:500] for r in rows) if rows else "(sin memos)"

    def _get_lens_instruction(self, evaluation_logic: dict) -> str:
        """Genera instrucción específica para el código teórico."""
        layer = evaluation_logic.get("what_it_tests", "")
        how = "\n".join(evaluation_logic.get("how_it_tests", []))
        cannot = "\n".join(evaluation_logic.get("what_it_cannot_test", []))
        return (
            f"LENTE TEÓRICA: {layer}\n\n"
            f"CÓMO EVALUAR:\n{how}\n\n"
            f"LO QUE NO DEBES HACER:\n{cannot}"
        )
