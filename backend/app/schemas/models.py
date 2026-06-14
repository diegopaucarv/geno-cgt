# backend/app/schemas/models.py
"""
Schemas Pydantic generados automáticamente desde los modelos SQLAlchemy.

Para añadir un nuevo schema, solo importa el modelo y usa la fábrica.
Los campos se derivan automáticamente de las columnas de la tabla.
"""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.domain.category import Categoria, CodigoSegmento
from app.models.domain.document import Documento
from app.models.domain.project import Proyecto
from app.models.domain.segment import Segmento
from app.schemas.factory import create_input_schema, response_schema

# ── Category ──────────────────────────────────────────────────────────

CategoryResponse = response_schema(
    Categoria,
    exclude={"embedding_centroide"},  # no exponer vectores al cliente
)

CategoryCreate = create_input_schema(
    Categoria,
    exclude={
        "embedding_centroide",  # no se crea manualmente
        "estado_saturacion",  # usa default
        "puntaje_relevancia",  # usa default
        "version",  # usa default
    },
)

# ── Segment ───────────────────────────────────────────────────────────

SegmentResponse = response_schema(
    Segmento,
    exclude={"embedding"},  # no exponer el vector de 1024 floats
)

# ── Code Assignment ───────────────────────────────────────────────────

CodeAssignRequest = create_input_schema(
    CodigoSegmento,
    exclude={
        "estado",  # usa default
        "confianza",  # usa default
        "creado_en",
        "actualizado_en",
    },
)

CodeAssignResponse = response_schema(CodigoSegmento)


# ── Recommendations ───────────────────────────────────────────────────


class RecommendationItem(BaseModel):
    categoria: CategoryResponse
    frecuencia: int

    model_config = ConfigDict(from_attributes=True)


# ── Project ───────────────────────────────────────────────────────────

ProjectResponse = response_schema(Proyecto)

ProjectCreate = create_input_schema(
    Proyecto,
    exclude={"estado"},  # usa default "ACTIVO"
)

# ── Document ──────────────────────────────────────────────────────────

DocumentResponse = response_schema(Documento, exclude={"metadatos"})
