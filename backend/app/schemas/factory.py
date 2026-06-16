# backend/app/schemas/factory.py
"""
Fábrica de schemas Pydantic a partir de modelos SQLAlchemy.

Uso:
    from app.schemas.factory import response_schema, create_schema
    from app.models.domain.category import Categoria

    CategoryResponse = response_schema(Categoria, exclude={"embedding_centroide"})
    CategoryCreate = create_schema(Categoria, exclude={"id", "creado_en", "actualizado_en", "embedding_centroide"})
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Type

from pydantic import BaseModel, ConfigDict, create_model
from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase

# ── Type mapping para tipos que sqlalchemy no mapea automáticamente ──

_CUSTOM_TYPE_MAP: dict[str, type] = {
    # pgvector
    "VECTOR": list[float],
    "vector": list[float],
    # JSONB can be dict or list
    "JSONB": dict | list,
    "JSON": dict | list,
}

# ── Columnas que típicamente se excluyen ──

AUTO_FIELDS = {"id", "creado_en", "actualizado_en"}
SENSITIVE_FIELDS = {"hashed_password"}
VECTOR_FIELDS = {"embedding", "embedding_centroide", "centroid"}


def _resolve_python_type(col, model_cls: Type[DeclarativeBase]) -> type:
    """
    Obtiene el tipo Python de una columna.
    1. Intenta col.type.python_type (funciona para la mayoría)
    2. Fallback al _CUSTOM_TYPE_MAP (pgvector)
    3. Fallback a la anotación Mapped[] de la clase (FK sin tipo explícito)
    """
    # Intento 1: mapa custom (pgvector, JSONB, etc.)
    type_name = type(col.type).__name__
    if type_name in _CUSTOM_TYPE_MAP:
        return _CUSTOM_TYPE_MAP[type_name]

    # Intento 2: python_type nativo
    try:
        return col.type.python_type
    except NotImplementedError:
        pass

    # Intento 3: leer de la anotación Mapped[] de la clase
    # SQLAlchemy 2.0: FK sin tipo explícito → NullType, pero la anotación lo tiene
    import typing

    hints = typing.get_type_hints(model_cls, include_extras=False)
    if col.name in hints:
        hint = hints[col.name]
        # Extraer el tipo interno de Mapped[T] o Optional[Mapped[T]]
        origin = typing.get_origin(hint)
        if origin is not None:
            args = typing.get_args(hint)
            if args:
                hint = args[0]  # Quitar Optional[...]
                origin = typing.get_origin(hint)
                if origin is not None:
                    args = typing.get_args(hint)
                    if args:
                        hint = args[0]
        else:
            # Si no es genérico, asumimos que es el tipo directo
            pass
        if isinstance(hint, type):
            return hint

    return str


def _make_optional(py_type: type, col) -> type:
    """Si la columna es nullable o tiene default, la hace opcional."""
    if col.nullable or col.default is not None or col.server_default is not None:
        return py_type | None
    return py_type


def create_schema(
    model_cls: Type[DeclarativeBase],
    *,
    exclude: set[str] | None = None,
    include: set[str] | None = None,
    optional: set[str] | None = None,
    name: str | None = None,
) -> Type[BaseModel]:
    """
    Genera un schema Pydantic a partir de un modelo SQLAlchemy.

    Args:
        model_cls: la clase del modelo (ej. Categoria)
        exclude: columnas a omitir
        include: si se especifica, SOLO estas columnas (ignora exclude)
        optional: columnas que deben ser opcionales aunque no sean nullable
        name: nombre de la clase resultante (default: {ModelName}Schema)
    """
    exclude = exclude or set()
    optional = optional or set()
    name = name or f"{model_cls.__name__}Schema"

    fields: dict[str, tuple[type, Any]] = {}

    mapper = inspect(model_cls)
    for col in mapper.columns:
        if include is not None and col.name not in include:
            continue
        if include is None and col.name in exclude:
            continue

        py_type = _resolve_python_type(col, model_cls)

        if col.name in optional or col.default is not None:
            py_type = py_type | None
        else:
            py_type = _make_optional(py_type, col)

        if col.default is not None:
            fields[col.name] = (py_type, col.default.arg)
        elif col.nullable:
            fields[col.name] = (py_type, None)
        else:
            fields[col.name] = (py_type, ...)

    model = create_model(
        name,
        __config__=ConfigDict(from_attributes=True),
        **fields,
    )
    return model


def response_schema(
    model_cls: Type[DeclarativeBase],
    *,
    exclude: set[str] | None = None,
    name: str | None = None,
) -> Type[BaseModel]:
    """
    Schema para respuestas (GET).
    Excluye automáticamente campos sensibles como hashed_password.
    """
    exclude = (exclude or set()) | SENSITIVE_FIELDS
    name = name or f"{model_cls.__name__}Response"
    return create_schema(model_cls, exclude=exclude, name=name)


def create_input_schema(
    model_cls: Type[DeclarativeBase],
    *,
    exclude: set[str] | None = None,
    name: str | None = None,
) -> Type[BaseModel]:
    """
    Schema para entrada (POST).
    Excluye automáticamente id, timestamps auto-generados.
    """
    exclude = (exclude or set()) | AUTO_FIELDS | SENSITIVE_FIELDS
    name = name or f"{model_cls.__name__}Create"
    return create_schema(model_cls, exclude=exclude, name=name)
