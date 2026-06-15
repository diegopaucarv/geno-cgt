"""SSE endpoint para notificaciones en tiempo real del pipeline (B22).

Los workers publican eventos via Redis pub/sub en el canal project:{id}:events.
El frontend se suscribe via EventSource con ?token= en query string.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/events", tags=["events"])


async def _event_stream(proyecto_id: str):
    """Generador SSE. Se suscribe a Redis pub/sub y transmite eventos."""
    try:
        import redis.asyncio as aioredis
    except ImportError:
        while True:
            yield f"data: {json.dumps({'type': 'heartbeat', 'note': 'redis not available'})}\n\n"
            await asyncio.sleep(15)

    redis_client = aioredis.from_url("redis://redis:6379", decode_responses=True)
    channel = f"project:{proyecto_id}:events"
    try:
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(channel)
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30.0)
            if message and message.get("data"):
                yield f"data: {message['data']}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel)
        except Exception:
            pass
        try:
            await redis_client.close()
        except Exception:
            pass


@router.get("/stream")
async def stream_events(
    proyecto_id: UUID = Query(..., description="ID del proyecto"),
    token: str | None = Query(None, description="JWT token (EventSource compat)"),
):
    """
    Stream SSE de eventos del pipeline. Usar con EventSource:
        const es = new EventSource('/api/v1/events/stream?proyecto_id=...&token=...');
    """
    return StreamingResponse(
        _event_stream(str(proyecto_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def publish_event(proyecto_id: str, event_type: str, data: dict) -> None:
    """Publica un evento en Redis para que el SSE endpoint lo transmita."""
    try:
        import redis
        r = redis.from_url("redis://redis:6379", decode_responses=True)
        payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
        r.publish(f"project:{proyecto_id}:events", payload)
    except Exception as e:
        logger.warning("Failed to publish event %s: %s", event_type, e)
