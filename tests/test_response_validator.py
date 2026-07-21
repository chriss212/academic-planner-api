"""Tests del contrato de respuesta de IA (nivel 1) — sin red."""
import json
from datetime import date, timedelta
from uuid import uuid4

import pytest

from app.ia.response_validator import (
    AIPlanResponseWire,
    validate_ai_response,
    validate_wire_response,
)

TASK_ID = uuid4()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def _payload(**overrides):
    base = {
        "version_plan": "1",
        "viabilidad": "viable",
        "plan": [
            {
                "tarea_id": str(TASK_ID),
                "dia": TOMORROW,
                "bloque_inicio": "14:00",
                "bloque_fin": "15:30",
                "orden": 1,
            }
        ],
        "justificacion": "Prioridad alta y deadline cercano.",
        "riesgos": [],
        "conflictos": [],
        "recomendaciones": [],
    }
    base.update(overrides)
    return base


def test_respuesta_valida():
    parsed = validate_ai_response(json.dumps(_payload()), [TASK_ID])
    assert parsed.viabilidad == "viable"
    assert parsed.plan[0].tarea_id == TASK_ID


def test_respuesta_con_fences_markdown():
    raw = "```json\n" + json.dumps(_payload()) + "\n```"
    parsed = validate_ai_response(raw, [TASK_ID])
    assert len(parsed.plan) == 1


def test_tarea_id_desconocido_rechazado():
    with pytest.raises(ValueError, match="tarea_id"):
        validate_ai_response(json.dumps(_payload()), [uuid4()])


def test_texto_no_json_rechazado():
    with pytest.raises(ValueError):
        validate_ai_response("no soy json", [TASK_ID])


def test_ventana_invertida_rechazada():
    payload = _payload()
    payload["plan"][0]["bloque_inicio"] = "16:00"
    with pytest.raises(ValueError, match="bloque_fin"):
        validate_ai_response(json.dumps(payload), [TASK_ID])


def test_viabilidad_fuera_de_enum_rechazada():
    with pytest.raises(ValueError):
        validate_ai_response(json.dumps(_payload(viabilidad="imposible")), [TASK_ID])


def test_wire_a_dominio():
    wire = AIPlanResponseWire.model_validate(_payload())
    parsed = validate_wire_response(wire, [TASK_ID])
    assert parsed.plan[0].dia.isoformat() == TOMORROW


def test_wire_con_fecha_invalida_rechazado():
    wire = AIPlanResponseWire.model_validate(_payload())
    wire.plan[0].dia = "lunes"
    with pytest.raises(ValueError):
        validate_wire_response(wire, [TASK_ID])
