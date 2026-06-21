"""
Schema Guard — Detecta drift entre modelos SQLAlchemy y la base de datos real.

Se ejecuta al iniciar FastAPI (en lifespan). Compara las columnas definidas
en los modelos ORM con las columnas reales en PostgreSQL y reporta cualquier
diferencia. Esto previene el error que tuvimos con `context_window_real`.

Reglas:
- Columnas en modelo pero NO en DB → 🚨 DRIFT (el modelo espera una columna que no existe)
- Columnas en DB pero NO en modelo → ⚠️  WARNING (columna huérfana, posible legacy)
- Tipos que no coinciden → ⚠️  WARNING (posible problema de migración)

NO modifica nada — solo reporta.
"""

from __future__ import annotations

import logging
import os
from typing import Any

# ── Importar TODOS los modelos para que Base.metadata los conozca ──
# (igual que env.py — necesario para que metadata.tables esté completo)
from app.models.base import Base
from app.models.domain.agent_outputs import (
    AgentFamilyReference,
    AgentLoopLog,
    AgentOutput,
)
from app.models.domain.canvas import (
    BordeDeLienzo,
    LienzoDelPlanDeAnalisis,
    NodoDeLienzo,
)
from app.models.domain.category import Categoria, CodigoSegmento, DocCode
from app.models.domain.concern import Concern
from app.models.domain.database import DatabaseEdge, DatabaseNode
from app.models.domain.document import Documento
from app.models.domain.document_process import DocumentProcess
from app.models.domain.hitl_decision import HitlDecision
from app.models.domain.incident import (
    ExtractedIncident,
    IncidentComparison,
    IncidentGroup,
)
from app.models.domain.memo import Memo
from app.models.domain.pipeline_run import (
    BatchExecution,
    PipelineRun,
    PipelineTask,
    TaskStepCheckpoint,
)
from app.models.domain.population_context import PopulationContext
from app.models.domain.project import Proyecto
from app.models.domain.project_config_history import ProjectConfigHistory
from app.models.domain.segment import Segmento
from app.models.domain.sorting import (
    MemoSortingAttempt,
    MemoSortingGroup,
)
from app.models.domain.synthesis import (
    CodeDocumentSummary,
    CodeGlobalSummary,
    CodePrototype,
    GraphEntity,
    GraphRelation,
    Hypothesis,
    ParadigmState,
    ProcessingState,
    SaturationMetrics,
)
from app.models.domain.theory import (
    CategoryDefinitionVersion,
    ConceptualRelationship,
    EcosystemLayout,
    ElaborationMemo,
    TheoreticalCode,
)
from app.models.domain.user import Usuario
from app.models.domain.workflow import Fase
from app.models.exec_log import RegistroEjecucionAgente
from app.models.langgraph_checkpoints import LangGraphCheckpoint
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Inspector

logger = logging.getLogger(__name__)

# Mapeo de tipos SQLAlchemy → nombres PostgreSQL (para comparación laxa)
_TYPE_NORMALIZE: dict[str, str] = {
    "VARCHAR": "character varying",
    "CHAR": "character varying",  # CHAR(32) for UUIDs → same as VARCHAR
    "INTEGER": "integer",
    "BIGINT": "bigint",
    "BOOLEAN": "boolean",
    "TEXT": "text",
    "FLOAT": "double precision",
    "REAL": "real",
    "TIMESTAMP": "timestamp without time zone",
    "DATETIME": "timestamp without time zone",
    "DATE": "date",
    "JSON": "jsonb",
    "UUID": "uuid",
    "VECTOR": "USER-DEFINED",  # pgvector extension
}


def _get_sync_inspector() -> Inspector | None:
    """Crea un inspector síncrono de SQLAlchemy para la DB."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return None
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    try:
        engine = create_engine(sync_url, isolation_level="AUTOCOMMIT")
        return inspect(engine)
    except Exception as e:
        logger.warning("No se pudo conectar para validar schema: %s", e)
        return None


def _normalize_type(sql_type: str) -> str:
    """Normaliza nombres de tipo para comparación tolerante."""
    utype = str(sql_type).upper().split("(")[0].strip()
    return _TYPE_NORMALIZE.get(utype, utype.lower())


def validate_schema() -> list[str]:
    """
    Compara modelos SQLAlchemy contra la base de datos real.

    Returns:
        Lista de strings describiendo cada issue encontrado.
        Lista vacía = sin problemas.
    """
    inspector = _get_sync_inspector()
    if not inspector:
        return ["No se pudo conectar a la DB para validar schema"]

    issues: list[str] = []
    db_tables: set[str] = set(inspector.get_table_names())

    # Iterar todas las tablas mapeadas por SQLAlchemy
    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_tables:
            issues.append(
                f"🚨 Tabla '{table_name}' definida en modelo pero NO existe en DB"
            )
            continue

        db_columns: dict[str, dict[str, Any]] = {
            c["name"]: c for c in inspector.get_columns(table_name)
        }
        model_columns: set[str] = {c.name for c in table.columns}

        # Columnas en modelo pero no en DB → DRIFT
        for col_name in sorted(model_columns - set(db_columns.keys())):
            col = table.columns[col_name]
            issues.append(
                f"🚨 Columna '{table_name}.{col_name}' ({col.type}) "
                f"definida en modelo pero NO existe en DB"
            )

        # Columnas en DB pero no en modelo → posible legacy
        for col_name in sorted(set(db_columns.keys()) - model_columns):
            issues.append(
                f"⚠️  Columna '{table_name}.{col_name}' existe en DB "
                f"pero NO en ningún modelo SQLAlchemy (posible legacy)"
            )

        # Tipo mismatch
        for col_name in sorted(model_columns & set(db_columns.keys())):
            model_col = table.columns[col_name]
            db_col = db_columns[col_name]
            model_type = _normalize_type(str(model_col.type))
            db_type = _normalize_type(str(db_col["type"]))

            if model_type != db_type:
                # Permitir diferencias conocidas (nullable JSONB sin default, etc.)
                issues.append(
                    f"⚠️  Tipo mismatch '{table_name}.{col_name}': "
                    f"modelo={model_col.type}, DB={db_col['type']}"
                )

    # Reportar tablas en DB sin modelo (posibles tablas legacy)
    model_tables: set[str] = set(Base.metadata.tables.keys())
    for t in sorted(db_tables - model_tables):
        # Ignorar tablas de sistema y de Alembic
        if t in ("alembic_version", "spatial_ref_sys"):
            continue
        issues.append(f"⚠️  Tabla '{t}' existe en DB pero NO tiene modelo SQLAlchemy")

    return issues
