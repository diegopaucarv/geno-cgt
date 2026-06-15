from app.core.security import decode_token, is_token_blacklisted
from app.db.database import get_db
from app.models.domain.user import Usuario
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    # Verificar blacklist
    jti = payload.get("jti")
    if jti and await is_token_blacklisted(jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token revoked"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    # Obtener usuario de BD (user_id es UUID string)
    from sqlalchemy import select

    result = await db.execute(select(Usuario).where(Usuario.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


async def get_current_user_optional(
    credentials = None,
    token: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Auth optional: Bearer header or ?token= query param (for EventSource)."""
    raw_token = None
    if credentials and hasattr(credentials, 'credentials') and credentials.credentials:
        raw_token = credentials.credentials
    elif token:
        raw_token = token
    if not raw_token:
        return None
    try:
        payload = decode_token(raw_token)
        if not payload:
            return None
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti):
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        from sqlalchemy import select
        result = await db.execute(select(Usuario).where(Usuario.id == user_id))
        return result.scalar_one_or_none()
    except Exception:
        return None
