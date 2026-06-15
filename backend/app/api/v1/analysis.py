"""Endpoints de analisis: SaturationGapAnalyzer, population context, config."""

import json
from uuid import UUID

from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user
from app.services.saturation_gap_analyzer import SaturationGapAnalyzer
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.get("/projects/{project_id}/analysis/saturation-gaps")
async def get_saturation_gaps(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """C08: GapReport unificado de 4 fuentes."""
    analyzer = SaturationGapAnalyzer(db)
    report = await analyzer.full_analysis(project_id)
    return {
        "project_id": str(report.project_id),
        "generated_at": report.generated_at,
        "critical": [
            {
                "severity": g.severity,
                "description": g.description,
                "action": g.suggested_action,
            }
            for g in report.critical
        ],
        "warnings": [
            {
                "severity": g.severity,
                "source": g.source,
                "description": g.description,
                "action": g.suggested_action,
            }
            for g in report.warnings
        ],
        "saturated": report.saturated,
    }


@router.post("/projects/{project_id}/analysis/saturation-gaps/refresh")
async def refresh_saturation_gaps(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Re-ejecuta el analisis (boton sync del frontend)."""
    analyzer = SaturationGapAnalyzer(db)
    report = await analyzer.full_analysis(project_id)
    return {
        "status": "refreshed",
        "gaps_found": len(report.critical) + len(report.warnings),
    }


@router.get("/projects/{project_id}/population-context")
async def get_population_context(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Ultima version del contexto poblacional (A1 memory)."""
    row = await db.execute(
        text(
            "SELECT surprising_details, language_patterns, data_production_context, version FROM population_contexts WHERE proyecto_id = :pid ORDER BY version DESC LIMIT 1"
        ),
        {"pid": project_id},
    )
    r = row.fetchone()
    if not r:
        return {
            "surprising_details": "",
            "language_patterns": "",
            "data_production_context": "",
            "version": 0,
        }
    return {
        "surprising_details": r[0],
        "language_patterns": r[1],
        "data_production_context": r[2],
        "version": r[3],
    }


@router.get("/projects/{project_id}/population-context/versions")
async def get_population_context_versions(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Historial de versiones del contexto poblacional."""
    rows = await db.execute(
        text(
            "SELECT version, surprising_details, language_patterns, data_production_context, creado_en FROM population_contexts WHERE proyecto_id = :pid ORDER BY version"
        ),
        {"pid": project_id},
    )
    return [
        {
            "version": r[0],
            "surprising_details": r[1],
            "language_patterns": r[2],
            "data_production_context": r[3],
            "created_at": str(r[4]),
        }
        for r in rows.fetchall()
    ]


# ── Coding Styles (Saldaña library) ──────────────────────────────────

@router.get("/coding-styles")
async def list_coding_styles():
    """Lista de estilos de codificación disponibles (Saldaña-inspired)."""
    from app.core.coding_styles import get_all_styles, get_default_style
    return {
        "styles": get_all_styles(),
        "default": get_default_style(),
    }


@router.put("/projects/{project_id}/config/coding-styles")
async def set_coding_styles(
    project_id: UUID,
    styles: str = Query("gerundio,in_vivo", description="Keys separadas por coma (gerundio,nominalizacion,parafrasis,tema_subtema,causal,in_vivo)"),
    db: AsyncSession = Depends(get_db),
    current_user: Usuario = Depends(get_current_user),
):
    """Configura los estilos de codificación (múltiples) para un proyecto."""
    from app.core.coding_styles import get_all_styles
    from app.core.coding_styles import get_combined_instruction

    keys = [s.strip() for s in styles.split(",") if s.strip()]
    valid_keys = [s for s in keys if s in CODING_STYLES]
    if not valid_keys:
        valid_keys = ["gerundio"]

    await db.execute(
        text(
            "UPDATE proyectos SET population_assumption = "
            "COALESCE(population_assumption, '{}'::jsonb) || "
            "jsonb_build_object('coding_styles', :styles) "
            "WHERE id = :pid"
        ),
        {"styles": json.dumps(valid_keys), "pid": project_id},
    )
    await db.commit()

    all_styles = {s["key"]: s["name"] for s in get_all_styles()}
    return {
        "coding_styles": valid_keys,
        "names": [all_styles.get(k, k) for k in valid_keys],
        "combined_instruction": get_combined_instruction(valid_keys),
    }
