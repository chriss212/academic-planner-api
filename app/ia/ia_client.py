"""Cliente de IA generativa (OpenAI).

Única pieza que habla con el proveedor. Usa la Responses API con Structured
Outputs (`responses.parse`), de modo que la respuesta llega ya garantizada
contra el esquema wire; la validación de dominio y de negocio se hace después.
"""
from __future__ import annotations

from dataclasses import dataclass

import openai
from openai import AsyncOpenAI

from app.core.config import settings
from app.ia.response_validator import AIPlanResponseWire


class IAClientError(RuntimeError):
    """Fallo de conexión o indisponibilidad del proveedor (ERR-SYS-001)."""


@dataclass(slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "TokenUsage") -> "TokenUsage":
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class IAClient:
    def __init__(self) -> None:
        self._client = (
            AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.openai_timeout_seconds,
            )
            if settings.openai_api_key
            else None
        )

    async def generate_plan_structured(
        self, system_prompt: str, user_prompt: str
    ) -> tuple[str, AIPlanResponseWire, TokenUsage]:
        """Devuelve (texto crudo, wire model parseado, uso de tokens).

        Lanza IAClientError ante indisponibilidad del servicio y ValueError si
        el modelo rechaza la solicitud o la respuesta queda incompleta.
        """
        if not self._client:
            raise IAClientError("Servicio de IA no disponible: falta OPENAI_API_KEY")

        try:
            response = await self._client.responses.parse(
                model=settings.openai_model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                text_format=AIPlanResponseWire,
                max_output_tokens=settings.openai_max_output_tokens,
            )
        except (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.RateLimitError,
            openai.AuthenticationError,
            openai.InternalServerError,
        ) as error:
            raise IAClientError(f"Servicio de IA no disponible: {error}") from error

        refusal = next(
            (
                item.refusal
                for output in response.output
                if getattr(output, "type", None) == "message"
                for item in output.content
                if getattr(item, "type", None) == "refusal"
            ),
            None,
        )
        if refusal:
            raise ValueError(f"El modelo rechazó la solicitud: {refusal}")

        if response.output_parsed is None:
            raise ValueError("La respuesta del modelo llegó incompleta o sin contenido parseable")

        usage = TokenUsage(
            input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
        )
        return response.output_text, response.output_parsed, usage
