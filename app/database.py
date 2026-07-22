from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=True,        # muestra las queries en consola, útil para debug
    pool_size=5,
    max_overflow=10,
    connect_args={"statement_cache_size": 0},  # requerido por el pgbouncer del pooler de Supabase (modo transaction)
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise