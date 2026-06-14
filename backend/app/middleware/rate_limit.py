import time

from app.core.security import redis_client
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        key = f"rate_limit:{client_ip}"
        current = await redis_client.incr(key)
        if current == 1:
            await redis_client.expire(key, 60)  # 1 minuto
        if current > 100:  # 100 requests por minuto
            raise HTTPException(status_code=429, detail="Too many requests")
        return await call_next(request)
