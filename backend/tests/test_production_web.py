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


def test_emailed_links_reach_the_app_rather_than_a_404(tmp_path):
    """Account emails point at client-side routes that exist only in the
    bundle. Plain StaticFiles answers 404 for those, which would break every
    verification, reset and invitation link while the home page looked fine."""
    import asyncio

    import httpx

    from emefa.config import Settings
    from emefa.main import create_app

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>EMEFA</title>")
    (dist / "assets").mkdir()
    (dist / "assets" / "index-abc.js").write_text("console.log('emefa')")

    app = create_app(
        Settings(database_path=tmp_path / "spa.db", web_dist_path=dist, cookie_secure=False)
    )

    async def check():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for path in ("/verifier-email", "/nouveau-mot-de-passe", "/rejoindre"):
                response = await client.get(path, params={"token": "abc"})
                assert response.status_code == 200, path
                assert "EMEFA" in response.text, path

            # A real asset is still served as itself.
            assert (await client.get("/assets/index-abc.js")).status_code == 200
            # A mistyped asset still 404s rather than silently returning HTML.
            assert (await client.get("/assets/absent.js")).status_code == 404

    asyncio.run(check())
