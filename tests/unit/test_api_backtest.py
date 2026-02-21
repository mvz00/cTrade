"""Tests for the backtest API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.exchange.market_data import MarketDataProvider


@pytest.fixture(autouse=True)
def _reset():
    MarketDataProvider.reset()
    # Reset the module-level backtest engine results
    from ctrade.api.routers import backtest as backtest_mod
    backtest_mod._engine._results.clear()
    yield
    MarketDataProvider.reset()


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_run_backtest(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/backtest/run", json={
            "symbol": "BTC/USDT",
            "initial_capital": 10000,
            "num_candles": 100,
            "timeframe": "1h",
            "entry_threshold": 0.65,
            "exit_threshold": 0.35,
        })
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["symbol"] == "BTC/USDT"
    assert data["initial_capital"] == 10000
    assert "total_return_pct" in data
    assert "sharpe_ratio" in data
    assert "equity_curve" in data
    assert isinstance(data["trade_log"], list)


@pytest.mark.asyncio
async def test_backtest_results_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/backtest/results")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_backtest_results_after_run(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        await c.post("/api/v1/backtest/run", json={
            "symbol": "BTC/USDT",
            "initial_capital": 10000,
            "num_candles": 100,
            "timeframe": "1h",
            "entry_threshold": 0.65,
            "exit_threshold": 0.35,
        })
        r = await c.get("/api/v1/backtest/results")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
