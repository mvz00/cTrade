"""Tests for sentiment API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.core.enums import SentimentLabel
from ctrade.core.models import SentimentDataPoint
from ctrade.feeds.sentiment import SentimentFeed


@pytest.fixture(autouse=True)
def reset_feeds():
    SentimentFeed.reset()
    yield
    SentimentFeed.reset()


def _seed_feed(asset: str = "BTC", n: int = 5) -> SentimentFeed:
    """Create and seed a sentiment feed with test data."""
    feed = SentimentFeed.get_instance()
    feed._enabled = True
    feed._healthy = True
    for i in range(n):
        dp = SentimentDataPoint(
            asset=asset,
            source="cryptocompare" if i % 2 == 0 else "reddit",
            source_id=f"test_{i}",
            raw_text=f"Test sentiment text {i}",
            label=SentimentLabel.POSITIVE if i % 2 == 0 else SentimentLabel.NEUTRAL,
            score=0.7 if i % 2 == 0 else 0.5,
            model_used="keyword-fallback",
        )
        feed._data_points.setdefault(asset, []).append(dp)
    return feed


@pytest.fixture
def app(monkeypatch):
    from ctrade.settings import get_settings
    get_settings.cache_clear()
    monkeypatch.setenv("CTRADE_AUTH__ENABLED", "false")
    _app = create_app()
    yield _app
    get_settings.cache_clear()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_get_all_scores(client):
    _seed_feed("BTC")
    _seed_feed("ETH")
    resp = await client.get("/api/v1/sentiment/scores")
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert "assets_tracked" in data
    assert data["assets_tracked"] >= 2


@pytest.mark.anyio
async def test_get_score(client):
    _seed_feed("BTC")
    resp = await client.get("/api/v1/sentiment/BTC/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC"
    assert 0.0 <= data["score"] <= 1.0
    assert data["signal"] in ("bullish", "bearish", "neutral")


@pytest.mark.anyio
async def test_get_timeline(client):
    _seed_feed("BTC", n=10)
    resp = await client.get("/api/v1/sentiment/BTC/timeline?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC"
    assert len(data["data_points"]) <= 5


@pytest.mark.anyio
async def test_get_factors(client):
    _seed_feed("BTC")
    resp = await client.get("/api/v1/sentiment/BTC/factors")
    assert resp.status_code == 200
    data = resp.json()
    assert "score" in data
    assert "signal" in data
    assert "data_points" in data


@pytest.mark.anyio
async def test_get_status(client):
    feed = SentimentFeed.get_instance()
    feed._enabled = True
    resp = await client.get("/api/v1/sentiment/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert "classifier_model" in data


@pytest.mark.anyio
async def test_get_score_no_data(client):
    """When no data, should return neutral."""
    feed = SentimentFeed.get_instance()
    feed._enabled = True
    resp = await client.get("/api/v1/sentiment/XYZ/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 0.5
    assert data["signal"] == "neutral"
