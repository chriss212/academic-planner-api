"""Tests del motor de reglas"""
from datetime import date, time, timedelta
from uuid import uuid4

from app.schemas.availability import AvailabilityOut
from app.schemas.constraint import ConstraintOut, ConstraintType
from app.schemas.plan import PlanItemOut
from app.schemas.task import TaskOut, TaskStatus
from app.services.planning import analyze_planning_input
from app.services.validation import validate_plan_business_rules

USER = uuid4()
TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)
DAY_AFTER = TODAY + timedelta(days=2)
YESTERDAY = TODAY - timedelta(days=1)


def _task(**kwargs) -> TaskOut:
    defaults = dict(
        id=uuid4(),
        user_id=USER,
        title="Tarea",
        description=None,
        category="academica",
        deadline=DAY_AFTER,
        priority=3,
        effort_hours=2,
        status=TaskStatus.pending,
        created_at=None,
    )
    defaults.update(kwargs)
    return TaskOut(**defaults)


def _block(**kwargs) -> AvailabilityOut:
    defaults = dict(
        id=uuid4(),
        user_id=USER,
        date=TOMORROW,
        start_time=time(14, 0),
        end_time=time(17, 0),
        label=None,
    )
    defaults.update(kwargs)
    return AvailabilityOut(**defaults)


def _item(task_id, **kwargs) -> PlanItemOut:
    defaults = dict(
        tarea_id=task_id,
        dia=TOMORROW,
        bloque_inicio=time(14, 0),
        bloque_fin=time(15, 0),
        orden=1,
    )
    defaults.update(kwargs)
    return PlanItemOut(**defaults)


def _constraint(type_: ConstraintType, description: str, metadata: dict) -> ConstraintOut:
    return ConstraintOut(
        id=uuid4(),
        user_id=USER,
        type=type_,
        description=description,
        metadata=metadata,
    )


class TestPrePlanningAnalysis:
    def test_faltan_datos(self):
        result = analyze_planning_input([], [], [])
        assert not result.is_ready
        assert "tareas" in result.missing

    def test_sobrecarga_detectada(self):
        tasks = [_task(effort_hours=10, deadline=DAY_AFTER)]  
        blocks = [_block()]  
        result = analyze_planning_input(tasks, blocks, [])
        assert result.is_ready
        assert result.overload
        assert result.deficit_minutes == 420

    def test_deadline_en_riesgo(self):
        tasks = [_task(effort_hours=5, deadline=TOMORROW)]  
        blocks = [_block(date=TOMORROW)]  
        result = analyze_planning_input(tasks, blocks, [])
        assert str(tasks[0].id) in result.deadlines_at_risk

    def test_overdue_detectado(self):
        tasks = [_task(deadline=YESTERDAY, status=TaskStatus.pending)]
        blocks = [_block()]
        result = analyze_planning_input(tasks, blocks, [], today=TODAY)
        assert str(tasks[0].id) in result.overdue_task_ids


class TestBusinessValidation:
    def test_plan_valido(self):
        task = _task(effort_hours=1)
        blocks = [_block()]
        items = [_item(task.id, bloque_inicio=time(14, 0), bloque_fin=time(15, 0))]
        result = validate_plan_business_rules(items, [task], blocks, [])
        assert result.is_valid

    def test_fuera_de_disponibilidad(self):
        task = _task(effort_hours=1)
        blocks = [_block(start_time=time(14, 0), end_time=time(16, 0))]
        items = [_item(task.id, bloque_inicio=time(16, 0), bloque_fin=time(17, 0))]
        result = validate_plan_business_rules(items, [task], blocks, [])
        assert not result.is_valid
        assert any(c.tipo == "fuera_de_disponibilidad" for c in result.conflictos)
        assert result.validation_code == "ERR-IA-004"

    def test_blocked_time(self):
        task = _task(effort_hours=1)
        blocks = [_block(start_time=time(8, 0), end_time=time(18, 0))]
        constraints = [
            _constraint(
                ConstraintType.blocked_time,
                "Trabajo",
                {
                    "date": TOMORROW.isoformat(),
                    "start_time": "08:00",
                    "end_time": "13:00",
                },
            )
        ]
        items = [_item(task.id, bloque_inicio=time(9, 0), bloque_fin=time(10, 0))]
        result = validate_plan_business_rules(items, [task], blocks, constraints)
        assert any(c.tipo == "blocked_time" for c in result.conflictos)

    def test_max_session_hours(self):
        task = _task(effort_hours=3)
        blocks = [_block(start_time=time(14, 0), end_time=time(18, 0))]
        constraints = [
            _constraint(
                ConstraintType.max_session_hours,
                "Máximo 90 min",
                {"max_session_minutes": 90},
            )
        ]
        items = [_item(task.id, bloque_inicio=time(14, 0), bloque_fin=time(17, 0))]  
        result = validate_plan_business_rules(items, [task], blocks, constraints)
        assert any(c.tipo == "excede_duracion_maxima" for c in result.conflictos)

    def test_fixed_task_fuera_de_ventana(self):
        task = _task(effort_hours=1)
        blocks = [_block(start_time=time(14, 0), end_time=time(18, 0))]
        constraints = [
            _constraint(
                ConstraintType.fixed_task,
                "Clase fija",
                {
                    "task_id": str(task.id),
                    "date": TOMORROW.isoformat(),
                    "start_time": "15:00",
                    "end_time": "16:00",
                },
            )
        ]
        items = [_item(task.id, bloque_inicio=time(14, 0), bloque_fin=time(15, 0))]
        result = validate_plan_business_rules(items, [task], blocks, constraints)
        assert any(c.tipo == "restriccion_violada" for c in result.conflictos)

    def test_solape_entre_sesiones(self):
        t1 = _task(effort_hours=1, title="A")
        t2 = _task(effort_hours=1, title="B")
        blocks = [_block(start_time=time(14, 0), end_time=time(18, 0))]
        items = [
            _item(t1.id, bloque_inicio=time(14, 0), bloque_fin=time(15, 30), orden=1),
            _item(t2.id, bloque_inicio=time(15, 0), bloque_fin=time(16, 0), orden=2),
        ]
        result = validate_plan_business_rules(items, [t1, t2], blocks, [])
        assert any(c.tipo == "solape_entre_sesiones" for c in result.conflictos)

    def test_despues_del_deadline(self):
        task = _task(effort_hours=1, deadline=TOMORROW)
        blocks = [_block(date=DAY_AFTER, start_time=time(14, 0), end_time=time(17, 0))]
        items = [
            _item(
                task.id,
                dia=DAY_AFTER,
                bloque_inicio=time(14, 0),
                bloque_fin=time(15, 0),
            )
        ]
        result = validate_plan_business_rules(items, [task], blocks, [])
        assert any(c.tipo == "despues_del_deadline" for c in result.conflictos)

    def test_esfuerzo_insuficiente(self):
        task = _task(effort_hours=3)  
        blocks = [_block()]
        items = [_item(task.id, bloque_inicio=time(14, 0), bloque_fin=time(15, 0))]  # 60 min
        result = validate_plan_business_rules(items, [task], blocks, [])
        assert any(c.tipo == "esfuerzo_insuficiente" for c in result.conflictos)

    def test_sobrecarga_por_dia_err_plan_001(self):
        t1 = _task(effort_hours=2, title="A")
        t2 = _task(effort_hours=2, title="B")
        blocks = [_block(start_time=time(14, 0), end_time=time(17, 0))]  # 180 min
        items = [
            _item(t1.id, bloque_inicio=time(14, 0), bloque_fin=time(15, 0), orden=1),
            _item(t2.id, bloque_inicio=time(15, 0), bloque_fin=time(16, 0), orden=2),
        ]
        result = validate_plan_business_rules(items, [t1, t2], blocks, [])
        assert not result.is_valid
        assert any(c.tipo == "sobrecarga" for c in result.conflictos)
        assert result.validation_code == "ERR-PLAN-001"
        assert result.forced_viabilidad == "no_viable"

    def test_tarea_sin_tiempo(self):
        task = _task(effort_hours=2)
        other = _task(effort_hours=1)
        blocks = [_block()]
        items = [_item(other.id, bloque_inicio=time(14, 0), bloque_fin=time(15, 0))]
        result = validate_plan_business_rules(items, [task, other], blocks, [])
        assert any(c.tipo == "tarea_sin_tiempo" and c.tarea_id == task.id for c in result.conflictos)
