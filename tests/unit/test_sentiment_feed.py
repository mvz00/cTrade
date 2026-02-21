"""Tests for the sentiment feed (mocked HTTP)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from ctrade.feeds.sentiment import SentimentFeed, ASSET_ALIASES


@pytest.fixture(autouse=True)
def reset_feed():
    """Reset the singleton between tests."""
    SentimentFeed.reset()
    yield
    SentimentFeed.reset()


class TestAssetExtraction:
    """Test the static _extract_assets method."""

    def test_bitcoin_by_name(self):
        assets = SentimentFeed._extract_assets("Bitcoin hits new all-time high")
        assert "BTC" in assets

    def test_ethereum_by_symbol(self):
        assets = SentimentFeed._extract_assets("ETH is pumping today")
        assert "ETH" in assets

    def test_multiple_assets(self):
        assets = SentimentFeed._extract_assets("Bitcoin and Ethereum are surging, Solana follows")
        assert "BTC" in assets
        assert "ETH" in assets
        assert "SOL" in assets

    def test_dollar_symbol(self):
        assets = SentimentFeed._extract_assets("$BTC breaking out!")
        assert "BTC" in assets

    def test_pair_format(self):
        assets = SentimentFeed._extract_assets("BTC/USDT is up 5%")
        assert "BTC" in assets

    def test_no_match(self):
        assets = SentimentFeed._extract_assets("The weather is nice today")
        assert len(assets) == 0

    def test_case_insensitive_names(self):
        assets = SentimentFeed._extract_assets("BITCOIN and ethereum")
        # Name matching is case-insensitive
        assert "BTC" in assets
        assert "ETH" in assets


class TestSentimentFeedSingleton:
    def test_get_instance(self):
        a = SentimentFeed.get_instance()
        b = SentimentFeed.get_instance()
        assert a is b

    def test_reset(self):
        a = SentimentFeed.get_instance()
        SentimentFeed.reset()
        b = SentimentFeed.get_instance()
        assert a is not b

    def test_initial_state(self):
        feed = SentimentFeed.get_instance()
        assert feed.name == "sentiment"
        assert not feed.is_enabled


class TestSentimentFeedQueries:
    def test_get_score_when_disabled(self):
        feed = SentimentFeed.get_instance()
        assert feed.get_sentiment_score("BTC/USDT") is None

    def test_get_all_scores_empty(self):
        feed = SentimentFeed.get_instance()
        feed._enabled = True
        assert feed.get_all_scores() == {}

    def test_get_recent_data_empty(self):
        feed = SentimentFeed.get_instance()
        assert feed.get_recent_data("BTC") == []

    def test_get_status(self):
        feed = SentimentFeed.get_instance()
        status = feed.get_status()
        assert "enabled" in status
        assert "healthy" in status
        assert "data_points" in status
        assert "assets_tracked" in status


class TestSentimentFeedParsing:
    """Test HTTP response parsing with mocked APIs."""

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_cryptocompare(self):
        respx.get("https://min-api.cryptocompare.com/data/v2/news/").mock(
            return_value=Response(200, json={
                "Data": [
                    {
                        "id": "12345",
                        "title": "Bitcoin surges past $100k",
                        "body": "BTC has hit a new milestone",
                        "categories": "BTC|Bitcoin",
                    },
                ]
            })
        )
        feed = SentimentFeed.get_instance()
        items = await feed._fetch_cryptocompare()
        assert len(items) >= 1
        assert items[0].source == "cryptocompare"
        assert "BTC" in items[0].assets

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_coingecko_trending(self):
        respx.get("https://api.coingecko.com/api/v3/search/trending").mock(
            return_value=Response(200, json={
                "coins": [
                    {"item": {"name": "Bitcoin", "symbol": "BTC", "score": 0}},
                    {"item": {"name": "Ethereum", "symbol": "ETH", "score": 1}},
                ]
            })
        )
        feed = SentimentFeed.get_instance()
        items = await feed._fetch_coingecko_trending()
        assert len(items) == 2
        assert items[0].source == "coingecko"
        assert "BTC" in items[0].assets

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_reddit(self):
        respx.get("https://www.reddit.com/r/cryptocurrency/hot.json").mock(
            return_value=Response(200, json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": "abc123",
                                "title": "Bitcoin is looking bullish today!",
                                "selftext": "",
                            }
                        }
                    ]
                }
            })
        )
        feed = SentimentFeed.get_instance()
        items = await feed._fetch_reddit()
        assert len(items) >= 1
        assert items[0].source == "reddit"
        assert "BTC" in items[0].assets

    @respx.mock
    @pytest.mark.anyio
    async def test_fetch_handles_error(self):
        respx.get("https://min-api.cryptocompare.com/data/v2/news/").mock(
            return_value=Response(500, json={"error": "server error"})
        )
        feed = SentimentFeed.get_instance()
        with pytest.raises(Exception):
            await feed._fetch_cryptocompare()
