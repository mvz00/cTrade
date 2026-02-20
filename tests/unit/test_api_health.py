"""Tests for API health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app


@pytest.fixture
def test_app():
    """Create a test app without lifespan (no DB needed)."""
    return create_app()


@pytest.mark.asyncio
async def test_health_endpoint(test_app):
    """Health endpoint should return ok status."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "cTrade"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_root_returns_html(test_app):
    """Root route should return HTML landing page, not 404."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "cTrade" in response.text


@pytest.mark.asyncio
async def test_config_trading_mode(test_app):
    """Config endpoint should return current trading mode."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/config/trading-mode")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] in ("paper", "live")


@pytest.mark.asyncio
async def test_dashboard_summary(test_app):
    """Dashboard summary endpoint should return placeholder data."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert "total_value_usd" in data
    assert "trading_mode" in data


@pytest.mark.asyncio
async def test_swagger_docs_available(test_app):
    """Swagger UI should be served at /api/docs."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/docs")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
