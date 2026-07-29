"""Short-lived LiveKit room tickets for EMEFA's private voice pilot."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants


class LiveKitBroker:
    """Mint scoped room tokens without exposing LiveKit server credentials."""

    def __init__(
        self,
        *,
        url: str | None,
        api_key: str | None,
        api_secret: str | None,
        agent_name: str = "emefa",
        token_ttl_seconds: int = 300,
    ) -> None:
        self._url = (url or "").strip()
        self._api_key = (api_key or "").strip()
        self._api_secret = (api_secret or "").strip()
        self._agent_name = agent_name.strip() or "emefa"
        self._token_ttl_seconds = min(900, max(60, token_ttl_seconds))

    @property
    def configured(self) -> bool:
        return bool(self._url and self._api_key and self._api_secret)

    async def create_session(self, device_id: str) -> dict[str, str]:
        if not self.configured:
            raise RuntimeError("livekit_not_configured")

        room = f"emefa-{uuid.uuid4().hex[:16]}"
        identity = f"device-{hashlib.sha256(device_id.encode('utf-8')).hexdigest()[:20]}"
        room_config = RoomConfiguration(
            agents=[RoomAgentDispatch(agent_name=self._agent_name)],
        )
        token = (
            AccessToken(api_key=self._api_key, api_secret=self._api_secret)
            .with_identity(identity)
            .with_name("EMEFA private device")
            .with_ttl(timedelta(seconds=self._token_ttl_seconds))
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .with_room_config(room_config)
            .to_jwt()
        )
        return {"token": token, "url": self._url, "room": room}

    async def close(self) -> None:
        """Keep a uniform gateway lifecycle; token minting owns no socket."""
