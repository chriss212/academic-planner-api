# Academic Planner API

REST API para planificación académica inteligente. Permite gestionar tareas, bloques de disponibilidad y restricciones de tiempo, con integración a IA generativa (Claude de Anthropic) para generar y replanificar planes de estudio automáticamente.

## Características

- **Tareas** — CRUD completo con prioridad (1-5), deadline, estimación de esfuerzo y estados (`pending`, `in_progress`, `completed`, `overdue`, `rescheduled`)
- **Disponibilidad** — Registro de bloques horarios libres por fecha
- **Restricciones** — Definición de restricciones de planificación (`blocked_time`, `max_session_hours`, `fixed_task`, `academic_priority`)
- **Planificación con IA** — Integración con Claude (Anthropic) para generar planes optimizados según disponibilidad y restricciones

## Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Framework web | FastAPI 0.139 |
| Base de datos | PostgreSQL (Supabase) |
| ORM | SQLAlchemy 2.0 (async) |
| Driver async | asyncpg |
| Validación | Pydantic v2 |
| IA generativa | Anthropic SDK (Claude) |
| Servidor ASGI | Uvicorn |

## Requisitos previos

- Python 3.11+
- Instancia de PostgreSQL (recomendado: [Supabase](https://supabase.com))
- API key de [Anthropic](https://console.anthropic.com)

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

Editar `.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres
ANTHROPIC_API_KEY=sk-ant-...
AI_MODEL=claude-sonnet-4-6
```

## Levantar el servidor

```bash
uvicorn app.main:app --reload
```

La API quedará disponible en `http://localhost:8000`.

Documentación interactiva (Swagger UI): `http://localhost:8000/docs`

## Endpoints principales

### Tareas (`/tasks`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/tasks/` | Crear tarea |
| `GET` | `/tasks/` | Listar todas las tareas |
| `GET` | `/tasks/{id}` | Obtener tarea por ID |
| `PATCH` | `/tasks/{id}` | Actualizar tarea |
| `DELETE` | `/tasks/{id}` | Eliminar tarea |

### Disponibilidad (`/availability`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/availability/` | Registrar bloque de tiempo libre |
| `GET` | `/availability/` | Listar bloques |
| `DELETE` | `/availability/{id}` | Eliminar bloque |

### Restricciones (`/constraints`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/constraints/` | Crear restricción |
| `GET` | `/constraints/` | Listar restricciones |
| `DELETE` | `/constraints/{id}` | Eliminar restricción |

### Estado

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/health` | Verificar que la API responde |

## Estructura del proyecto

```
academic-planner-api/
├── app/
│   ├── main.py              # Punto de entrada, registro de routers
│   ├── database.py          # Engine y sesión async de SQLAlchemy
│   ├── core/
│   │   └── config.py        # Settings desde variables de entorno
│   ├── models/              # Modelos SQLAlchemy (tablas)
│   │   ├── task.py
│   │   ├── availability.py
│   │   └── constraint.py
│   ├── schemas/             # Schemas Pydantic (request / response)
│   │   ├── task.py
│   │   ├── availability.py
│   │   └── constraint.py
│   ├── routers/             # Endpoints FastAPI
│   │   ├── tasks.py
│   │   ├── availability.py
│   │   ├── constraints.py
│   │   ├── plans.py
│   │   └── ai.py
│   └── services/            # Lógica de negocio e integración con IA
│       ├── planning.py
│       ├── validation.py
│       └── replanning.py
├── requirements.txt
├── .env.example
└── README.md
```
