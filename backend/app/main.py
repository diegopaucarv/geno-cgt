from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import (
    analysis,
    auth,
    coding,
    documents,
    elaboration,
    events,
    hypotheses,
    ping,
    pipeline,
    projects,
    rag,
    theoretical_codes,
)
from app.core.minio_client import minio_client
from app.db.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    await minio_client.ensure_bucket_exists()
    # Seed theoretical codes vía Celery (la BD se inicializa con sync sessions)
    try:
        from app.core.celery_app import celery_app

        celery_app.send_task("seed_theoretical_codes", queue="heavy")
    except Exception:
        pass  # Silencioso: Redis puede no estar listo aún
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

app.include_router(auth.router)
app.include_router(coding.router)
app.include_router(documents.router)
app.include_router(hypotheses.router)
app.include_router(ping.router)
app.include_router(pipeline.router)
app.include_router(projects.router)
app.include_router(rag.router)
app.include_router(events.router)
app.include_router(analysis.router)
app.include_router(theoretical_codes.router)
app.include_router(elaboration.router)
