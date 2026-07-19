import httpx
import pytest

from emefa.config import Settings
from emefa.main import create_app


@pytest.mark.asyncio
async def test_web_session_cookie_is_secure_and_revocable(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="WEB-CLAUDE",
            database_path=tmp_path / "web-session.db",
            cookie_secure=True,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.test") as client:
        activated = await client.post(
            "/v1/web/session",
            json={"name": "Navigateur de Claude", "enrollment_code": "WEB-CLAUDE"},
        )
        assert activated.status_code == 201
        assert "token" not in activated.json()
        cookie = activated.headers["set-cookie"].lower()
        assert "httponly" in cookie
        assert "secure" in cookie
        assert "samesite=strict" in cookie

        session = await client.get("/v1/web/session")
        assert session.status_code == 200
        assert session.json()["name"] == "Navigateur de Claude"

        agent = await client.post("/v1/agent/runs", json={"message": "Bonjour"})
        assert agent.status_code == 200

        disconnected = await client.delete("/v1/web/session")
        assert disconnected.status_code == 204
        after = await client.get("/v1/web/session")
        assert after.status_code == 401
