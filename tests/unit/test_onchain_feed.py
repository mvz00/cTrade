"""Tests for the on-chain data feed (mocked HTTP)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from ctrade.feeds.onchain import OnChainFeed


@pytest.fixture(autouse=True)
def reset_feed():
    """Reset the singleton between tests."""
    OnChainFeed.reset()
    yield
    OnChainFeed.reset()


class TestOnChainFeedSingleton:
    def test_get_instance(self):
        a = OnChainFeed.get_instance()
        b = OnChainFeed.get_instance()
        assert a is b

    def test_reset(self):
        a = OnChainFeed.get_instance()
        OnChainFeed.reset()
        b = OnChainFeed.get_instance()
        assert a is not b

    def test_initial_state(self):
        feed = OnChainFeed.get_instance()
        assert feed.name == "onchain"
        assert not feed.is_enabled


class TestOnChainFeedQueries:
    def test_get_score_when_disabled(self):
        feed = OnChainFeed.get_instance()
        assert feed.get_onchain_score("BTC/USDT") is None

    def test_get_all_scores_empty(self):
        feed = OnChainFeed.get_instance()
        feed._enabled = True
        assert feed.get_all_scores() == {}

    def test_get_metrics_empty(self):
        feed = OnChainFeed.get_instance()
        assert feed.get_metrics("BTC") == []

    def test_get_status(self):
        feed = OnChainFeed.get_instance()
        status = feed.get_status()
        assert "enabled" in status
        assert "healthy" in status
        assert "metrics_count" in status
        assert "assets_tracked" in status


class TestOnChainFeedParsing:
    """Test HTTP response parsing with mocked APIs."""

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_blockchain_info(self):
        respx.get("https://api.blockchain.info/stats").mock(
            return_value=Response(200, json={
                "hash_rate": 600000000.0,
                "n_tx": 350000,
                "market_price_usd": 50000.0,
                "totalbc": 1900000000000000,
            })
        )
        respx.get("https://api.blockchain.info/mempool").mock(
            return_value=Response(200, json={
                "count": 5000,
            })
        )
        feed = OnChainFeed.get_instance()
        metrics = await feed._fetch_blockchain_info()
        assert len(metrics) >= 3  # hash_rate, tx_count, market_cap
        names = {m.metric_name for m in metrics}
        assert "hash_rate" in names
        assert "tx_count_24h" in names
        assert all(m.asset == "BTC" for m in metrics)
        assert all(m.source == "blockchain.info" for m in metrics)

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_coingecko_market(self):
        respx.get("https://api.coingecko.com/api/v3/coins/markets").mock(
            return_value=Response(200, json=[
                {
                    "id": "bitcoin",
                    "symbol": "btc",
                    "total_volume": 30000000000,
                    "market_cap": 1000000000000,
                    "total_supply": 21000000,
                    "circulating_supply": 19500000,
                },
                {
                    "id": "ethereum",
                    "symbol": "eth",
                    "total_volume": 15000000000,
                    "market_cap": 400000000000,
                    "total_supply": None,
                    "circulating_supply": 120000000,
                },
            ])
        )
        feed = OnChainFeed.get_instance()
        metrics = await feed._fetch_coingecko_market()
        # BTC should have volume, market_cap, and circulating_supply_pct
        btc_metrics = [m for m in metrics if m.asset == "BTC"]
        assert len(btc_metrics) >= 2
        btc_names = {m.metric_name for m in btc_metrics}
        assert "volume_24h" in btc_names
        assert "market_cap" in btc_names
        # ETH should not have supply pct (total_supply is None)
        eth_metrics = [m for m in metrics if m.asset == "ETH"]
        assert len(eth_metrics) >= 1

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_blockchain_info_error(self):
        respx.get("https://api.blockchain.info/stats").mock(
            return_value=Response(500, json={"error": "server error"})
        )
        feed = OnChainFeed.get_instance()
        with pytest.raises(Exception):
            await feed._fetch_blockchain_info()

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_all_sources_stores_metrics(self):
        respx.get("https://api.blockchain.info/stats").mock(
            return_value=Response(200, json={
                "hash_rate": 600000000.0,
                "n_tx": 350000,
                "market_price_usd": 50000.0,
                "totalbc": 1900000000000000,
            })
        )
        respx.get("https://api.blockchain.info/mempool").mock(
            return_value=Response(200, json={"count": 5000})
        )
        respx.get("https://api.coingecko.com/api/v3/coins/markets").mock(
            return_value=Response(200, json=[
                {
                    "id": "bitcoin",
                    "symbol": "btc",
                    "total_volume": 30e9,
                    "market_cap": 1e12,
                    "total_supply": 21e6,
                    "circulating_supply": 19.5e6,
                },
            ])
        )
        feed = OnChainFeed.get_instance()
        await feed._fetch_all_sources()
        assert feed._healthy is True
        assert "BTC" in feed._metrics
        assert len(feed._metrics["BTC"]) > 0
