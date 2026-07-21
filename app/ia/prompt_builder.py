"""Catálogo de prompts

| ID   | Nombre                          | Versión | Módulo            |
|------|---------------------------------|---------|-------------------|
| P-01 | System prompt base              | v1.0    | prompt_builder.py |
| P-02 | User prompt — generación        | v1.0    | prompt_builder.py |
| P-03 | User prompt — replanificación   | v1.0    | prompt_builder.py |
| P-04 | Prompt de corrección de formato | v1.0    | prompt_builder.py |

El system prompt es fijo y versionado; nunca se genera dinámicamente.
"""
from __future__ import annotations

import json

from app.schemas.plan import PlanGenerationRequest

PROMPT_VERSION = "v1.0"

SYSTEM_PROMPT = (
    "Eres un agente de planificación académica controlado. Generas propuestas de plan "
    "que un humano debe revisar y aprobar; tu salida es una recomendación, nunca una decisión final.\n"
    "Reglas obligatorias:\n"
    "1. No ignores ninguna fecha límite (deadline) declarada; ninguna sesión de una tarea "
    "puede quedar después de su deadline.\n"
    "2. Asigna tareas únicamente dentro de los bloques de disponibilidad declarados "
    "(misma fecha, hora de inicio y fin dentro del bloque).\n"
    "3. Respeta todas las restricciones: blocked_time (no planificar en esos horarios), "
    "fixed_task (no mover esa tarea de su ventana), max_session_hours (ninguna sesión "
    "supera max_session_minutes) y academic_priority (lo académico va primero).\n"
    "4. Prioriza por cercanía de deadline y prioridad (5 es la más alta). Puedes dividir una "
    "tarea en varias sesiones; la suma debe cubrir su esfuerzo estimado en minutos.\n"
    "5. No inventes tareas, fechas ni datos que no fueron proporcionados. Usa exclusivamente "
    "los tarea_id del contexto.\n"
    "6. Si no es posible cumplir todas las restricciones, decláralo en viabilidad "
    "(viable_con_ajustes o no_viable) y detalla los conflictos con día y déficit.\n"
    "7. Explica en justificacion las razones principales del orden, la prioridad y la "
    "distribución del plan.\n"
    "8. El campo dia de cada elemento del plan es una fecha concreta con formato YYYY-MM-DD; "
    "bloque_inicio y bloque_fin usan formato HH:MM de 24 horas.\n"
    "9. Responde únicamente con JSON válido conforme al esquema solicitado, sin texto "
    "adicional ni markdown."
)


def build_generation_prompt(payload: PlanGenerationRequest, context: dict[str, object]) -> str:
    """P-02: generación inicial. Si la solicitud trae change_block, actúa como P-03 (replanificación)."""
    sections = [
        f"[catálogo {PROMPT_VERSION}]",
        f"ALCANCE SOLICITADO: {payload.scope}",
    ]
    if payload.user_note:
        sections.append(f"NOTA DEL USUARIO: {payload.user_note}")
    if payload.change_block:
        sections.append(
            "EVENTO DE CAMBIO (replanifica a partir del plan anterior, no desde cero): "
            + json.dumps(payload.change_block, ensure_ascii=False)
        )
    sections.append("CONTEXTO: " + json.dumps(context, ensure_ascii=False))
    sections.append(
        "Genera el plan cumpliendo todas las reglas del sistema y devuelve solo el JSON del esquema."
    )
    return "\n".join(sections)


def build_correction_prompt(raw_response: str, error_message: str) -> str:
    """P-04: corrección de formato tras una respuesta que no cumple el esquema (ERR-IA-001/002)."""
    return (
        f"[catálogo {PROMPT_VERSION}] Tu respuesta anterior no cumple el esquema esperado. "
        "Corrige únicamente el formato sin cambiar el contenido del plan y devuelve solo JSON válido.\n"
        f"Error detectado: {error_message}\n"
        f"Respuesta original: {raw_response}"
    )
