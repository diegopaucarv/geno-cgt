from app.models.domain.user import User
from app.services.auth import get_current_user
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/v1", tags=["system"])


@router.get("/ping")
async def ping(current_user: User = Depends(get_current_user)):
    return {"status": "ok", "user_id": current_user.id, "message": "Authenticated"}
