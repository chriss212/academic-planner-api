"""Tests de la orquestación de replanificación

"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.ia.ia_client import IAClientError, TokenUsage
from app.ia.replan_service import ReplanService, ReplanValidationError
from app.ia.response_validator import AIPlanItemWire, AIPlanResponseWire
from app.schemas.plan import PlanGenerationRequest
import app.services.replanning as replanning
from app.services.replanning import try_auto_replan

TASK_ID = uuid.uuid4()


class FakeDb:
    """Stub mínimo para probar la ruta de manejo de errores de try_auto_replan
    sin una sesión real: solo necesita responder a rollback()."""

    def __init__(self) -> None:
        self.rolled_back = False

    async def rollback(self) -> None:
        self.rolled_back = True


def _wire(tarea_id: str) -> AIPlanResponseWire:
    return AIPlanResponseWire(
        version_plan="v1",
        viabilidad="viable",
        plan=[
            AIPlanItemWire(
                tarea_id=tarea_id,
                dia="2026-07-21",
                bloque_inicio="09:00",
                bloque_fin="10:00",
                orden=1,
            )
        ],
        justificacion="ok",
        riesgos=[],
        conflictos=[],
        recomendaciones=[],
    )


class FakeIAClient:
    """Devuelve respuestas encoladas; registra los prompts recibidos."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def generate_plan_structured(self, system_prompt, user_prompt):
        self.prompts.append(user_prompt)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _payload() -> PlanGenerationRequest:
    return PlanGenerationRequest(scope="semanal", user_note=None, change_block=None)


async def test_generate_plan_valido_a_la_primera():
    client = FakeIAClient([("raw-1", _wire(str(TASK_ID)), TokenUsage(100, 50))])
    service = ReplanService(client=client)

    raw, parsed, prompt, usage = await service.generate_plan(_payload(), context={}, task_ids=[TASK_ID])

    assert raw == "raw-1"
    assert str(parsed.plan[0].tarea_id) == str(TASK_ID)
    assert usage.input_tokens == 100 and usage.output_tokens == 50
    assert len(client.prompts) == 1


async def test_generate_plan_reintenta_una_vez_y_suma_tokens():
    # Primera respuesta con tarea_id inventado -> falla dominio -> reintento P-04 válido.
    client = FakeIAClient(
        [
            ("raw-mala", _wire("no-es-uuid"), TokenUsage(100, 50)),
            ("raw-buena", _wire(str(TASK_ID)), TokenUsage(80, 40)),
        ]
    )
    service = ReplanService(client=client)

    raw, parsed, prompt, usage = await service.generate_plan(_payload(), context={}, task_ids=[TASK_ID])

    assert raw == "raw-buena"
    assert len(client.prompts) == 2
    assert "no cumple el esquema" in client.prompts[1]  # prompt de corrección P-04
    assert prompt == client.prompts[1]
    assert usage.input_tokens == 180 and usage.output_tokens == 90


async def test_generate_plan_falla_tras_reintento_con_contexto():
    client = FakeIAClient(
        [
            ("raw-mala-1", _wire("no-es-uuid"), TokenUsage(1, 1)),
            ("raw-mala-2", _wire("tampoco-uuid"), TokenUsage(1, 1)),
        ]
    )
    service = ReplanService(client=client)

    with pytest.raises(ReplanValidationError) as exc_info:
        await service.generate_plan(_payload(), context={}, task_ids=[TASK_ID])

    # El error conserva prompt y respuesta cruda para poder trazarlos en ai_traces.
    assert exc_info.value.raw_response == "raw-mala-2"
    assert "no cumple el esquema" in exc_info.value.prompt


async def test_generate_plan_propaga_error_de_proveedor():
    client = FakeIAClient([IAClientError("caído")])
    service = ReplanService(client=client)

    with pytest.raises(IAClientError):
        await service.generate_plan(_payload(), context={}, task_ids=[TASK_ID])


async def test_auto_replan_se_salta_sin_plan_previo(monkeypatch):
    async def no_plan(db, user_id):
        return None

    called = False

    async def should_not_run(db, user_id, payload):
        nonlocal called
        called = True

    monkeypatch.setattr(replanning, "_latest_plan", no_plan)
    monkeypatch.setattr(replanning, "generate_and_persist_plan", should_not_run)

    status = await try_auto_replan(db=None, user_id=uuid.uuid4(), payload=_payload())

    assert status == "skipped_no_plan"
    assert not called  # sin plan previo no se gasta una llamada a la IA


async def test_auto_replan_devuelve_version_generada(monkeypatch):
    async def existing_plan(db, user_id):
        return SimpleNamespace(version=2)

    async def fake_generate(db, user_id, payload):
        return SimpleNamespace(version=3)

    monkeypatch.setattr(replanning, "_latest_plan", existing_plan)
    monkeypatch.setattr(replanning, "generate_and_persist_plan", fake_generate)

    status = await try_auto_replan(db=None, user_id=uuid.uuid4(), payload=_payload())

    assert status == "replanned_v3"


async def test_auto_replan_no_propaga_fallo_y_lo_expone(monkeypatch):
    async def existing_plan(db, user_id):
        return SimpleNamespace(version=1)

    async def failing_generate(db, user_id, payload):
        raise HTTPException(status_code=503, detail={"code": "ERR-SYS-001", "message": "IA caída"})

    monkeypatch.setattr(replanning, "_latest_plan", existing_plan)
    monkeypatch.setattr(replanning, "generate_and_persist_plan", failing_generate)

    fake_db = FakeDb()
    status = await try_auto_replan(db=fake_db, user_id=uuid.uuid4(), payload=_payload())

    assert status == "failed_ERR-SYS-001"
    assert fake_db.rolled_back


async def test_auto_replan_no_propaga_fallo_inesperado(monkeypatch):
    """Un fallo no anticipado (p. ej. una colisión de versión por concurrencia,
    IntegrityError) tampoco debe tumbar la mutación que disparó el replan."""

    async def existing_plan(db, user_id):
        return SimpleNamespace(version=1)

    async def failing_generate(db, user_id, payload):
        raise RuntimeError("duplicate key value violates unique constraint")

    monkeypatch.setattr(replanning, "_latest_plan", existing_plan)
    monkeypatch.setattr(replanning, "generate_and_persist_plan", failing_generate)

    fake_db = FakeDb()
    status = await try_auto_replan(db=fake_db, user_id=uuid.uuid4(), payload=_payload())

    assert status == "failed_ERR-SYS-002"
    assert fake_db.rolled_back
