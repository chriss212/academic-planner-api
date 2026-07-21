# Academic Planner API

API REST para planificación académica inteligente. Gestiona tareas, bloques de disponibilidad y restricciones de tiempo, y usa IA generativa (OpenAI) para **generar y replanificar** planes de estudio. La IA produce propuestas que un humano revisa y aprueba: la salida es siempre una recomendación, nunca una decisión final.

> Este repositorio es solo el **backend**. El frontend se mantiene por separado.

## Características

- **Tareas** — CRUD con prioridad (1-5), deadline, esfuerzo estimado y estados (`pending`, `in_progress`, `completed`, `overdue`, `rescheduled`). Panel de seguimiento por estado (`/tasks/summary`).
- **Disponibilidad** — Bloques horarios libres por **fecha** concreta, con validación de solapamientos.
- **Restricciones** — `blocked_time`, `max_session_hours`, `fixed_task`, `academic_priority`, con metadatos validados por tipo.
- **Planificación con IA** — Genera planes con OpenAI usando *Structured Outputs* (esquema garantizado). Incluye análisis previo (datos insuficientes, sobrecarga, deadlines en riesgo) y validación posterior de reglas de negocio.
- **Replanificación automática** — Al crear/editar/eliminar tareas, disponibilidad o restricciones, si ya existe un plan se replanifica sobre el plan anterior. El resultado se expone en la cabecera `X-Replan-Status`.
- **Trazabilidad** — Cada llamada a la IA (exitosa o fallida) se registra en `ai_traces` con prompt, respuesta, estado y tokens. El historial guarda el motivo de cada cambio.
- **Estimación de coste** — Endpoint que calcula el coste operativo a partir de los tokens reales trazados.

## Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Framework web | FastAPI 0.139 |
| Base de datos | PostgreSQL (Supabase) |
| ORM | SQLAlchemy 2.0 (async) |
| Driver async | asyncpg |
| Migraciones | Alembic |
| Validación | Pydantic v2 |
| IA generativa | OpenAI SDK (`gpt-4o-mini` por defecto) |
| Servidor ASGI | Uvicorn |
| Tests | pytest + pytest-asyncio + httpx |

## Requisitos previos

- Python 3.11+
- Instancia de PostgreSQL (recomendado: [Supabase](https://supabase.com))
- API key de [OpenAI](https://platform.openai.com)

## Instalación

```bash
# 1. Clonar el repositorio
git clone <repo-url>
cd academic-planner-api

# 2. Crear y activar el entorno virtual
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Copiar el archivo de ejemplo y completar los valores:

```bash
cp .env.example .env
```

Variables de entorno (`.env`):

```env
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres

# OpenAI (proveedor de IA generativa)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# Precios del modelo en USD por 1M de tokens (para la estimación de coste)
OPENAI_PRICE_INPUT_PER_1M=0.15
OPENAI_PRICE_OUTPUT_PER_1M=0.60

# CORS
FRONTEND_ORIGIN=http://localhost:3000
```

`OPENAI_MODEL` usa `gpt-4o-mini` por su bajo coste y soporte de *Structured Outputs*. Los precios por defecto corresponden a ese modelo; ajústalos si cambian las tarifas.

## Migraciones de base de datos

El esquema se gestiona con Alembic:

```bash
# Aplicar todas las migraciones
alembic upgrade head

# Crear una nueva migración tras cambiar los modelos
alembic revision -m "descripcion" --autogenerate
```

## Levantar el servidor

```bash
uvicorn app.main:app --reload
```

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

## Autenticación

Los endpoints leen el usuario del header `Authorization: Bearer <jwt>` (se usa el claim `sub`). Sin header se emplea un usuario temporal de desarrollo. La verificación de firma del JWT queda a cargo del gateway/frontend.

## Endpoints

### Tareas (`/tasks`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/tasks/` | Crear tarea (dispara replanificación si hay plan) |
| `GET` | `/tasks/` | Listar tareas (filtro opcional `?status=`) |
| `GET` | `/tasks/summary` | Conteo de tareas por estado |
| `GET` | `/tasks/{id}` | Obtener tarea |
| `PATCH` | `/tasks/{id}` | Actualizar tarea (dispara replanificación) |
| `DELETE` | `/tasks/{id}` | Eliminar tarea (dispara replanificación) |

### Disponibilidad (`/availability`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/availability/` | Registrar bloque libre (valida solapamientos) |
| `GET` | `/availability/` | Listar bloques |
| `PATCH` | `/availability/{id}` | Actualizar bloque |
| `DELETE` | `/availability/{id}` | Eliminar bloque |

### Restricciones (`/constraints`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/constraints/` | Crear restricción |
| `GET` | `/constraints/` | Listar restricciones |
| `PATCH` | `/constraints/{id}` | Actualizar restricción |
| `DELETE` | `/constraints/{id}` | Eliminar restricción |

### Planes (`/plans`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/plans/` | Listar versiones de plan |
| `GET` | `/plans/latest` | Último plan generado |
| `GET` | `/plans/history` | Historial de acciones sobre planes |
| `GET` | `/plans/{id}` | Obtener un plan |
| `PATCH` | `/plans/{id}` | Editar el plan manualmente (revalida reglas de negocio) |
| `PATCH` | `/plans/{id}/approval` | Aprobar / rechazar / marcar como editado |

### IA (`/ai`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/ai/plans/generate` | Generar (o replanificar) un plan |
| `GET` | `/ai/cost` | Estimación de coste operativo (`?monthly_plans=` para proyección mensual) |

### Estado

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Verificar que la API responde |

## Cabecera `X-Replan-Status`

Las mutaciones de tareas, disponibilidad y restricciones devuelven esta cabecera indicando el resultado de la replanificación automática:

- `skipped_no_plan` — aún no hay ningún plan; no se gasta una llamada a la IA.
- `replanned_v<N>` — se generó la versión N.
- `failed_<código>` — la replanificación falló; la mutación **sí** se conservó y el detalle queda en logs y en `ai_traces`.

## Tests

```bash
pytest -q
```

Los tests no consumen la API real de OpenAI ni requieren PostgreSQL: usan un doble de la IA y una base SQLite en memoria (los tipos de PostgreSQL se compilan a equivalentes de SQLite en `tests/conftest.py`).

## Estructura del proyecto

```
academic-planner-api/
├── app/
│   ├── main.py              # Punto de entrada, routers y CORS
│   ├── database.py          # Engine y sesión async de SQLAlchemy
│   ├── core/
│   │   ├── config.py        # Settings desde variables de entorno
│   │   └── auth.py          # Extracción de usuario desde el JWT
│   ├── models/              # Modelos SQLAlchemy (tablas)
│   ├── schemas/             # Schemas Pydantic (request / response)
│   ├── routers/             # Endpoints FastAPI (tasks, availability, constraints, plans, ai)
│   ├── ia/                  # Cliente OpenAI, prompts y validación de respuesta
│   │   ├── ia_client.py
│   │   ├── prompt_builder.py
│   │   ├── replan_service.py
│   │   └── response_validator.py
│   └── services/            # Lógica de negocio
│       ├── planning.py      # Análisis previo a la IA
│       ├── validation.py    # Reglas de negocio posteriores a la IA
│       ├── replanning.py    # Orquestación de generación/replanificación
│       └── cost.py          # Estimación de coste
├── alembic/                 # Migraciones de base de datos
├── tests/                   # Tests unitarios y de integración
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```
