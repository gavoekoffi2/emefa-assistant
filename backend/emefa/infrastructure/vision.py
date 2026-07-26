"""OpenRouter-backed analysis for private user-uploaded images."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx


class OpenRouterVisionAnalyzer:
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(60.0, connect=10.0),
            transport=transport,
        )

    async def analyze(self, image_path: Path, content_type: str, question: str) -> str:
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        response = await self.client.post(
            "chat/completions",
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": question},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{content_type};base64,{encoded}"
                                },
                            },
                        ],
                    }
                ],
            },
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "\n".join(
                str(part.get("text", "")).strip()
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
            if text:
                return text
        raise ValueError("vision_provider_empty_response")

    async def close(self) -> None:
        await self.client.aclose()
