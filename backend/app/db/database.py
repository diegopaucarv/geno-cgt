import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

_raw_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://app_user:strongpass@pgbouncer:6432/gt-db",
)
# docker-compose usa postgresql://, async necesita postgresql+asyncpg://
DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False, pool_size=20, max_overflow=10)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    """Dependency para FastAPI: inyecta una sesión asíncrona de BD."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
