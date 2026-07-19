import httpx
import pytest

from emefa.main import app


@pytest.mark.asyncio
async def test_health_returns_minimal_public_status():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "emefa-backend",
        "version": "0.1.0",
    }
