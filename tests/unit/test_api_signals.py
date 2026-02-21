"""Tests for the signals API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.strategy.signal_manager import SignalManager


@pytest.fixture(autouse=True)
def _reset():
    SignalManager.reset()
    yield
    SignalManager.reset()


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_list_signals_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/signals/")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_latest_signal_none(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/signals/BTC%2FUSDT/latest")
    assert r.status_code == 200
    assert r.json() is None


@pytest.mark.asyncio
async def test_indicators_none(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/signals/BTC%2FUSDT/indicators")
    assert r.status_code == 200
    assert r.json() is None
