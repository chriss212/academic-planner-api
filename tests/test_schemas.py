from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.availability import AvailabilityCreate, AvailabilityUpdate
from app.schemas.constraint import ConstraintCreate, ConstraintType, validate_constraint_metadata
from app.schemas.task import TaskCreate, TaskUpdate


TOMORROW = date.today() + timedelta(days=1)
YESTERDAY = date.today() - timedelta(days=1)


class TestTaskSchemas:
    def test_create_valida(self):
        task = TaskCreate(title="Ensayo", deadline=TOMORROW, priority=3, effort_hours=2)
        assert task.priority == 3

    def test_deadline_pasado_rechazado(self):
        with pytest.raises(ValidationError, match="deadline"):
            TaskCreate(title="Ensayo", deadline=YESTERDAY, priority=3, effort_hours=2)

    def test_update_permite_deadline_pasado(self):
        """A diferencia de TaskCreate, actualizar una tarea existente cuyo
        deadline ya venció debe seguir siendo posible (p. ej. marcarla como
        completada) sin que la fecha, ya vencida, bloquee el guardado."""
        update = TaskUpdate(deadline=YESTERDAY)
        assert update.deadline == YESTERDAY

    def test_priority_fuera_de_rango(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="X", deadline=TOMORROW, priority=6, effort_hours=1)

    def test_effort_no_positivo(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="X", deadline=TOMORROW, priority=1, effort_hours=0)


class TestAvailabilitySchemas:
    def test_create_valida(self):
        block = AvailabilityCreate(date=TOMORROW, start_time="14:00", end_time="17:00")
        assert block.date == TOMORROW

    def test_orden_de_tiempos_invalido(self):
        with pytest.raises(ValidationError, match="start_time"):
            AvailabilityCreate(date=TOMORROW, start_time="17:00", end_time="14:00")

    def test_update_parcial_con_ambos_tiempos_invertidos(self):
        with pytest.raises(ValidationError, match="start_time"):
            AvailabilityUpdate(start_time="17:00", end_time="14:00")

    def test_update_parcial_un_solo_tiempo_pasa_schema(self):
        update = AvailabilityUpdate(end_time="18:00")
        assert update.end_time is not None


class TestConstraintMetadata:
    def test_max_session_horas_normaliza_a_minutos(self):
        constraint = ConstraintCreate(
            type=ConstraintType.max_session_hours,
            description="Máximo 1.5 h por sesión",
            metadata={"max_session_hours": 1.5},
        )
        assert constraint.metadata["max_session_minutes"] == 90

    def test_max_session_sin_valor_rechazado(self):
        with pytest.raises(ValidationError, match="max_session"):
            ConstraintCreate(
                type=ConstraintType.max_session_hours,
                description="Sin valor",
                metadata={},
            )

    def test_fixed_task_requiere_task_id(self):
        with pytest.raises(ValidationError, match="task_id"):
            ConstraintCreate(
                type=ConstraintType.fixed_task,
                description="Tarea fija",
                metadata={},
            )

    def test_fixed_task_con_ventana_valida(self):
        constraint = ConstraintCreate(
            type=ConstraintType.fixed_task,
            description="Clase fija",
            metadata={
                "task_id": "5a3c9df0-7d4e-4a4a-8a3f-2f6d1c1b2a3c",
                "date": TOMORROW.isoformat(),
                "start_time": "10:00",
                "end_time": "11:30",
            },
        )
        assert constraint.metadata["date"] == TOMORROW.isoformat()

    def test_blocked_time_requiere_fecha_o_weekday(self):
        with pytest.raises(ValidationError, match="blocked_time"):
            ConstraintCreate(
                type=ConstraintType.blocked_time,
                description="Trabajo",
                metadata={"start_time": "08:00", "end_time": "13:00"},
            )

    def test_blocked_time_con_weekday_valido(self):
        constraint = ConstraintCreate(
            type=ConstraintType.blocked_time,
            description="Trabajo lunes por la mañana",
            metadata={"weekday": "lunes", "start_time": "08:00", "end_time": "13:00"},
        )
        assert constraint.metadata["weekday"] == "lunes"

    def test_academic_priority_sin_metadata(self):
        constraint = ConstraintCreate(
            type=ConstraintType.academic_priority,
            description="Lo académico manda",
        )
        assert constraint.metadata is None

    def test_validador_reutilizable_con_tipo_persistido_string(self):
        normalized = validate_constraint_metadata(
            "max_session_hours",  
            {"max_session_minutes": 45},
        )
        assert normalized["max_session_minutes"] == 45
