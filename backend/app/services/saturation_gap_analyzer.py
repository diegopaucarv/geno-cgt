"""
SaturationGapAnalyzer — C08 del plan Pre-Coding.

Servicio unificado de analisis de gaps. Combina 4 fuentes de senal:
1. SATURACION MATEMATICA (rolling std)
2. PARADIGM STATE (did_state_expand)
3. EJES DE COMPARACION (TheoSampler — gaps por categoria de variable)
4. DENSIDAD DE RELACIONES (categorias sin conexiones)

Produce GapReport con severidad, sugerencia de accion, y estimacion de impacto.
Invocable como GET /projects/{pid}/analysis/saturation-gaps
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class GapSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class GapSource(str, Enum):
    MATH = "math"  # rolling std
    PARADIGM = "paradigm"  # did_state_expand window
    AXES = "axes"  # TheoSampler variable gaps
    DENSITY = "density"  # relaciones faltantes


@dataclass
class Gap:
    severity: GapSeverity
    source: GapSource
    category_name: str | None
    description: str
    suggested_action: str
    impact_estimate: str | None = None
    detail: dict = field(default_factory=dict)


@dataclass
class GapReport:
    project_id: str
    critical: list[Gap] = field(default_factory=list)
    warnings: list[Gap] = field(default_factory=list)
    saturated: list[str] = field(default_factory=list)
    generated_at: str = ""


class SaturationGapAnalyzer:
    """
    Analizador unificado de gaps de saturacion y elaboracion teorica.
    Combina 4 fuentes de senal en un solo informe accionable.
    """

    def __init__(self, db_session):
        self.db = db_session

    async def full_analysis(self, project_id: UUID) -> GapReport:
        """Ejecuta las 4 fuentes y produce un informe unificado."""
        from datetime import datetime, timezone

        report = GapReport(
            project_id=str(project_id),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # 1. Rolling std gaps
        await self._analyze_math_saturation(report, project_id)

        # 2. Paradigm state gaps
        await self._analyze_paradigm_state(report, project_id)

        # 3. Axes comparison gaps (TheoSampler)
        await self._analyze_sampling_axes(report, project_id)

        # 4. Density gaps (categories without relationships)
        await self._analyze_relationship_density(report, project_id)

        return report

    async def _analyze_math_saturation(self, report: GapReport, project_id: UUID):
        """Categorias con rolling std alto = unsaturated."""
        from sqlalchemy import text

        rows = await self.db.execute(
            text("""
                SELECT c.nombre, sm.rolling_std, sm.saturation_status,
                       sm.documents_since_change
                FROM categorias c
                JOIN saturation_metrics sm ON c.id = sm.code_id
                WHERE c.proyecto_id = :pid
                ORDER BY sm.rolling_std DESC
            """),
            {"pid": project_id},
        )
        for row in rows.fetchall():
            name, std, status, docs = row
            if status == "saturated":
                report.saturated.append(name)
            elif std and std > 0.20:
                report.warnings.append(
                    Gap(
                        severity=GapSeverity.WARNING,
                        source=GapSource.MATH,
                        category_name=name,
                        description=f"Rolling std alto ({std:.2f}). Siguen apareciendo variantes.",
                        suggested_action="Continuar codificacion selectiva para esta categoria.",
                        impact_estimate="Alta — la categoria no ha estabilizado sus propiedades.",
                        detail={"rolling_std": std, "docs_since_change": docs},
                    )
                )

    async def _analyze_paradigm_state(self, report: GapReport, project_id: UUID):
        """Ventana deslizante de 5 iteraciones sin expandir."""
        from sqlalchemy import text

        rows = await self.db.execute(
            text("""
                SELECT c.nombre, ps.did_state_expand, ps.iteration, ps.expansion_type
                FROM categorias c
                JOIN paradigm_states ps ON c.id = ps.code_id
                WHERE c.proyecto_id = :pid
                ORDER BY ps.iteration DESC
            """),
            {"pid": project_id},
        )
        # Grupo por categoria y evalua ventana
        cat_states: dict[str, list] = {}
        for row in rows.fetchall():
            name, expanded, it, etype = row
            if name not in cat_states:
                cat_states[name] = []
            cat_states[name].append(expanded)

        for name, states in cat_states.items():
            if len(states) >= 5 and all(not s for s in states[:5]):
                if name not in report.saturated:
                    report.saturated.append(name)
            elif states and states[0]:  # Ultima iteracion expandio
                report.warnings.append(
                    Gap(
                        severity=GapSeverity.INFO,
                        source=GapSource.PARADIGM,
                        category_name=name,
                        description="Ultimo incidente expandio el paradigma.",
                        suggested_action="Continuar elaboracion hasta 5 iteraciones sin expandir.",
                    )
                )

    async def _analyze_sampling_axes(self, report: GapReport, project_id: UUID):
        """Ejes de comparacion sin documentos = gaps de muestreo."""
        from sqlalchemy import text

        # Categorias con pocos documentos
        rows = await self.db.execute(
            text("""
                SELECT c.nombre, COUNT(DISTINCT cs.segmento_id) as seg_count
                FROM categorias c
                LEFT JOIN codigos_segmento cs ON c.id = cs.categoria_id
                WHERE c.proyecto_id = :pid
                GROUP BY c.id, c.nombre
                HAVING COUNT(DISTINCT cs.segmento_id) < 3
            """),
            {"pid": project_id},
        )
        for row in rows.fetchall():
            name, count = row
            report.warnings.append(
                Gap(
                    severity=GapSeverity.WARNING if count == 0 else GapSeverity.INFO,
                    source=GapSource.AXES,
                    category_name=name,
                    description=f"Solo {count} segmentos asignados.",
                    suggested_action="Muestrear mas documentos que contengan esta categoria.",
                    detail={"segment_count": count or 0},
                )
            )

    async def _analyze_relationship_density(self, report: GapReport, project_id: UUID):
        """Categorias sin relaciones elaboradas."""
        from sqlalchemy import text

        rows = await self.db.execute(
            text("""
                SELECT c.nombre
                FROM categorias c
                WHERE c.proyecto_id = :pid
                  AND c.id NOT IN (
                      SELECT DISTINCT category_ids::jsonb->>0 FROM conceptual_relationships
                      UNION
                      SELECT DISTINCT category_ids::jsonb->>1 FROM conceptual_relationships
                  )
            """),
            {"pid": project_id},
        )
        for row in rows.fetchall():
            name = row[0]
            report.warnings.append(
                Gap(
                    severity=GapSeverity.INFO,
                    source=GapSource.DENSITY,
                    category_name=name,
                    description="Categoria sin relaciones elaboradas.",
                    suggested_action="Conectar con otras categorias en el Theoretical Playground.",
                )
            )
