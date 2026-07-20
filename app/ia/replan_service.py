from __future__ import annotations

from dataclasses import dataclass

from app.ia.ia_client import IAClient, IAClientError
from app.ia.prompt_builder import build_correction_prompt, build_generation_prompt
from app.ia.response_validator import validate_claude_response
from app.schemas.plan import PlanGenerationRequest


@dataclass(slots=True)
class IAResult:
    raw_response: str
    parsed_response: object


class ReplanService:
    def __init__(self, client: IAClient | None = None) -> None:
        self.client = client or IAClient()

    async def generate_plan(
        self,
        payload: PlanGenerationRequest,
        context: dict[str, object],
        task_ids,
    ) -> tuple[str, object, str]:
        prompt = build_generation_prompt(payload, context)
        raw_response = await self.client.generate_text(prompt)

        try:
            parsed = validate_claude_response(raw_response, task_ids)
            return raw_response, parsed, prompt
        except ValueError as first_error:
            retry_prompt = build_correction_prompt(raw_response, str(first_error))
            retry_response = await self.client.generate_text(retry_prompt)
            parsed = validate_claude_response(retry_response, task_ids)
            return retry_response, parsed, retry_prompt