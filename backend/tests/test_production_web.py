import httpx
import pytest

from emefa.config import Settings
from emefa.main import create_app


@pytest.mark.asyncio
async def test_production_app_serves_web_shell_with_security_headers(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>EMEFA</title>", encoding="utf-8")
    app = create_app(
        Settings(
            enrollment_code="PRIVATE",
            database_path=tmp_path / "app.db",
            web_dist_path=dist,
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://emefa.example") as client:
        page = await client.get("/")
        private_api = await client.get("/v1/web/session")

    assert page.status_code == 200
    assert "EMEFA" in page.text
    assert page.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert "connect-src 'self' https://api.elevenlabs.io wss://api.elevenlabs.io" in page.headers["content-security-policy"]
    assert private_api.status_code == 401
    assert private_api.headers["cache-control"] == "no-store"
