"""Tests de integración end-to-end 
"""
from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from app.ia.response_validator import AIPlanItem

pytestmark = pytest.mark.asyncio

TOMORROW = date.today() + timedelta(days=1)
DEADLINE = date.today() + timedelta(days=7)


async def _create_task(client, effort_hours: int = 1, priority: int = 3, title: str = "Estudiar"):
    resp = await client.post(
        "/tasks/",
        json={
            "title": title,
            "deadline": DEADLINE.isoformat(),
            "priority": priority,
            "effort_hours": effort_hours,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_availability(client, start="09:00", end="11:00"):
    resp = await client.post(
        "/availability/",
        json={"date": TOMORROW.isoformat(), "start_time": start, "end_time": end},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _valid_plan_item(task_id: str) -> AIPlanItem:
    """Sesión de 60 min dentro de la disponibilidad y antes del deadline."""
    return AIPlanItem(
        tarea_id=task_id,
        dia=TOMORROW,
        bloque_inicio=time(9, 0),
        bloque_fin=time(10, 0),
        orden=1,
    )


async def test_sin_plan_previo_no_se_replanifica(client, fake_ia):
    task = await _create_task(client)
    resp = await client.post("/availability/", json={
        "date": TOMORROW.isoformat(), "start_time": "09:00", "end_time": "11:00",
    })
    assert resp.status_code == 201
    assert resp.headers["x-replan-status"] == "skipped_no_plan"

    latest = await client.get("/plans/latest")
    assert latest.status_code == 404


async def test_ciclo_completo_generar_aprobar_historial_coste(client, fake_ia):
    task = await _create_task(client)
    await _create_availability(client)
    fake_ia.items = [_valid_plan_item(task["id"])]

    gen = await client.post("/ai/plans/generate", json={"scope": "semanal"})
    assert gen.status_code == 200, gen.text
    plan = gen.json()
    assert plan["version"] == 1
    assert plan["response_status"] == "valid"
    assert plan["estado_revision"] == "normal"
    assert plan["viabilidad"] == "viable"
    assert len(plan["plan"]) == 1

    latest = await client.get("/plans/latest")
    assert latest.status_code == 200
    assert latest.json()["id"] == plan["id"]

    approval = await client.patch(
        f"/plans/{plan['id']}/approval", json={"approval_status": "aprobado"}
    )
    assert approval.status_code == 200
    assert approval.json()["approval_status"] == "aprobado"

    history = await client.get("/plans/history")
    assert history.status_code == 200
    actions = [h["action"] for h in history.json()]
    assert "generado" in actions
    assert "aprobado" in actions

    cost = await client.get("/ai/cost", params={"monthly_plans": 30})
    assert cost.status_code == 200
    body = cost.json()
    assert body["modelo_configurado"] == "gpt-4o-mini"
    assert body["tokens_entrada"] == 100
    assert body["tokens_salida"] == 50
    assert body["total_llamadas"] == 1
    assert body["costo_total_usd"] > 0
    assert body["costo_estimado_mensual_usd"] > 0


async def test_replan_automatica_al_actualizar_tarea(client, fake_ia):
    task = await _create_task(client)
    await _create_availability(client)
    fake_ia.items = [_valid_plan_item(task["id"])]

    gen = await client.post("/ai/plans/generate", json={"scope": "semanal"})
    assert gen.json()["version"] == 1

    upd = await client.patch(f"/tasks/{task['id']}", json={"title": "Estudiar más"})
    assert upd.status_code == 200
    assert upd.headers["x-replan-status"] == "replanned_v2"

    latest = await client.get("/plans/latest")
    assert latest.json()["version"] == 2


async def test_fallo_de_ia_es_observable_y_no_pierde_la_mutacion(client, fake_ia):
    task = await _create_task(client)
    await _create_availability(client)
    fake_ia.items = [_valid_plan_item(task["id"])]

    await client.post("/ai/plans/generate", json={"scope": "semanal"})

    fake_ia.behavior = "raise_ia"
    upd = await client.patch(f"/tasks/{task['id']}", json={"title": "Nuevo título"})

    assert upd.status_code == 200
    assert upd.headers["x-replan-status"] == "failed_ERR-SYS-001"
    assert upd.json()["title"] == "Nuevo título"

    cost = await client.get("/ai/cost")
    body = cost.json()
    assert body["total_llamadas"] == 2
    assert body["llamadas_con_tokens"] == 1


async def test_generar_sin_datos_devuelve_422(client, fake_ia):
    gen = await client.post("/ai/plans/generate", json={"scope": "semanal"})
    assert gen.status_code == 422
    assert gen.json()["detail"]["code"] == "ERR-DATA-001"


async def test_plan_invalido_queda_para_revision(client, fake_ia):
    task = await _create_task(client, effort_hours=2)  
    await _create_availability(client, start="09:00", end="11:00")
    fake_ia.items = [_valid_plan_item(task["id"])]

    gen = await client.post("/ai/plans/generate", json={"scope": "semanal"})
    assert gen.status_code == 200
    plan = gen.json()
    assert plan["response_status"] == "invalid"
    assert plan["estado_revision"] == "requiere_revision"
    assert plan["validation_code"] is not None
    assert len(plan["conflictos"]) >= 1
