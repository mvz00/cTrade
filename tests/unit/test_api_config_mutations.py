"""Tests for config PUT endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_put_trading_mode(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/trading-mode",
            json={"mode": "live"},
        )
    assert response.status_code == 200
    assert response.json()["mode"] == "live"


@pytest.mark.asyncio
async def test_put_trading_mode_persists(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.put("/api/v1/config/trading-mode", json={"mode": "live"})
        response = await client.get("/api/v1/config/trading-mode")
    assert response.json()["mode"] == "live"


@pytest.mark.asyncio
async def test_put_trading_mode_invalid(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/trading-mode",
            json={"mode": "invalid"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_put_strategy_config(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/strategy",
            json={
                "technical_weight": 0.60,
                "sentiment_weight": 0.25,
                "onchain_weight": 0.15,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["technical_weight"] == 0.60
    assert data["sentiment_weight"] == 0.25
    assert data["onchain_weight"] == 0.15


@pytest.mark.asyncio
async def test_put_strategy_invalid_weights(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/strategy",
            json={"technical_weight": 0.90},
        )
    assert response.status_code == 422
    assert "sum to 1.0" in response.json()["detail"]


@pytest.mark.asyncio
async def test_put_strategy_partial_non_weight(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/strategy",
            json={"entry_confidence_threshold": 0.85},
        )
    assert response.status_code == 200
    assert response.json()["entry_confidence_threshold"] == 0.85


@pytest.mark.asyncio
async def test_put_risk_config(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/risk",
            json={
                "max_position_pct": 0.20,
                "default_stop_loss_pct": 0.05,
            },
        )
    assert response.status_code == 200
    data = response.json()
    assert data["max_position_pct"] == 0.20
    assert data["default_stop_loss_pct"] == 0.05


@pytest.mark.asyncio
async def test_put_risk_out_of_range(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            "/api/v1/config/risk",
            json={"max_position_pct": 2.0},
        )
    assert response.status_code == 422
