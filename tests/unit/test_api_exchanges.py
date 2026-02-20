"""Tests for exchange management endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.security.vault import Vault


@pytest.fixture
def test_app(monkeypatch):
    """Create a test app with a valid encryption key set."""
    key = Vault.generate_key()
    monkeypatch.setenv("CTRADE_ENCRYPTION_KEY", key)
    # Re-create settings with the encryption key
    from ctrade.settings import get_settings
    get_settings.cache_clear()
    from ctrade.core.config_store import RuntimeConfigStore
    RuntimeConfigStore.initialize(get_settings())
    app = create_app()
    yield app
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_list_available_exchanges(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/exchanges/available")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    names = [ex["name"] for ex in data]
    assert "binance" in names
    assert "kraken" in names


@pytest.mark.asyncio
async def test_list_exchanges_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/exchanges/")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_add_exchange(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/exchanges/",
            json={
                "name": "binance",
                "api_key": "test-api-key",
                "api_secret": "test-api-secret",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "binance"
    assert data["exchange_type"] == "spot"
    assert data["is_active"] is True
    assert "id" in data
    # Credentials must NOT be in response
    assert "api_key" not in data
    assert "api_secret" not in data


@pytest.mark.asyncio
async def test_add_unknown_exchange(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/exchanges/",
            json={
                "name": "fake_exchange",
                "api_key": "k",
                "api_secret": "s",
            },
        )
    assert response.status_code == 422
    assert "Unknown exchange" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_exchange(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Add first
        add_resp = await client.post(
            "/api/v1/exchanges/",
            json={"name": "binance", "api_key": "k", "api_secret": "s"},
        )
        exchange_id = add_resp.json()["id"]
        # Delete
        del_resp = await client.delete(f"/api/v1/exchanges/{exchange_id}")
        assert del_resp.status_code == 204
        # Verify gone
        list_resp = await client.get("/api/v1/exchanges/")
        assert list_resp.json() == []


@pytest.mark.asyncio
async def test_delete_nonexistent_exchange(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete("/api/v1/exchanges/nonexistent-id")
    assert response.status_code == 404
