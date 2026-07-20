from __future__ import annotations

import json

from app.schemas.plan import PlanGenerationRequest


def build_generation_prompt(payload: PlanGenerationRequest, context: dict[str, object]) -> str:
    return (
        "Eres un agente de planificación académica. Devuelve SOLO JSON válido sin markdown. "
        "Respeta exactamente este esquema: version_plan, viabilidad, plan, justificacion, riesgos, conflictos, recomendaciones. "
        "Cada elemento de plan debe incluir tarea_id, dia, bloque_inicio, bloque_fin y orden. "
        "Si no hay forma de cumplir, devuelve viabilidad=no_viable y explica los conflictos.\n\n"
        f"SOLICITUD: {json.dumps(payload.model_dump(mode='json'), ensure_ascii=False)}\n"
        f"CONTEXTO: {json.dumps(context, ensure_ascii=False)}"
    )


def build_correction_prompt(raw_response: str, error_message: str) -> str:
    return (
        "La respuesta anterior no cumple el esquema esperado. Corrige y devuelve SOLO JSON válido. "
        f"Error detectado: {error_message}.\n"
        f"Respuesta original: {raw_response}"
    )