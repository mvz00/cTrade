"""Tests for on-chain API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.core.models import OnChainMetric
from ctrade.feeds.onchain import OnChainFeed


@pytest.fixture(autouse=True)
def reset_feeds():
    OnChainFeed.reset()
    yield
    OnChainFeed.reset()


def _seed_feed(asset: str = "BTC", n_metrics: int = 3) -> OnChainFeed:
    """Create and seed an on-chain feed with test data."""
    feed = OnChainFeed.get_instance()
    feed._enabled = True
    feed._healthy = True
    metric_names = ["hash_rate", "tx_count_24h", "volume_24h", "market_cap", "mempool_size"]
    for i in range(n_metrics):
        m = OnChainMetric(
            asset=asset,
            metric_name=metric_names[i % len(metric_names)],
            metric_value=Decimal(str(100000 * (i + 1))),
            source="test",
        )
        feed._metrics.setdefault(asset, []).append(m)
    return feed


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.anyio
async def test_get_all_scores(client):
    _seed_feed("BTC")
    _seed_feed("ETH")
    resp = await client.get("/api/v1/onchain/scores")
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert "assets_tracked" in data
    assert data["assets_tracked"] >= 2


@pytest.mark.anyio
async def test_get_score(client):
    _seed_feed("BTC")
    resp = await client.get("/api/v1/onchain/BTC/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC"
    assert 0.0 <= data["score"] <= 1.0
    assert data["signal"] in ("bullish", "bearish", "neutral")


@pytest.mark.anyio
async def test_get_metrics(client):
    _seed_feed("BTC", n_metrics=5)
    resp = await client.get("/api/v1/onchain/BTC/metrics?limit=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "BTC"
    assert len(data["metrics"]) <= 3
    for m in data["metrics"]:
        assert "metric_name" in m
        assert "metric_value" in m
        assert "source" in m


@pytest.mark.anyio
async def test_get_status(client):
    feed = OnChainFeed.get_instance()
    feed._enabled = True
    resp = await client.get("/api/v1/onchain/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert "metrics_count" in data


@pytest.mark.anyio
async def test_get_score_no_data(client):
    """When no data, should return neutral."""
    feed = OnChainFeed.get_instance()
    feed._enabled = True
    resp = await client.get("/api/v1/onchain/XYZ/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["score"] == 0.5
    assert data["signal"] == "neutral"
