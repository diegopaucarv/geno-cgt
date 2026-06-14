import os
from datetime import datetime, timedelta, timezone

import redis.asyncio as redis
from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

# Configuración desde variables de entorno
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# Hashing de contraseñas
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Conexión a Redis (para blacklist)
redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"))


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def add_token_to_blacklist(jti: str, expires_in: int):
    """Agrega el jti (JWT ID) a Redis con TTL igual a la expiración del token"""
    await redis_client.setex(f"blacklist:{jti}", expires_in, "revoked")


async def is_token_blacklisted(jti: str) -> bool:
    return await redis_client.exists(f"blacklist:{jti}") == 1


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
