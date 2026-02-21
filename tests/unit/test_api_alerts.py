"""Tests for the alerts API endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.notifications.alert_manager import AlertManager


@pytest.fixture(autouse=True)
def _reset():
    AlertManager.reset()
    yield
    AlertManager.reset()


@pytest.fixture
def test_app():
    return create_app()


@pytest.mark.asyncio
async def test_list_alerts_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/alerts/")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_alert(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/v1/alerts/", json={
            "alert_type": "price_above",
            "symbol": "BTC/USDT",
            "value": 70000.0,
            "message": "BTC mooning!",
        })
    assert r.status_code == 201
    data = r.json()
    assert data["alert_type"] == "price_above"
    assert data["symbol"] == "BTC/USDT"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_delete_alert(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_r = await c.post("/api/v1/alerts/", json={
            "alert_type": "price_above",
            "symbol": "BTC/USDT",
            "value": 70000.0,
        })
        alert_id = create_r.json()["id"]
        r = await c.delete(f"/api/v1/alerts/{alert_id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_toggle_alert(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        create_r = await c.post("/api/v1/alerts/", json={
            "alert_type": "price_above",
            "symbol": "BTC/USDT",
            "value": 70000.0,
        })
        alert_id = create_r.json()["id"]
        r = await c.put(f"/api/v1/alerts/{alert_id}/toggle")
    assert r.status_code == 200
    assert r.json()["is_active"] is False


@pytest.mark.asyncio
async def test_alert_history_empty(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/alerts/history")
    assert r.status_code == 200
    assert r.json() == []
