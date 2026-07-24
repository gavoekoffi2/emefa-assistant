"""Streaming OpenAI-compatible proxy for ElevenLabs Custom LLM.

The proxy preserves ElevenLabs client-tool schemas, injects EMEFA's bounded
profile/memory context, and relays upstream SSE bytes as they arrive. Actions
remain governed: ElevenLabs invokes the browser-side ``emefa_execute`` client
tool, which calls the authenticated EMEFA agent API and approval loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx


# Keep the provider request intentionally bounded. ElevenLabs may add
# transport-specific fields that an OpenAI-compatible provider does not know.
_FORWARDED_FIELDS = {
    "frequency_penalty",
    "max_completion_tokens",
    "max_tokens",
    "parallel_tool_calls",
    "presence_penalty",
    "response_format",
    "seed",
    "stop",
    "stream",
    "stream_options",
    "temperature",
    "tool_choice",
    "tools",
    "top_p",
}


class VoiceLLMProxy:
    def __init__(
        self,
        api_key: str | None,
        model: str,
        base_url: str,
        context_provider: Callable[[], str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.configured = bool((api_key or "").strip())
        self.model = model
        self.context_provider = context_provider
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            timeout=httpx.Timeout(60.0, connect=10.0),
            transport=transport,
        )

    def build_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        messages = list(payload.get("messages") or [])
        context = ""
        if self.context_provider is not None:
            context = self.context_provider().strip()
        if context:
            messages = [{"role": "system", "content": context}, *messages]
        forwarded = {
            key: value for key, value in payload.items() if key in _FORWARDED_FIELDS
        }
        return {**forwarded, "model": self.model, "messages": messages}

    async def close(self) -> None:
        await self.client.aclose()
