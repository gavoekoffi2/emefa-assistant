"""LLM-backed fact extraction over the OpenAI-compatible provider.

Deliberately a small, separate client rather than a second use of the chat
brain: extraction runs off the request path, wants a different temperature, a
much smaller token ceiling and its own timeout, and must never be able to
emit a tool call. Sharing the brain would make all four of those accidental.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx

from emefa.domain.memory.ingest import (
    EXTRACTION_PROMPT,
    MAX_TRANSCRIPT_CHARS,
    ExtractedFact,
    parse_extraction,
)

#: Extraction is background work. A slow provider must not keep a connection
#: open behind the user's next turn.
_TIMEOUT = httpx.Timeout(20.0, connect=10.0)

#: Six short facts fit comfortably; more than this is a runaway response.
_MAX_TOKENS = 600


class LLMFactExtractor:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        on_usage: Callable[[int, int], None] | None = None,
    ) -> None:
        self.model = model
        self.on_usage = on_usage
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_TIMEOUT,
            transport=transport,
        )

    async def extract(self, transcript: str) -> list[ExtractedFact]:
        response = await self.client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    # The transcript is fenced as data, and the system prompt
                    # above states it carries no instructions. Extraction can
                    # only ever emit facts — it has no tools — so the worst a
                    # hostile transcript achieves is a false memory the user
                    # can see and delete.
                    {
                        "role": "user",
                        "content": (
                            "Extrait de conversation à analyser :\n"
                            "<<<TRANSCRIPT\n"
                            f"{transcript[:MAX_TRANSCRIPT_CHARS]}\n"
                            "TRANSCRIPT>>>"
                        ),
                    },
                ],
                "temperature": 0.0,
                "max_tokens": _MAX_TOKENS,
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage")
        if self.on_usage is not None and isinstance(usage, dict):
            self.on_usage(
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
            )
        content = payload["choices"][0]["message"].get("content") or ""
        return parse_extraction(content)

    async def close(self) -> None:
        await self.client.aclose()
