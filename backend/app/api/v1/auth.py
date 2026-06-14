import uuid
from datetime import datetime, timezone

from app.core.security import (
    add_token_to_blacklist,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.database import get_db
from app.models.domain.user import Usuario
from app.services.auth import get_current_user, security
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login")
async def login(email: str, password: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Usuario).where(Usuario.correo == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    access_token = create_access_token(data={"sub": str(user.id), "jti": access_jti})
    refresh_token = create_refresh_token(data={"sub": str(user.id), "jti": refresh_jti})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(
    current_user: Usuario = Depends(get_current_user),
    token: str = Depends(security),
):
    payload = decode_token(token.credentials)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        ttl = exp - int(datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await add_token_to_blacklist(jti, ttl)
    return {"msg": "Logged out"}
