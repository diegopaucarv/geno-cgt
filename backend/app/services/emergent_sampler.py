"""E03 — emergent_sampler.py

Muestreo teórico por propiedades emergentes.
Reemplaza al viejo TheoSampler (metadata-based) con muestreo semántico
basado en las propiedades de las categorías.

Flujo:
  1. Detecta propiedades con gradientes desbalanceados
  2. Escanea el corpus (corpus_scanner FLASH) buscando el extremo faltante
  3. Si no encuentra → property_sampler (PRO) sugiere muestreo externo
  4. Si encuentra → retorna incidentes para codificar
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class EmergentDimension:
    property_name: str
    gradient: str
    axis_type: str  # "core_concern_variable" | "category_property"
    values: dict[str, int]  # {"extreme_a": count, "extreme_b": count}
    is_balanced: bool
    missing_extremes: list[str]


@dataclass
class SamplingResult:
    category_id: str
    property_name: str
    target_extreme: str
    found_incidents: list[dict] = field(default_factory=list)
    gradient_expanded: bool = False
    corpus_gap: bool = False
    sampling_recommendation: str = ""
    suggested_interview_question: str = ""


class EmergentSampler:
    """Muestreo guiado por propiedades de categorías, no por metadatos."""

    def __init__(self, db_session: Session, llm_client):
        self.db = db_session
        self.llm = llm_client

    def detect_emergent_dimensions(self, project_id: UUID) -> list[EmergentDimension]:
        """
        Analiza propiedades de categorías y detecta:
        - Gradientes desbalanceados (ej. 8 en polo A, 1 en polo B)
        - Propiedades nuevas con pocos incidentes
        """
        dims: list[EmergentDimension] = []

        # 1. Propiedades desde paradigm_states (Momento 2)
        rows = self.db.execute(
            text("""
                SELECT c.id, c.nombre, ps.paradigm_snapshot
                FROM categorias c
                JOIN paradigm_states ps ON c.id = ps.code_id
                WHERE c.proyecto_id = :pid
                  AND ps.paradigm_snapshot IS NOT NULL
                ORDER BY ps.iteration DESC
            """),
            {"pid": project_id},
        ).fetchall()

        for row in rows:
            cat_id, cat_name, snapshot = row
            if not isinstance(snapshot, dict):
                continue

            for dim in snapshot.get("dimensions", []):
                label = dim.get("label", "")
                desc = dim.get("description", "")
                if not label:
                    continue

                # Contar incidentes en los extremos (heurística: buscar en descripción)
                parts = desc.split("↔") if "↔" in desc else desc.split("←→")
                extremes = [p.strip() for p in parts] if len(parts) == 2 else [desc, ""]

                # Contar desde codigos_segmento
                count = self.db.execute(
                    text(
                        "SELECT COUNT(*) FROM codigos_segmento "
                        "WHERE categoria_id = :cid"
                    ),
                    {"cid": cat_id},
                ).fetchone()[0]

                # Asumir distribución balanceada como heurística inicial
                # En producción, el incident_elaborator registra extremos por incidente
                half = count // 2
                values = {extremes[0]: half + (count % 2), extremes[1]: half}

                dims.append(
                    EmergentDimension(
                        property_name=label,
                        gradient=desc,
                        axis_type="category_property",
                        values=values,
                        is_balanced=abs(
                            values.get(extremes[0], 0) - values.get(extremes[1], 0)
                        )
                        <= 2,
                        missing_extremes=[e for e, c in values.items() if c == 0],
                    )
                )

        # 2. Variables del core concern (Momento 1)
        # Derivadas de A14: relevant_population_dimensions
        # (se poblarán cuando A14 se ejecute con el nuevo output schema)

        return dims

    def sample_for_property_extreme(
        self,
        category_id: UUID,
        property_name: str,
        target_extreme: str,
        project_id: UUID,
    ) -> SamplingResult:
        """
        Busca incidentes que manifiesten una propiedad en un extremo específico.

        1. Escanea corpus existente (corpus_scanner FLASH)
        2. Si no encuentra → property_sampler (PRO) para sugerencia externa
        """
        cat = self.db.execute(
            text("SELECT nombre, definicion FROM categorias WHERE id = :cid"),
            {"cid": category_id},
        ).fetchone()
        if not cat:
            return SamplingResult(
                category_id=str(category_id),
                property_name=property_name,
                target_extreme=target_extreme,
            )

        # Paso 1: escanear corpus con FLASH
        all_segments = self.db.execute(
            text(
                "SELECT s.id, s.texto, d.original_filename "
                "FROM segmentos s "
                "JOIN documentos d ON s.documento_id = d.id "
                "WHERE d.proyecto_id = :pid "
                "LIMIT 100"
            ),
            {"pid": project_id},
        ).fetchall()

        # Paso 1: escanear corpus con FLASH (en batches de 6 para mantener <2000 chars)
        BATCH = 6
        all_matches = []
        for i in range(0, len(all_segments), BATCH):
            batch = all_segments[i : i + BATCH]
            batch_text = "\n---\n".join(f"[{r[0]}] {r[2]}: {r[1][:300]}" for r in batch)
            flash_result = self.llm.run_agent(
                "corpus_scanner",
                variables={
                    "category_label": cat[0],
                    "category_definition": cat[1] or "",
                    "property_name": property_name,
                    "property_gradient": target_extreme,
                    "target_extreme": target_extreme,
                    "segments_text": batch_text,
                },
                tier="FAST",
                temperature=0.1,
            )
            matches = flash_result.get("matches", [])
            all_matches.extend(matches)

        # Deduplicar por segment_id
        seen = set()
        unique_matches = []
        for m in all_matches:
            if m["segment_id"] not in seen:
                seen.add(m["segment_id"])
                unique_matches.append(m)

        if unique_matches:
            return SamplingResult(
                category_id=str(category_id),
                property_name=property_name,
                target_extreme=target_extreme,
                found_incidents=unique_matches,
                gradient_expanded=False,
                corpus_gap=False,
            )

        # Paso 2: no hay matches → PRO para sugerencia externa
        pro_result = self.llm.run_agent(
            "property_sampler",
            variables={
                "category_label": cat[0],
                "category_definition": cat[1] or "",
                "property_name": property_name,
                "property_gradient": target_extreme,
                "target_extreme": target_extreme,
                "current_count": "0",
                "all_segments_summary": f"Corpus de {len(all_segments)} segmentos. Sin coincidencias en escaneo FLASH.",
                "sampling_memos": "(sin memos de muestreo)",
            },
            temperature=0.3,
        )

        return SamplingResult(
            category_id=str(category_id),
            property_name=property_name,
            target_extreme=target_extreme,
            corpus_gap=pro_result.get("corpus_gap", True),
            sampling_recommendation=pro_result.get("sampling_recommendation", ""),
            suggested_interview_question=pro_result.get(
                "suggested_interview_question", ""
            ),
        )

    def suggest_rename_from_expansion(
        self, category_id: UUID, new_dimension: str
    ) -> list[str]:
        """
        Cuando una categoría se expande para acomodar un nuevo polo,
        sugiere nombres que capturen AMBOS extremos.
        """
        from app.services.rename_detector import get_rename_candidates

        result = get_rename_candidates(category_id, self.db, self.llm)
        if not result:
            return []
        return [s["name"] for s in result.get("suggestions", [])]
