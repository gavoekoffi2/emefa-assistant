import httpx
import pytest

from emefa.config import Settings
from emefa.infrastructure.website_profile import WebsiteImport, WebsiteProfileImporter
from emefa.main import create_app


async def public_resolver(_host: str, _port: int) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.asyncio
async def test_importer_rejects_private_network_targets():
    async def private_resolver(_host: str, _port: int) -> list[str]:
        return ["127.0.0.1"]

    importer = WebsiteProfileImporter(resolver=private_resolver)
    with pytest.raises(ValueError, match="site public"):
        await importer.import_site("http://localhost/admin")


@pytest.mark.asyncio
async def test_importer_extracts_bounded_same_origin_pages():
    pages = {
        "https://example.com/": """
            <html><head><title>Horizon Conseil | Accueil</title>
            <meta property="og:site_name" content="Horizon Conseil">
            <meta name="description" content="Conseil logistique pour les PME africaines.">
            </head><body><h1>Accélérez vos opérations</h1>
            <a href="/a-propos">À propos</a><a href="https://other.test/secret">Autre</a>
            <script>ne pas importer</script></body></html>
        """,
        "https://example.com/a-propos": """
            <html><head><title>À propos</title></head>
            <body><p>Notre équipe accompagne les entreprises à Lomé.</p></body></html>
        """,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        html = pages.get(str(request.url))
        if html is None:
            return httpx.Response(404)
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    importer = WebsiteProfileImporter(
        transport=httpx.MockTransport(handler), resolver=public_resolver
    )
    result = await importer.import_site("https://example.com")
    assert result.company_name == "Horizon Conseil"
    assert result.description == "Conseil logistique pour les PME africaines."
    assert result.pages_imported == 2
    assert "Lomé" in result.summary
    assert "ne pas importer" not in result.summary
    assert "other.test" not in result.summary


@pytest.mark.asyncio
async def test_profile_import_endpoint_saves_context(tmp_path):
    app = create_app(
        Settings(
            enrollment_code="CODE-SECRET",
            database_path=tmp_path / "import.db",
            cookie_secure=False,
        )
    )

    class FakeImporter:
        async def import_site(self, url: str) -> WebsiteImport:
            assert url == "https://horizon.example"
            return WebsiteImport(
                url=url,
                company_name="Horizon SARL",
                description="Conseil en logistique.",
                summary="Entreprise basée à Lomé. Services de transport et logistique.",
                pages_imported=3,
            )

    app.state.website_importer = FakeImporter()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthenticated = await client.post(
            "/v1/assistant/business/import", json={"url": "https://horizon.example"}
        )
        assert unauthenticated.status_code == 401
        await client.post(
            "/v1/web/session",
            json={"name": "Navigateur", "enrollment_code": "CODE-SECRET"},
        )
        response = await client.post(
            "/v1/assistant/business/import", json={"url": "https://horizon.example"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["pages_imported"] == 3
        assert body["profile"]["company_name"] == "Horizon SARL"
        assert body["profile"]["website_url"] == "https://horizon.example"
        assert "Lomé" in body["profile"]["website_summary"]
        assert "Horizon SARL" in app.state.profiles.system_context()
        assert "Services de transport" in app.state.profiles.system_context()
