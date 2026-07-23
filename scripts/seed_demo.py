"""Seed de datos demo para los 3 escenarios obligatorios de la rúbrica (sección 4.1):

1. Semana normal        -> user_normal@demo.com
2. Semana con sobrecarga -> user_overload@demo.com
3. Cambio inesperado     -> user_change@demo.com

Idempotente: si alguno de los 3 correos ya existe, borra primero todos sus datos
(tareas, disponibilidad, restricciones, planes, historial, trazas de IA) y al
usuario mismo, para volver a crear todo desde cero con ids frescos.

No llama a la IA real (OpenAI) — el plan del escenario 3 se inserta directamente
en la tabla `plans` como dato semilla, etiquetado como tal en `prompt_enviado`/
`respuesta_ia`, para no gastar la API ni depender de que esté configurada.

Uso (desde la raíz del repo, con el venv activado y DATABASE_URL apuntando a la
base real — Supabase/Postgres, NO la SQLite de tests):

    python -m scripts.seed_demo

Credenciales de los 3 usuarios: la contraseña es la misma para los tres,
DEMO_PASSWORD (ver abajo). Quedan impresas al final de la ejecución.
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import date, datetime, timedelta

# La consola de Windows suele quedar en cp1252, que no puede codificar "✓" ni
# tildes — sin esto, el script revienta a mitad de camino (con ROLLBACK, pero
# sucio de todos modos) apenas intenta imprimir el primer resumen.
sys.stdout.reconfigure(encoding="utf-8")

from sqlalchemy import delete, select

from app.core.security import hash_password
from app.database import AsyncSessionLocal, engine
from app.models.ai_trace import AITrace
from app.models.availability import AvailabilityBlock
from app.models.constraint import Constraint
from app.models.history import HistoryEntry
from app.models.plan import Plan
from app.models.task import Task
from app.models.user import User

DEMO_PASSWORD = "Demo1234!"
TODAY = date.today()


def in_days(n: int) -> date:
    return TODAY + timedelta(days=n)


async def _delete_user_and_data(session, email: str) -> None:
    """Borra un usuario demo previo y todo lo que le pertenece, si existía."""
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return

    user_id = user.id
    # Orden defensivo (padres antes que el usuario); no depende de que las
    # FKs tengan ON DELETE CASCADE configurado a nivel de base de datos.
    await session.execute(delete(HistoryEntry).where(HistoryEntry.user_id == user_id))
    await session.execute(delete(AITrace).where(AITrace.user_id == user_id))
    await session.execute(delete(Plan).where(Plan.user_id == user_id))
    await session.execute(delete(Task).where(Task.user_id == user_id))
    await session.execute(delete(AvailabilityBlock).where(AvailabilityBlock.user_id == user_id))
    await session.execute(delete(Constraint).where(Constraint.user_id == user_id))
    await session.execute(delete(User).where(User.id == user_id))


async def _create_user(session, email: str, name: str) -> User:
    user = User(email=email, name=name, hashed_password=hash_password(DEMO_PASSWORD))
    session.add(user)
    await session.flush()  # asigna user.id sin cerrar la transacción
    return user


def _task(user_id, title, category, deadline, priority, effort_hours) -> Task:
    return Task(
        user_id=user_id,
        title=title,
        description=f"Tarea semilla ({title}) creada por scripts/seed_demo.py.",
        category=category,
        deadline=deadline,
        priority=priority,
        effort_hours=effort_hours,
        status="pending",
    )


def _time(value: str):
    """'HH:MM' -> datetime.time. asyncpg exige un time real, no un string
    (a diferencia de la capa Pydantic de la API, que sí lo coerciona)."""
    return datetime.strptime(value, "%H:%M").time()


def _block(user_id, block_date, start_time, end_time, label) -> AvailabilityBlock:
    return AvailabilityBlock(
        user_id=user_id,
        date=block_date,
        start_time=_time(start_time),
        end_time=_time(end_time),
        label=label,
    )


async def seed_normal(session) -> None:
    """Escenario 1: semana normal — 4 tareas (8h) caben en 3 bloques (12h)."""
    user = await _create_user(session, "user_normal@demo.com", "Usuario Semana Normal")

    session.add_all(
        [
            _task(user.id, "Ensayo de Historia", "academico", in_days(2), 4, 2),
            _task(user.id, "Entrega de Álgebra Lineal", "academico", in_days(3), 3, 2),
            _task(user.id, "Rutina de gimnasio", "salud", in_days(4), 2, 2),
            _task(user.id, "Preparar presentación de trabajo", "trabajo", in_days(5), 3, 2),
        ]
    )
    session.add_all(
        [
            _block(user.id, in_days(0), "08:00", "12:00", "Mañana libre"),
            _block(user.id, in_days(1), "14:00", "18:00", "Tarde de estudio"),
            _block(user.id, in_days(3), "09:00", "13:00", "Bloque largo de fin de semana"),
        ]
    )
    print(f"  ✓ {user.email} — 4 tareas (8h) / 3 bloques (12h)")


async def seed_overload(session) -> None:
    """Escenario 2: sobrecarga — 5 tareas (20h) contra solo 2 bloques (8h). Déficit: 12h."""
    user = await _create_user(session, "user_overload@demo.com", "Usuario Sobrecarga")

    session.add_all(
        [
            _task(user.id, "Proyecto final de Base de Datos", "academico", in_days(2), 5, 4),
            _task(user.id, "Ensayo de Filosofía", "academico", in_days(2), 4, 4),
            _task(user.id, "Informe de Laboratorio de Física", "academico", in_days(3), 4, 4),
            _task(user.id, "Preparar examen de Estadística", "academico", in_days(3), 5, 4),
            _task(user.id, "Entrega de Proyecto de Trabajo", "trabajo", in_days(4), 3, 4),
        ]
    )
    session.add_all(
        [
            _block(user.id, in_days(0), "18:00", "22:00", "Noche entre semana"),
            _block(user.id, in_days(2), "18:00", "22:00", "Noche entre semana"),
        ]
    )
    print(f"  ✓ {user.email} — 5 tareas (20h) / 2 bloques (8h) → déficit de 12h esperado")


async def seed_change(session) -> None:
    """Escenario 3: cambio inesperado — 2 tareas equilibradas + un plan ya
    'propuesto' cargado. Al agregar una 3ra tarea desde la UI, RF-07 dispara
    la replanificación automática (try_auto_replan) y se demuestra el escenario.
    """
    user = await _create_user(session, "user_change@demo.com", "Usuario Cambio Inesperado")

    task_lectura = _task(user.id, "Lectura de Cálculo III", "academico", in_days(2), 3, 2)
    task_natacion = _task(user.id, "Entrenamiento de natación", "salud", in_days(3), 2, 2)
    session.add_all([task_lectura, task_natacion])

    session.add_all(
        [
            _block(user.id, in_days(0), "16:00", "19:00", "Tarde libre"),
            _block(user.id, in_days(2), "16:00", "19:00", "Tarde libre"),
        ]
    )

    # flush para tener los UUID reales de las tareas antes de armar el plan
    await session.flush()

    dia_1 = in_days(0).isoformat()
    dia_2 = in_days(2).isoformat()

    plan_items = [
        {
            "tarea_id": str(task_lectura.id),
            "dia": dia_1,
            "bloque_inicio": "16:00:00",
            "bloque_fin": "18:00:00",
            "orden": 1,
            "task_title": task_lectura.title,
            "priority": task_lectura.priority,
            "status": "programada",
        },
        {
            "tarea_id": str(task_natacion.id),
            "dia": dia_2,
            "bloque_inicio": "16:00:00",
            "bloque_fin": "18:00:00",
            "orden": 2,
            "task_title": task_natacion.title,
            "priority": task_natacion.priority,
            "status": "programada",
        },
    ]

    prompt_enviado = (
        "[SEED] scripts/seed_demo.py — plan sintético para el escenario 'cambio "
        "inesperado'; no se llamó a la IA real. Contexto: 2 tareas académicas/salud "
        "equilibradas contra 2 bloques de disponibilidad con margen holgado."
    )
    respuesta_ia = json.dumps(
        {
            "version_plan": "v1",
            "viabilidad": "viable",
            "plan": plan_items,
            "justificacion": (
                "Ambas tareas caben cómodamente dentro de los bloques de "
                "disponibilidad registrados, sin conflictos ni sobrecarga."
            ),
            "riesgos": [],
            "conflictos": [],
            "recomendaciones": [],
        },
        ensure_ascii=False,
    )
    justificacion = (
        "Plan semilla para demostrar 'cambio inesperado': agregá una tarea nueva "
        "desde la UI para disparar la replanificación automática (RF-07)."
    )

    plan = Plan(
        user_id=user.id,
        version=1,
        version_plan="v1",
        scope="semanal",
        viabilidad="viable",
        justificacion=justificacion,
        riesgos=[],
        conflictos=[],
        recomendaciones=[],
        plan=plan_items,
        prompt_enviado=prompt_enviado,
        respuesta_ia=respuesta_ia,
        response_status="valid",
        modelo_usado="seed-demo",
        validation_code=None,
        estado_revision="normal",
        approval_status="propuesto",
    )
    session.add(plan)
    await session.flush()  # asigna plan.id para el HistoryEntry

    session.add(
        HistoryEntry(
            user_id=user.id,
            plan_id=plan.id,
            version=plan.version,
            scope=plan.scope,
            action="generado",
            approval_status="propuesto",
            prompt_used=prompt_enviado,
            respuesta_ia=respuesta_ia,
            user_note="Plan semilla (scripts/seed_demo.py) — escenario 'cambio inesperado'.",
        )
    )
    print(f"  ✓ {user.email} — 2 tareas (4h) / 2 bloques (6h) / plan v1 'propuesto' ya cargado")


async def main() -> None:
    emails = ["user_normal@demo.com", "user_overload@demo.com", "user_change@demo.com"]

    async with AsyncSessionLocal() as session:
        print("Limpiando datos previos de los 3 correos demo (si existían)...")
        for email in emails:
            await _delete_user_and_data(session, email)
        await session.flush()

        print("Creando escenarios...")
        await seed_normal(session)
        await seed_overload(session)
        await seed_change(session)

        await session.commit()

    await engine.dispose()

    print("\nListo. Credenciales (misma contraseña para los 3):")
    for email in emails:
        print(f"  - {email}  /  {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
