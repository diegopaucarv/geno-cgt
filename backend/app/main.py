import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    admin,
    analysis,
    auth,
    chain_runs,
    coding,
    config_info,
    documents,
    elaboration,
    events,
    hitl,
    hypotheses,
    memos,
    ping,
    pipeline,
    projects,
    rag,
    setup,
    theoretical_codes,
)
from app.core.minio_client import minio_client
from app.db.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 0. Run pending DB migrations BEFORE anything else ──
    _log_startup = __import__("logging").getLogger("uvicorn")
    try:
        from alembic import command as alembic_command
        from alembic.config import Config as AlembicConfig

        alembic_ini = os.path.join(os.path.dirname(__file__), "..", "alembic.ini")
        if os.path.exists(alembic_ini):
            alembic_cfg = AlembicConfig(alembic_ini)
            alembic_command.upgrade(alembic_cfg, "head")
            _log_startup.info("✅ Migraciones aplicadas — schema up-to-date")
    except Exception as e:
        _log_startup.warning(f"⚠️  No se pudieron ejecutar migraciones: {e}")

    # ── 1. Validate schema — detecta drift entre modelos y DB ──
    try:
        from app.core.schema_guard import validate_schema

        issues = validate_schema()
        drift_issues = [i for i in issues if i.startswith("🚨")]
        warn_issues = [i for i in issues if i.startswith("⚠️")]

        if drift_issues:
            _log_startup.error(
                f"🚨 SCHEMA DRIFT ({len(drift_issues)} breaking issues):\n"
                + "\n".join(f"  • {i}" for i in drift_issues[:10])
            )
            if len(drift_issues) > 10:
                _log_startup.error(f"  ... y {len(drift_issues) - 10} más")
        else:
            _log_startup.info("✅ Schema validado — sin drift bloqueante")

        if warn_issues:
            _log_startup.info(
                f"ℹ️  {len(warn_issues)} advertencias no-bloqueantes (columnas legacy, tipos)"
            )
    except Exception as e:
        _log_startup.warning(f"⚠️  Schema validation skipped: {e}")

    await minio_client.ensure_bucket_exists()
    # Seed theoretical codes al iniciar (usa psycopg2 sync, no asyncpg)
    try:
        import logging as _log
        import os

        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text
        from sqlalchemy.orm import sessionmaker

        sync_url = os.getenv("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
        if sync_url:
            sync_engine = create_engine(sync_url)
            SyncSession = sessionmaker(bind=sync_engine)
            s = SyncSession()
            try:
                from app.services.theory_seeder import seed_theoretical_codes

                inserted = seed_theoretical_codes(s)
                if inserted:
                    _log.getLogger("uvicorn").info(
                        f"Seeded {inserted} theoretical codes"
                    )
            finally:
                s.close()
                sync_engine.dispose()
    except Exception as e:
        import logging as _log

        _log.getLogger("uvicorn").warning(f"Seed skipped: {e}")
    yield
    await engine.dispose()


app = FastAPI(
    title="GT API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(chain_runs.router)
app.include_router(coding.router)
app.include_router(documents.router)
app.include_router(hypotheses.router)
app.include_router(ping.router)
app.include_router(pipeline.router)
app.include_router(projects.router)
app.include_router(rag.router)
app.include_router(events.router)
app.include_router(analysis.router)
app.include_router(config_info.router)
app.include_router(theoretical_codes.router)
app.include_router(elaboration.router)
app.include_router(hitl.router)
app.include_router(memos.router)
app.include_router(setup.router)
