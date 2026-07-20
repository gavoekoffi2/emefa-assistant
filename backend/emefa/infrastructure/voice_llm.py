"""OpenAI-compatible proxy so the voice agent can use EMEFA's brain.

ElevenLabs agents support a "Custom LLM" pointing to any OpenAI-compatible
/chat/completions endpoint. This proxy injects EMEFA's profile context into
the conversation and forwards the request (streaming or not) to the same
provider that powers the text brain, so voice and text share business
context without a second provider integration.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


class VoiceLLMProxy:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        context_provider: Callable[[], str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.configured = bool(api_key)
        self.model = model
        self.context_provider = context_provider
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=httpx.Timeout(60.0, connect=10.0),
            transport=transport,
        )

    def build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Force the configured model and prepend EMEFA's profile context."""
        messages = list(payload.get("messages") or [])
        context = ""
        if self.context_provider is not None:
            context = self.context_provider().strip()
        if context:
            messages = [{"role": "system", "content": context}, *messages]
        forwarded = {
            key: value
            for key, value in payload.items()
            if key not in {"model", "messages"}
        }
        return {**forwarded, "model": self.model, "messages": messages}

    async def close(self) -> None:
        await self.client.aclose()
