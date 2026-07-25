"""Server-only ElevenLabs session broker for EMEFA."""

from __future__ import annotations

import httpx


class RealtimeGateway:
    def __init__(
        self,
        api_key: str | None,
        agent_id: str | None,
        voice_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.agent_id = (agent_id or "").strip()
        self.voice_id = (voice_id or "").strip()
        self.client = httpx.AsyncClient(
            base_url="https://api.elevenlabs.io",
            timeout=httpx.Timeout(30.0, connect=10.0),
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.agent_id)

    @property
    def speech_configured(self) -> bool:
        return bool(self.api_key and self.voice_id)

    async def get_signed_url(self, safety_identifier: str) -> str:
        del safety_identifier  # Device authentication is enforced before this call.
        if not self.configured:
            raise RuntimeError("realtime_not_configured")
        response = await self.client.get(
            "/v1/convai/conversation/get-signed-url",
            headers={"xi-api-key": self.api_key},
            params={"agent_id": self.agent_id},
        )
        response.raise_for_status()
        return str(response.json()["signed_url"])

    async def synthesize(self, text: str) -> bytes:
        if not self.speech_configured:
            raise RuntimeError("speech_not_configured")
        response = await self.client.post(
            f"/v1/text-to-speech/{self.voice_id}",
            headers={"xi-api-key": self.api_key, "accept": "audio/mpeg"},
            params={"output_format": "mp3_44100_128"},
            json={
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "language_code": "fr",
                "voice_settings": {
                    "stability": 0.52,
                    "similarity_boost": 0.86,
                    "style": 0.16,
                    "use_speaker_boost": True,
                },
            },
        )
        response.raise_for_status()
        return response.content

    async def close(self) -> None:
        await self.client.aclose()