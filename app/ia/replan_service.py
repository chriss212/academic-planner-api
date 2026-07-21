from __future__ import annotations

from app.ia.ia_client import IAClient, TokenUsage
from app.ia.prompt_builder import SYSTEM_PROMPT, build_correction_prompt, build_generation_prompt
from app.ia.response_validator import AIPlanResponse, validate_wire_response
from app.schemas.plan import PlanGenerationRequest


class ReplanService:
    def __init__(self, client: IAClient | None = None) -> None:
        self.client = client or IAClient()

    async def generate_plan(
        self,
        payload: PlanGenerationRequest,
        context: dict[str, object],
        task_ids,
    ) -> tuple[str, AIPlanResponse, str, TokenUsage]:
        """Devuelve (respuesta cruda, plan validado, prompt usado, tokens).

        Structured Outputs garantiza el esquema wire; aun así el modelo puede
        devolver datos inválidos de dominio (tarea_id inventado, fechas mal
        formadas). En ese caso se hace un único reintento con P-04 (ERR-IA-001).
        """
        prompt = build_generation_prompt(payload, context)
        raw_response, wire, usage = await self.client.generate_plan_structured(SYSTEM_PROMPT, prompt)

        try:
            parsed = validate_wire_response(wire, task_ids)
            return raw_response, parsed, prompt, usage
        except ValueError as first_error:
            retry_prompt = build_correction_prompt(raw_response, str(first_error))
            retry_response, retry_wire, retry_usage = await self.client.generate_plan_structured(
                SYSTEM_PROMPT, retry_prompt
            )
            parsed = validate_wire_response(retry_wire, task_ids)
            return retry_response, parsed, retry_prompt, usage.add(retry_usage)
