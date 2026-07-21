# Trazabilidad del proyecto — Agente Generativo de Planificación Académica

Documento de defensa que mapea cada requisito de los enunciados
(`Agente_Generativo_Planificacion_Academica_Personal.pdf` y
`diseno_tecnico_ia_planificacion.pdf`) con su implementación en el backend, más
el catálogo de prompts, el catálogo de errores y los escenarios de prueba.

> La implementación usa **OpenAI `gpt-4o-mini`**, opción permitida
> explícitamente por el enunciado (sección 11, "IA generativa: OpenAI, Azure
> OpenAI, Gemini, Claude, …") y elegida por su bajo coste y su soporte de
> *Structured Outputs*, que garantiza el esquema JSON de respuesta.

---

## 1. Requisitos funcionales (RF)

| Código | Requisito | Dónde se implementa |
|--------|-----------|---------------------|
| RF-01 | Gestión de tareas | `app/routers/tasks.py` (CRUD + `?status=`), `app/models/task.py`, `app/schemas/task.py` (estados `pending/in_progress/completed/overdue/rescheduled`) |
| RF-02 | Disponibilidad | `app/routers/availability.py` (CRUD, `_check_no_overlap`), `app/models/availability.py` (bloques por **fecha**), `app/schemas/availability.py` |
| RF-03 | Priorización | `app/schemas/task.py` (`priority` 1-5, `deadline`, `effort_hours`), validado por Pydantic y `CheckConstraint` en BD |
| RF-04 | Plan generativo | `POST /ai/plans/generate` → `app/services/replanning.py`, `app/ia/` (cliente, prompts, validación) |
| RF-05 | Justificación | Campo `justificacion` en el plan; regla 7 del `SYSTEM_PROMPT` (`app/ia/prompt_builder.py`) |
| RF-06 | Revisión humana | `PATCH /plans/{id}` (editar y revalidar), `PATCH /plans/{id}/approval` (aprobar/rechazar/editado); "solicitar nueva versión" = volver a `POST /ai/plans/generate` |
| RF-07 | Replanificación | `app/services/replanning.py` (`try_auto_replan`, `generate_and_persist_plan`), disparada por los CRUD; `app/ia/replan_service.py` (reintento P-04); cabecera `X-Replan-Status` |
| RF-08 | Detección de conflictos | Pre-IA: `app/services/planning.py` (`analyze_planning_input`: sobrecarga, deadlines en riesgo, datos insuficientes). Post-IA: `app/services/validation.py` (`validate_plan_business_rules`) |
| RF-09 | Historial | `app/models/history.py` (incluye `change_block` con el motivo del cambio), `GET /plans/history` |
| RF-10 | Trazabilidad de IA | `app/models/ai_trace.py` (prompt, respuesta, modelo, versión, tokens); se traza también el fallo (`_record_failed_trace`) |
| RF-11 | Panel de seguimiento | `GET /tasks/summary` (`app/routers/tasks.py`): conteo por estado |
| RF-12 | Manejo de errores | Catálogo `ERR-*` en routers y servicios (ver sección 4) |

## 2. Requisitos no funcionales (RNF)

| Código | Categoría | Dónde se cumple |
|--------|-----------|-----------------|
| RNF-01 | Arquitectura | Separación por responsabilidades: `routers/`, `services/`, `ia/`, `models/`, `schemas/`, `core/` |
| RNF-02 | Seguridad | `app/core/config.py` lee de entorno; `.env.example` sin secretos reales; `.env` fuera de control de versiones |
| RNF-03 | Privacidad | Solo datos académicos; escenarios de prueba ficticios (ver `tests/`) |
| RNF-04 | Validación | `app/schemas/*` (Pydantic), `app/services/validation.py`, `app/ia/response_validator.py` (2 niveles) |
| RNF-05 | Trazabilidad | `ai_traces` + `history_entries` (prompt, respuesta, versión, ajustes del usuario, estado de aprobación) |
| RNF-06 | Manejo de errores | Respuestas con `code` y `message` claros; fallos de auto-replan expuestos en `X-Replan-Status` sin perder datos |
| RNF-07 | Usabilidad | Responsabilidad del frontend (fuera del alcance de este backend) |
| RNF-08 | Mantenibilidad | `README.md`, `requirements.txt` con versiones fijadas, migraciones Alembic, suite de tests |

## 3. Catálogo de prompts

| ID | Nombre | Versión | Módulo | Objetivo |
|----|--------|---------|--------|----------|
| P-01 | System prompt base | v1.0 | `app/ia/prompt_builder.py` (`SYSTEM_PROMPT`) | Reglas fijas: no ignorar deadlines, respetar disponibilidad y restricciones, salida JSON, no inventar datos, marcar viabilidad |
| P-02 | User prompt — generación | v1.0 | `app/ia/prompt_builder.py` (`build_generation_prompt`) | Envía el contexto completo (tareas + disponibilidad + restricciones + análisis previo) |
| P-03 | User prompt — replanificación | v1.0 | `app/ia/prompt_builder.py` (`build_generation_prompt` con `change_block`) | Agrega el evento de cambio y el plan anterior para pedir una nueva versión |
| P-04 | Prompt de corrección | v1.0 | `app/ia/prompt_builder.py` (`build_correction_prompt`), invocado en `app/ia/replan_service.py` | Reintento único cuando la respuesta no pasa la validación de dominio |

La versión activa se marca con `PROMPT_VERSION` en `prompt_builder.py`.

## 4. Catálogo de errores

| Código | Situación | Comportamiento | Dónde |
|--------|-----------|----------------|-------|
| ERR-DATA-001 | Datos incompletos (sin tareas o sin disponibilidad) | No se llama a la IA; `422` indicando qué falta | `app/services/replanning.py` (vía `analyze_planning_input`) |
| ERR-DATA-002 | Bloque de disponibilidad solapado o `end_time <= start_time` | `422` antes de persistir | `app/routers/availability.py` |
| ERR-IA-001 | Respuesta inválida de dominio tras reintento P-04 | Reintento único; si vuelve a fallar, `502` + traza `invalid` | `app/ia/replan_service.py`, `app/services/replanning.py` |
| ERR-IA-004 | La IA violó una restricción declarada (nivel 2) | Plan marcado `requiere_revision`, no se muestra como final | `app/services/validation.py` |
| ERR-PLAN-001 | Conflicto no resoluble (más trabajo del que cabe) | Plan `no_viable`, se listan conflictos por día con déficit | `app/services/validation.py` |
| ERR-SYS-001 | Fallo de conexión con el proveedor (timeout, 5xx, auth) | `503` "servicio no disponible"; no se pierden datos; traza `error` | `app/ia/ia_client.py`, `app/services/replanning.py` |

> **ERR-IA-002 (falta campo) y ERR-IA-003 (viabilidad fuera del enum).** En el
> diseño original se manejaban como reintentos. Con *Structured Outputs* de
> OpenAI (`responses.parse` + modelo `AIPlanResponseWire`), el esquema y los
> enums quedan **garantizados por el proveedor**, por lo que estos casos no
> llegan a producirse en la práctica. Si aun así la respuesta llegara incompleta
> o rechazada, se trata como `ERR-IA-001`/`ERR-SYS-001` (ver
> `app/ia/ia_client.py`).

## 5. Escenarios de prueba obligatorios

| Escenario | Descripción | Cobertura automatizada |
|-----------|-------------|------------------------|
| 1 — Semana académica normal | Camino feliz: generación → validación niveles 1 y 2 → plan propuesto → aprobación | `tests/test_integration.py::test_ciclo_completo_generar_aprobar_historial_coste` |
| 2 — Semana con sobrecarga | Esfuerzo > disponibilidad → conflictos con déficit, `ERR-PLAN-001` / plan que requiere revisión | `tests/test_validation.py` (`ERR-PLAN-001`), `tests/test_integration.py::test_plan_invalido_queda_para_revision` |
| 3 — Semana con cambio inesperado | Plan existente + cambio (PATCH tarea) → replanificación v2, nueva traza | `tests/test_integration.py::test_replan_automatica_al_actualizar_tarea`, `::test_fallo_de_ia_es_observable_y_no_pierde_la_mutacion` |

Los tests usan un doble de la IA y SQLite en memoria (`tests/conftest.py`), por
lo que no consumen la API real ni requieren PostgreSQL. Para la evidencia de
defensa con la IA real, ejecutar los 3 escenarios contra la app con una
`OPENAI_API_KEY` válida y adjuntar prompt, respuesta cruda y decisión del
usuario (quedan guardados en `ai_traces` y `history_entries`).

## 6. Estimación de coste operativo

`GET /ai/cost` (`app/services/cost.py`) calcula el coste a partir de los tokens
reales trazados en `ai_traces` y de los precios configurados
(`OPENAI_PRICE_INPUT_PER_1M`, `OPENAI_PRICE_OUTPUT_PER_1M`). Con
`?monthly_plans=N` proyecta el gasto mensual según el número esperado de
planificaciones. Justifica la elección de `gpt-4o-mini` frente a modelos más
caros.

## 7. Desviaciones respecto al diseño original

- **Proveedor de IA**: Claude → OpenAI `gpt-4o-mini` (permitido por el enunciado).
- **Disponibilidad por fecha** concreta en lugar de día de la semana, para
  soportar planes semanales con fechas reales.
- **Structured Outputs** en lugar de parsing manual de texto: elimina en la
  práctica `ERR-IA-002`/`ERR-IA-003`.
- **`ai_traces`** añade `tokens_entrada`/`tokens_salida` (no estaban en el
  diseño) para habilitar la estimación de coste.
- **`history_entries`** añade `change_block` para registrar el motivo tipado de
  cada replanificación (RF-09).
