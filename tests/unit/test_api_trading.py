"""Tests for the trading API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine


@pytest.fixture(autouse=True)
def _reset_engines():
    PaperEngine.reset()
    MarketDataProvider.reset()
    yield
    PaperEngine.reset()
    MarketDataProvider.reset()


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_list_pairs_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/trading/pairs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_add_pair(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/trading/pairs", json={"symbol": "BTC/USDT"})
    assert r.status_code == 200
    assert r.json()["symbol"] == "BTC/USDT"


@pytest.mark.asyncio
async def test_add_duplicate_pair(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/trading/pairs", json={"symbol": "BTC/USDT"})
        r = await c.post("/api/v1/trading/pairs", json={"symbol": "BTC/USDT"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_remove_pair(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/trading/pairs", json={"symbol": "BTC/USDT"})
        r = await c.delete("/api/v1/trading/pairs/BTC%2FUSDT")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_available_pairs(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/trading/available-pairs")
    assert r.status_code == 200
    pairs = r.json()
    assert isinstance(pairs, list)
    assert "BTC/USDT" in pairs


@pytest.mark.asyncio
async def test_place_order(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/trading/orders", json={
            "symbol": "BTC/USDT",
            "side": "buy",
            "order_type": "market",
            "quantity": 0.01,
        })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "filled"
    assert data["pair_symbol"] == "BTC/USDT"


@pytest.mark.asyncio
async def test_list_orders(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/trading/orders", json={
            "symbol": "BTC/USDT", "side": "buy", "order_type": "market", "quantity": 0.01,
        })
        r = await c.get("/api/v1/trading/orders")
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_list_positions(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/trading/orders", json={
            "symbol": "BTC/USDT", "side": "buy", "order_type": "market", "quantity": 0.01,
        })
        r = await c.get("/api/v1/trading/positions?status=open")
    assert r.status_code == 200
    positions = r.json()
    assert len(positions) == 1
    assert positions[0]["side"] == "long"


@pytest.mark.asyncio
async def test_close_position(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/trading/orders", json={
            "symbol": "BTC/USDT", "side": "buy", "order_type": "market", "quantity": 0.01,
        })
        positions_r = await c.get("/api/v1/trading/positions?status=open")
        pos_id = positions_r.json()[0]["id"]
        r = await c.post(f"/api/v1/trading/positions/{pos_id}/close")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_portfolio(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/trading/portfolio")
    assert r.status_code == 200
    data = r.json()
    assert data["total_value_usd"] == 10000.0


@pytest.mark.asyncio
async def test_engine_status(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/trading/engine/status")
    assert r.status_code == 200
    data = r.json()
    assert data["running"] is False
