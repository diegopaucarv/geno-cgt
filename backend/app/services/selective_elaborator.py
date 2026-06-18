"""
SelectiveElaborator — S05 del plan Selective Coding.

Orquesta el ciclo de elaboración por incidente para la Fase 5b.
Reemplaza los 4 nodos paralelos (Behavioral Patterns, Properties, Causes, Consequences)
por un ciclo iterativo donde cada incidente se compara contra el estado actual de la categoría.

Flujo:
  1. Carga estado actual de la categoría (definición, propiedades, versión)
  2. Invoca f6b_incident_elaborator.md (PRO)
  3. Procesa respuesta: converge → contador++, diverge → expande definición
  4. Actualiza ParadigmState
  5. Retorna resultado para el frontend (blob crece/cambia de color/tiembla)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class ElaborationResult:
    category_id: str
    elaboration_type: str  # converges | diverges_dimension | diverges_property | diverges_condition | diverges_strong
    description: str
    expanded_definition: str | None = None
    new_properties: list[dict] = field(default_factory=list)
    suggested_action: str = "none"
    rename_suggested: bool = False
    rename_candidates: list[str] = field(default_factory=list)
    elaboration_note: str = ""
    did_state_expand: bool = False


class SelectiveElaborator:
    """
    Orquestador del ciclo de elaboración selectiva.
    Usa f6b_incident_elaborator.md (PRO) para evaluar cada incidente.
    """

    def __init__(self, llm_client, db_session):
        self.llm = llm_client
        self.db = db_session

    def elaborate_incident(
        self,
        category_id: UUID,
        incident_text: str,
        document_name: str = "",
    ) -> ElaborationResult:
        """
        Evalúa un nuevo incidente contra una categoría y elabora la relación.

        Returns:
            ElaborationResult con el tipo de elaboración, propiedades expandidas,
            definición actualizada (si cambió), y acción sugerida.
        """
        from sqlalchemy import text

        # 1. Cargar estado actual de la categoría
        cat = self.db.execute(
            text(
                "SELECT nombre, definicion, version, embedding_centroide "
                "FROM categorias WHERE id = :cid"
            ),
            {"cid": category_id},
        ).fetchone()

        if not cat:
            return ElaborationResult(
                category_id=str(category_id),
                elaboration_type="converges",
                description="Categoría no encontrada.",
            )

        cat_name, cat_def, cat_version = cat[0], cat[1] or "", cat[2] or 1

        # 2. Obtener propiedades actuales desde paradigm_states
        paradigm = self.db.execute(
            text(
                "SELECT paradigm_snapshot FROM paradigm_states "
                "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 1"
            ),
            {"cid": category_id},
        ).fetchone()

        current_properties = ""
        if paradigm and paradigm[0]:
            ps = paradigm[0] if isinstance(paradigm[0], dict) else {}
            dims = ps.get("dimensions", [])
            current_properties = json.dumps(
                [
                    {"name": d.get("label", ""), "gradient": d.get("description", "")}
                    for d in dims
                ],
                ensure_ascii=False,
            )

        # 3. Invocar f6b_incident_elaborator (PRO)
        response = self.llm.run_agent(
            "f6b_incident_elaborator",
            variables={
                "category_label": cat_name,
                "category_definition": cat_def,
                "version": str(cat_version),
                "current_properties": current_properties
                or "(sin propiedades documentadas)",
                "document_name": document_name,
                "incident_text": incident_text[:5000],
                "coding_style_instruction": self._get_style_instruction(category_id),
            },
            temperature=0.3,
        )

        # 4. Procesar respuesta
        elaboration_type = response.get("elaboration_type", "converges")
        description = response.get("description", "")
        expanded_def = response.get("expanded_definition", "")
        new_props = response.get("new_or_expanded_properties", [])
        suggested_action = response.get("suggested_action", "none")
        rename_suggested = response.get("rename_suggested", False)
        rename_candidates = response.get("rename_candidates", [])
        elaboration_note = response.get("elaboration_note", "")
        did_expand = elaboration_type != "converges"

        # 5. Actualizar ParadigmState
        current_iter = self._get_current_iteration(category_id)
        new_paradigm = self._update_paradigm(
            category_id,
            cat_name,
            did_expand,
            elaboration_type,
            new_props,
            elaboration_note,
        )

        self.db.execute(
            text(
                "INSERT INTO paradigm_states (id, code_id, proyecto_id, iteration, "
                "did_state_expand, expansion_type, paradigm_snapshot, integration_memo) "
                "VALUES (gen_random_uuid(), :cid, "
                "(SELECT proyecto_id FROM categorias WHERE id = :cid2), "
                ":iter, :exp, :etype, :snap, :memo)"
            ),
            {
                "cid": category_id,
                "cid2": category_id,
                "iter": current_iter + 1,
                "exp": did_expand,
                "etype": elaboration_type if did_expand else "NONE",
                "snap": json.dumps(new_paradigm),
                "memo": elaboration_note,
            },
        )

        # 6. Si la definición se expandió, actualizar la categoría
        if expanded_def and suggested_action in (
            "update_definition",
            "add_property",
            "expand_gradient",
        ):
            self.db.execute(
                text(
                    "UPDATE categorias SET definicion = :def, version = version + 1 "
                    "WHERE id = :cid"
                ),
                {"def": expanded_def, "cid": category_id},
            )

        # 7. Si se sugiere renombre, marcar la categoría
        if rename_suggested:
            self.db.execute(
                text(
                    "UPDATE categorias SET metadatos = COALESCE(metadatos, '{}'::jsonb) || "
                    "jsonb_build_object('rename_pending', true, 'rename_candidates', :cands) "
                    "WHERE id = :cid"
                ),
                {"cands": json.dumps(rename_candidates), "cid": category_id},
            )

        self.db.commit()

        return ElaborationResult(
            category_id=str(category_id),
            elaboration_type=elaboration_type,
            description=description,
            expanded_definition=expanded_def if expanded_def else None,
            new_properties=new_props,
            suggested_action=suggested_action,
            rename_suggested=rename_suggested,
            rename_candidates=rename_candidates,
            elaboration_note=elaboration_note,
            did_state_expand=did_expand,
        )

    def get_category_evolution(self, category_id: UUID) -> dict:
        """Historial de evolución de la categoría para el frontend."""
        from sqlalchemy import text

        rows = self.db.execute(
            text(
                "SELECT iteration, did_state_expand, expansion_type, integration_memo, creado_en "
                "FROM paradigm_states WHERE code_id = :cid ORDER BY iteration"
            ),
            {"cid": category_id},
        ).fetchall()

        return {
            "category_id": str(category_id),
            "iterations": [
                {
                    "iteration": r[0],
                    "did_expand": r[1],
                    "expansion_type": r[2],
                    "memo": r[3],
                    "timestamp": str(r[4]),
                }
                for r in rows
            ],
        }

    def _get_style_instruction(self, category_id) -> str:
        """Lee el coding_style del proyecto y devuelve la instrucción."""
        row = self.db.execute(
            text("SELECT c.proyecto_id FROM categorias c WHERE c.id = :cid"),
            {"cid": category_id},
        ).fetchone()
        if not row:
            from app.core.coding_styles import get_default_style_instruction

            return get_default_style_instruction()
        config = self.db.execute(
            text("SELECT population_assumption FROM proyectos WHERE id = :pid"),
            {"pid": row[0]},
        ).fetchone()
        from app.core.coding_styles import get_default_style

        style_key = get_default_style()
        if config and config[0] and isinstance(config[0], dict):
            style_key = config[0].get("coding_style", style_key)
        from app.core.coding_styles import get_rename_instruction

        return get_rename_instruction(style_key)

    def _get_current_iteration(self, category_id: UUID) -> int:
        row = self.db.execute(
            text("SELECT MAX(iteration) FROM paradigm_states WHERE code_id = :cid"),
            {"cid": category_id},
        ).fetchone()
        return row[0] if row and row[0] else 0

    def _update_paradigm(
        self, category_id, cat_name, did_expand, elaboration_type, new_props, memo
    ) -> dict:
        """Actualiza el paradigm_snapshot con nuevas propiedades."""
        # Obtener snapshot actual
        row = self.db.execute(
            text(
                "SELECT paradigm_snapshot FROM paradigm_states "
                "WHERE code_id = :cid ORDER BY iteration DESC LIMIT 1"
            ),
            {"cid": category_id},
        ).fetchone()

        current = (
            row[0]
            if row and row[0]
            else {
                "dimensions": [],
                "conditions": [],
                "consequences": [],
                "strategies": [],
            }
        )
        if isinstance(current, str):
            current = json.loads(current)

        # Si divergió con nuevas propiedades, añadirlas como dimensions
        if did_expand and new_props:
            for prop in new_props:
                name = prop.get("name", "")
                gradient = prop.get("gradient", "")
                if name and not any(
                    d.get("label") == name for d in current.get("dimensions", [])
                ):
                    current.setdefault("dimensions", []).append(
                        {
                            "label": name,
                            "description": gradient,
                            "added_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )

        return current
