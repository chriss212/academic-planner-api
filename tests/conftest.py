"""Configuración compartida de tests.

Fija un DATABASE_URL ficticio antes de importar la app (para que el engine
declarado en app.database no falle) y monta una base SQLite en memoria para los
tests de integración. Los tipos específicos de PostgreSQL (UUID, JSONB) se
compilan a equivalentes de SQLite mediante hooks @compiles, de modo que los
modelos se usan sin modificarlos.
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/testdb")

from dataclasses import dataclass, field  

import pytest_asyncio  
from httpx import ASGITransport, AsyncClient  
from sqlalchemy.dialects.postgresql import JSONB, UUID  
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  
from sqlalchemy.ext.compiler import compiles  
from sqlalchemy.pool import StaticPool  


@compiles(UUID, "sqlite")
def _compile_uuid_sqlite(element, compiler, **kw):  
    return "CHAR(36)"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  
    return "JSON"


from app.database import Base, get_db  
from app.main import app as fastapi_app  

import app.models.task  
import app.models.availability  
import app.models.constraint  
import app.models.plan  
import app.models.history  
import app.models.ai_trace  


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    session_maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine):
    """Cliente HTTP contra la app con la sesión apuntando a la BD de test."""
    session_maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    fastapi_app.dependency_overrides.clear()



from app.ia.ia_client import IAClientError, TokenUsage  
from app.ia.replan_service import ReplanValidationError  
from app.ia.response_validator import AIPlanResponse  
import app.services.replanning as replanning_module  


@dataclass
class IAController:
    behavior: str = "return"  
    viabilidad: str = "viable"
    justificacion: str = "plan de prueba"
    items: list = field(default_factory=list)
    usage: TokenUsage = field(default_factory=lambda: TokenUsage(input_tokens=100, output_tokens=50))


@pytest_asyncio.fixture
async def fake_ia(monkeypatch):
    controller = IAController()

    class FakeReplanService:
        def __init__(self, *args, **kwargs):
            pass

        async def generate_plan(self, payload, context, task_ids):
            if controller.behavior == "raise_ia":
                raise IAClientError("IA no disponible (simulada)")
            if controller.behavior == "raise_validation":
                raise ReplanValidationError(
                    "respuesta inválida tras reintento (simulada)",
                    prompt="P-04 corrección simulada",
                    raw_response='{"plan": []}',
                )
            parsed = AIPlanResponse(
                version_plan="v1",
                viabilidad=controller.viabilidad,
                plan=list(controller.items),
                justificacion=controller.justificacion,
                riesgos=[],
                conflictos=[],
                recomendaciones=[],
            )
            return "raw-json-simulado", parsed, "prompt-usado-simulado", controller.usage

    monkeypatch.setattr(replanning_module, "ReplanService", FakeReplanService)
    return controller
