"""
Engine SQLAlchemy síncrono para worker-nlp.

Los workers no pueden usar asyncpg (Celery es síncrono).
Este módulo espeja ``workers/heavy/database.py``: normaliza ``DATABASE_URL``
al driver psycopg2 y expone ``SessionLocal`` para las tareas de
``saturation.py``.
"""

from __future__ import annotations

import logging

from config import DATABASE_URL as _raw_url
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Asegurar driver síncrono (psycopg2, no asyncpg)
DATABASE_URL = _raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
if not DATABASE_URL.startswith("postgresql+psycopg2"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(bind=engine, class_=Session)


def get_session() -> Session:
    """Devuelve una sesión síncrona. El caller debe cerrarla."""
    session = SessionLocal()
    try:
        return session
    except Exception:
        session.close()
        raise
