from __future__ import annotations

from anthropic import Anthropic

from app.core.config import settings


class IAClientError(RuntimeError):
    pass


class IAClient:
    def __init__(self) -> None:
        self._client = Anthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None

    async def generate_text(self, prompt: str) -> str:
        if not self._client:
            raise IAClientError("Servicio de IA no disponible")

        message = self._client.messages.create(
            model=settings.ai_model,
            max_tokens=2048,
            temperature=0,
            system="Devuelve únicamente JSON válido y no agregues explicaciones.",
            messages=[{"role": "user", "content": prompt}],
        )

        content = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                content.append(text)

        return "".join(content).strip()