"""Server-only ElevenLabs session broker for EMEFA."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("emefa.voice")

#: ElevenLabs' own failure names, mapped to the reasons EMEFA reports.
#:
#: The provider is specific about *why* it refused — the voice does not exist,
#: the quota is spent, the key is not entitled to that voice. Collapsing all of
#: that into one "rejected" code is what made this failure undiagnosable: the
#: operator saw a 502 and had no way to tell a typo in a voice id from an
#: exhausted plan.
_PROVIDER_REASONS: dict[str, str] = {
    "voice_not_found": "speech_voice_not_found",
    "voice_does_not_exist": "speech_voice_not_found",
    "invalid_api_key": "speech_key_invalid",
    "needs_authorization": "speech_key_invalid",
    "quota_exceeded": "speech_quota_exceeded",
    "too_many_concurrent_requests": "speech_rate_limited",
    "detected_unusual_activity": "speech_account_blocked",
    "voice_limit_reached": "speech_voice_limit_reached",
    "model_not_found": "speech_model_unavailable",
    "invalid_output_format": "speech_format_unsupported",
    "language_not_supported": "speech_language_unsupported",
}

#: Fallback when the body carries no recognisable name, keyed on HTTP status.
#:
#: 400 matters as much as the rest: the provider uses it for most refusals,
#: and leaving it out sent exactly the failures we were trying to diagnose
#: back to the generic "rejected" code.
_STATUS_REASONS: dict[int, str] = {
    400: "speech_request_invalid",
    401: "speech_key_invalid",
    403: "speech_key_not_entitled",
    404: "speech_voice_not_found",
    413: "speech_text_too_long",
    422: "speech_request_invalid",
    429: "speech_rate_limited",
}


def _reason_for(status_code: int) -> str:
    """A named reason for any status, so nothing lands on the catch-all."""
    if status_code in _STATUS_REASONS:
        return _STATUS_REASONS[status_code]
    # The provider's own fault, and it usually passes — worth retrying rather
    # than tearing down the cloned voice.
    if status_code >= 500:
        return "speech_provider_unavailable"
    return "speech_provider_rejected_request"


class SpeechProviderError(RuntimeError):
    """The speech provider refused, with the reason it gave.

    Carries a stable ``reason`` the API and the interface can act on, plus the
    provider's own message for the server log — never for the client, since a
    provider message can quote account details.
    """

    def __init__(self, reason: str, status_code: int, provider_message: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code
        self.provider_message = provider_message


def _classify(response: httpx.Response) -> SpeechProviderError:
    """Turn a provider refusal into a reason EMEFA can explain."""
    name = ""
    message = ""
    try:
        body: Any = response.json()
    except ValueError:
        body = None

    detail = body.get("detail") if isinstance(body, dict) else None
    if isinstance(detail, dict):
        name = str(detail.get("status") or "")
        message = str(detail.get("message") or "")
    elif isinstance(detail, list) and detail:
        # FastAPI-style validation errors from the provider.
        first = detail[0]
        if isinstance(first, dict):
            name = "request_invalid"
            message = str(first.get("msg") or "")
    elif isinstance(detail, str):
        message = detail

    reason = _PROVIDER_REASONS.get(name) or _reason_for(response.status_code)
    return SpeechProviderError(reason, response.status_code, message or name)


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
            params={
                "output_format": "mp3_44100_128",
                "optimize_streaming_latency": "3",
            },
            json={
                "text": text,
                "model_id": "eleven_turbo_v2_5",
                "language_code": "fr",
                "voice_settings": {
                    "stability": 0.52,
                    "similarity_boost": 0.86,
                    "style": 0.16,
                    "use_speaker_boost": True,
                },
            },
        )
        if response.is_error:
            error = _classify(response)
            # The one place the real cause is recorded. The voice id is safe to
            # log — it identifies which voice was asked for, and is the single
            # most useful fact when a synthesis starts failing. The API key is
            # never logged.
            logger.warning(
                "speech provider refused the request",
                extra={
                    "reason": error.reason,
                    "provider_status": error.status_code,
                    "provider_message": error.provider_message,
                    "voice_id": self.voice_id,
                },
            )
            raise error
        return response.content

    async def list_voices(self, limit: int = 25) -> list[dict[str, str]]:
        """The voices this key can actually use.

        When a synthesis fails on a voice id, the useful next question is
        "then which ids do I have?" — answering it from the provider beats
        asking someone to go and read a dashboard.
        """
        if not self.api_key:
            raise RuntimeError("speech_not_configured")
        response = await self.client.get("/v1/voices", headers={"xi-api-key": self.api_key})
        if response.is_error:
            raise _classify(response)
        payload = response.json()
        voices = payload.get("voices", []) if isinstance(payload, dict) else []
        return [
            {
                "voice_id": str(voice.get("voice_id", "")),
                "name": str(voice.get("name", "")),
                "category": str(voice.get("category", "")),
            }
            for voice in voices[:limit]
            if isinstance(voice, dict)
        ]

    async def close(self) -> None:
        await self.client.aclose()
