"""T13 — recommendation_engine.py

Motor de recomendaciones para el Theoretical Playground.
Genera la "Guía de Elaboración": sugerencias rankeadas por impacto.
Evalúa 5 dimensiones: conexiones sugeridas, ghosts, renombres, neblina, tensiones.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    category: str
    title: str
    description: str
    action_type: str  # connect | absorb_ghost | rename | sample | resolve_tension
    category_ids: list[str] = field(default_factory=list)
    suggested_code: str = ""
    impact_score: float = 0.0


class RecommendationEngine:
    """Genera recomendaciones accionables para avanzar la teoría."""

    def __init__(self, db_session: Session):
        self.db = db_session

    def generate_recommendations(self, project_id: UUID) -> list[Recommendation]:
        """Genera recomendaciones rankeadas por impacto estimado."""
        recs: list[Recommendation] = []

        # 1. Conexiones sugeridas (pares co-ocurrentes sin relación)
        recs.extend(self._suggest_connections(project_id))

        # 2. Ghost-blobs sin absorber (hipótesis no conectadas)
        recs.extend(self._suggest_ghost_absorption(project_id))

        # 3. Renombres sugeridos (categorías con definición expandida)
        recs.extend(self._suggest_renames(project_id))

        # 4. Zonas de neblina (capas no cubiertas, huérfanas)
        recs.extend(self._suggest_sampling_zones(project_id))

        # 5. Tensiones sin resolver
        recs.extend(self._suggest_tension_resolution(project_id))

        # Rankear por impacto
        return sorted(recs, key=lambda r: r.impact_score, reverse=True)

    def _suggest_connections(self, project_id: UUID) -> list[Recommendation]:
        """Pares de categorías con alta co-ocurrencia pero sin relación elaborada."""
        rows = self.db.execute(
            text("""
                SELECT c1.nombre, c2.nombre, COUNT(DISTINCT s1.documento_id) as co_docs,
                       c1.id as id1, c2.id as id2
                FROM codigos_segmento cs1
                JOIN segmentos s1 ON cs1.segmento_id = s1.id
                JOIN codigos_segmento cs2 ON s1.id = cs2.segmento_id
                JOIN categorias c1 ON cs1.categoria_id = c1.id
                JOIN categorias c2 ON cs2.categoria_id = c2.id
                WHERE c1.proyecto_id = :pid
                  AND c1.id < c2.id
                  AND NOT EXISTS (
                      SELECT 1 FROM conceptual_relationships cr
                      WHERE cr.project_id = :pid2
                      AND cr.category_ids @> to_jsonb(ARRAY[c1.id::text, c2.id::text])
                  )
                GROUP BY c1.id, c2.id, c1.nombre, c2.nombre
                HAVING COUNT(DISTINCT s1.documento_id) >= 2
                ORDER BY co_docs DESC
                LIMIT 10
            """),
            {"pid": project_id, "pid2": project_id},
        ).fetchall()

        return [
            Recommendation(
                category="Conexiones sugeridas",
                title=f"'{r[0]}' y '{r[1]}' co-ocurren en {r[2]} docs",
                description=f"Alta co-ocurrencia sin relación elaborada. ¿Las arrastrás juntas para explorar?",
                action_type="connect",
                category_ids=[str(r[3]), str(r[4])],
                impact_score=min(r[2] * 0.25, 1.0),
            )
            for r in rows
        ]

    def _suggest_ghost_absorption(self, project_id: UUID) -> list[Recommendation]:
        """Hipótesis de memos no conectados a ninguna categoría."""
        rows = self.db.execute(
            text("""
                SELECT m.id, m.contenido, m.tipo
                FROM memos m
                WHERE m.proyecto_id = :pid
                  AND m.tipo = 'HIPOTESIS'
                  AND m.id NOT IN (
                      SELECT memo_id FROM elaboration_memos
                      WHERE memo_id IS NOT NULL AND project_id = :pid2
                  )
                LIMIT 5
            """),
            {"pid": project_id, "pid2": project_id},
        ).fetchall()

        return [
            Recommendation(
                category="Ghost-blobs sin absorber",
                title=f"Memo de hipótesis sin conectar",
                description=f"Esta hipótesis podría densificar una categoría existente. Arrastrala hacia un blob.",
                action_type="absorb_ghost",
                category_ids=[str(r[0])],
                impact_score=0.5,
            )
            for r in rows
        ]

    def _suggest_renames(self, project_id: UUID) -> list[Recommendation]:
        """Categorías con ≥ 3 versiones de definición."""
        rows = self.db.execute(
            text("""
                SELECT c.id, c.nombre, COUNT(*) as versions
                FROM categorias c
                JOIN category_definition_versions cdv ON c.id = cdv.category_id
                WHERE c.proyecto_id = :pid
                GROUP BY c.id, c.nombre
                HAVING COUNT(*) >= 3
                LIMIT 5
            """),
            {"pid": project_id},
        ).fetchall()

        return [
            Recommendation(
                category="Renombres sugeridos",
                title=f"'{r[1]}' tiene {r[2]} versiones de definición",
                description="La definición creció. ¿El nombre sigue capturando toda la riqueza?",
                action_type="rename",
                category_ids=[str(r[0])],
                impact_score=min(r[2] * 0.3, 1.0),
            )
            for r in rows
        ]

    def _suggest_sampling_zones(self, project_id: UUID) -> list[Recommendation]:
        """Capas teóricas sin relaciones y categorías huérfanas."""
        # Capas cubiertas
        layers = self.db.execute(
            text("""
                SELECT DISTINCT layer FROM conceptual_relationships
                WHERE project_id = :pid AND layer IS NOT NULL
            """),
            {"pid": project_id},
        ).fetchall()
        covered = {r[0] for r in layers}
        all_layers = {
            "process",
            "conditions",
            "variation",
            "structure",
            "consequences",
            "action",
            "fusion",
        }
        missing = all_layers - covered

        recs = []
        for layer in missing:
            recs.append(
                Recommendation(
                    category="Zonas de neblina",
                    title=f"Capa '{layer}' sin relaciones",
                    description=f"Ninguna relación elaborada cubre esta capa teórica.",
                    action_type="sample",
                    suggested_code=layer,
                    impact_score=0.7,
                )
            )

        # Huérfanas
        orphans = self.db.execute(
            text("""
                SELECT c.id, c.nombre FROM categorias c
                WHERE c.proyecto_id = :pid
                  AND c.id NOT IN (
                      SELECT DISTINCT jsonb_array_elements_text(cr.category_ids)::uuid
                      FROM conceptual_relationships cr
                      WHERE cr.project_id = :pid2
                  )
                LIMIT 5
            """),
            {"pid": project_id, "pid2": project_id},
        ).fetchall()

        for r in orphans:
            recs.append(
                Recommendation(
                    category="Zonas de neblina",
                    title=f"'{r[1]}' no está conectada al modelo",
                    description="Categoría huérfana. ¿Con qué otras se relaciona?",
                    action_type="connect",
                    category_ids=[str(r[0])],
                    impact_score=0.8,
                )
            )

        return recs

    def _suggest_tension_resolution(self, project_id: UUID) -> list[Recommendation]:
        """Relaciones con evidencia divergente sin resolver."""
        rows = self.db.execute(
            text("""
                SELECT cr.id, cr.elaboration_status, cr.diverging_doc_count,
                       cr.researcher_question
                FROM conceptual_relationships cr
                WHERE cr.project_id = :pid
                  AND cr.diverging_doc_count > 0
                  AND cr.divergence_resolution IS NULL
                  AND cr.elaboration_status = 'tense'
                LIMIT 5
            """),
            {"pid": project_id},
        ).fetchall()

        return [
            Recommendation(
                category="Tensiones sin resolver",
                title=f"Relación con {r[2]} datos divergentes: '{r[3][:80]}...'",
                description="Esta relación tiene datos que no encajan. Hacé clic en la fisura para expandirla.",
                action_type="resolve_tension",
                category_ids=[str(r[0])],
                impact_score=0.6,
            )
            for r in rows
        ]
