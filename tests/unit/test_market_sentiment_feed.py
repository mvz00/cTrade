"""Tests for the market sentiment feed (Fear & Greed, L/S ratio, taker volume)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest
import respx
from httpx import Response

from ctrade.feeds.market_sentiment import (
    FearGreedData,
    LiquidationData,
    LongShortData,
    MarketSentimentFeed,
    _BINANCE_LONG_SHORT_URL,
    _BINANCE_TAKER_VOLUME_URL,
    _BINANCE_TOP_TRADER_URL,
    _FEAR_GREED_URL,
)


@pytest.fixture(autouse=True)
def reset_feed():
    """Reset the singleton between tests."""
    MarketSentimentFeed.reset()
    yield
    MarketSentimentFeed.reset()


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestMarketSentimentSingleton:
    def test_get_instance(self):
        a = MarketSentimentFeed.get_instance()
        b = MarketSentimentFeed.get_instance()
        assert a is b

    def test_reset(self):
        a = MarketSentimentFeed.get_instance()
        MarketSentimentFeed.reset()
        b = MarketSentimentFeed.get_instance()
        assert a is not b

    def test_initial_state(self):
        feed = MarketSentimentFeed.get_instance()
        assert feed.name == "market_sentiment"
        assert not feed.is_enabled

    def test_default_fear_greed_neutral(self):
        feed = MarketSentimentFeed.get_instance()
        assert feed._fear_greed.value == 50
        assert feed._fear_greed.classification == "Neutral"


# ---------------------------------------------------------------------------
# Score queries when disabled / empty
# ---------------------------------------------------------------------------

class TestMarketSentimentQueries:
    def test_get_score_when_disabled(self):
        feed = MarketSentimentFeed.get_instance()
        assert feed.get_market_sentiment_score("BTC/USDT") is None

    def test_get_score_when_enabled_no_data(self):
        """Enabled with default F&G only → returns a score (F&G always available)."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        score = feed.get_market_sentiment_score("BTC/USDT")
        # Default F&G = 50 → neutral, score should be ~0.5
        assert score is not None
        assert abs(score - 0.5) < 0.05

    def test_get_fear_greed_default(self):
        feed = MarketSentimentFeed.get_instance()
        fg = feed.get_fear_greed()
        assert fg["value"] == 50
        assert fg["classification"] == "Neutral"
        assert "score" in fg
        assert "timestamp" in fg

    def test_get_long_short_ratio_no_data(self):
        feed = MarketSentimentFeed.get_instance()
        assert feed.get_long_short_ratio("BTC/USDT") is None

    def test_get_liquidation_data_no_data(self):
        feed = MarketSentimentFeed.get_instance()
        assert feed.get_liquidation_data("BTC/USDT") is None

    def test_get_all_scores_empty(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        # No L/S or taker data, but F&G is always available
        scores = feed.get_all_scores()
        # Should have scores for tracked symbols based on F&G alone
        assert isinstance(scores, dict)

    def test_get_status(self):
        feed = MarketSentimentFeed.get_instance()
        status = feed.get_status()
        assert "enabled" in status
        assert "healthy" in status
        assert "fear_greed_value" in status
        assert "fear_greed_class" in status
        assert "long_short_symbols" in status
        assert "liquidation_symbols" in status
        assert "poll_interval" in status

    def test_get_contributing_factors_disabled(self):
        feed = MarketSentimentFeed.get_instance()
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors == {"available": False}


# ---------------------------------------------------------------------------
# Fear & Greed scoring (contrarian: fear = bullish, greed = bearish)
# ---------------------------------------------------------------------------

class TestFearGreedScoring:
    """Fear & Greed is contrarian: extreme fear → buy opportunity → score > 0.5."""

    def test_neutral_50_gives_near_half(self):
        score = MarketSentimentFeed._fear_greed_to_score(50)
        assert abs(score - 0.5) < 0.01

    def test_extreme_fear_is_bullish(self):
        """F&G = 5 (extreme fear) → strong buy → score >> 0.5."""
        score = MarketSentimentFeed._fear_greed_to_score(5)
        assert score > 0.8

    def test_extreme_greed_is_bearish(self):
        """F&G = 95 (extreme greed) → caution → score << 0.5."""
        score = MarketSentimentFeed._fear_greed_to_score(95)
        assert score < 0.2

    def test_mild_fear_slightly_bullish(self):
        """F&G = 35 (fear) → slightly bullish → score > 0.5."""
        score = MarketSentimentFeed._fear_greed_to_score(35)
        assert score > 0.5

    def test_mild_greed_slightly_bearish(self):
        """F&G = 65 (greed) → slightly bearish → score < 0.5."""
        score = MarketSentimentFeed._fear_greed_to_score(65)
        assert score < 0.5

    def test_score_bounded_0_1(self):
        for value in [0, 10, 25, 50, 75, 90, 100]:
            score = MarketSentimentFeed._fear_greed_to_score(value)
            assert 0.0 <= score <= 1.0

    def test_monotonically_decreasing(self):
        """Higher F&G (greed) → lower score (bearish)."""
        scores = [MarketSentimentFeed._fear_greed_to_score(v) for v in range(0, 101, 10)]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]


# ---------------------------------------------------------------------------
# Long/Short ratio scoring (contrarian: crowded longs = bearish)
# ---------------------------------------------------------------------------

class TestLongShortScoring:
    """L/S ratio is contrarian: overcrowded longs → price drops → score < 0.5."""

    def test_balanced_is_neutral(self):
        score = MarketSentimentFeed._long_short_to_score(0.5)
        assert abs(score - 0.5) < 0.001

    def test_overcrowded_longs_is_bearish(self):
        """70% long → contrarian bearish → score < 0.5."""
        score = MarketSentimentFeed._long_short_to_score(0.70)
        assert score < 0.4

    def test_overcrowded_shorts_is_bullish(self):
        """30% long (70% short) → contrarian bullish → score > 0.5."""
        score = MarketSentimentFeed._long_short_to_score(0.30)
        assert score > 0.6

    def test_extreme_longs_very_bearish(self):
        """80%+ long → very bearish → score well below 0.5."""
        score = MarketSentimentFeed._long_short_to_score(0.80)
        assert score < 0.25

    def test_extreme_shorts_very_bullish(self):
        """20% long (80% short) → very bullish → score well above 0.5."""
        score = MarketSentimentFeed._long_short_to_score(0.20)
        assert score > 0.75

    def test_score_bounded_0_1(self):
        for pct in [0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0]:
            score = MarketSentimentFeed._long_short_to_score(pct)
            assert 0.0 <= score <= 1.0

    def test_monotonically_decreasing(self):
        """Higher long% → lower score (contrarian)."""
        scores = [MarketSentimentFeed._long_short_to_score(p / 10) for p in range(0, 11)]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]


# ---------------------------------------------------------------------------
# Taker volume scoring (momentum: more buys = bullish)
# ---------------------------------------------------------------------------

class TestTakerVolumeScoring:
    """Taker volume is momentum: more taker buys → bullish → score > 0.5."""

    def test_balanced_is_neutral(self):
        score = MarketSentimentFeed._taker_volume_to_score(1.0)
        assert abs(score - 0.5) < 0.001

    def test_buy_heavy_is_bullish(self):
        """Ratio > 1 → taker buys dominate → bullish → score > 0.5."""
        score = MarketSentimentFeed._taker_volume_to_score(1.5)
        assert score > 0.5

    def test_sell_heavy_is_bearish(self):
        """Ratio < 1 → taker sells dominate (liquidation proxy) → bearish."""
        score = MarketSentimentFeed._taker_volume_to_score(0.7)
        assert score < 0.5

    def test_extreme_buys(self):
        """Ratio = 3.0 → heavily buy-skewed → strong bullish."""
        score = MarketSentimentFeed._taker_volume_to_score(3.0)
        assert score > 0.7

    def test_extreme_sells(self):
        """Ratio = 0.3 → heavy sell-side (liquidation cascade) → strong bearish."""
        score = MarketSentimentFeed._taker_volume_to_score(0.3)
        assert score < 0.3

    def test_zero_ratio_is_zero(self):
        score = MarketSentimentFeed._taker_volume_to_score(0.0)
        assert score == 0.0

    def test_negative_ratio_is_zero(self):
        score = MarketSentimentFeed._taker_volume_to_score(-1.0)
        assert score == 0.0

    def test_score_bounded_0_1(self):
        for ratio in [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]:
            score = MarketSentimentFeed._taker_volume_to_score(ratio)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Composite score calculation
# ---------------------------------------------------------------------------

class TestCompositeScore:
    """Test the composite market sentiment score computation."""

    def test_full_data_neutral(self):
        """All neutral data → composite near 0.5."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=50, classification="Neutral")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.0, long_pct=0.5, short_pct=0.5,
        )
        feed._liquidations["BTCUSDT"] = LiquidationData(
            symbol="BTCUSDT", buy_sell_ratio=1.0, buy_volume=1000, sell_volume=1000,
        )

        score = feed.get_market_sentiment_score("BTC/USDT")
        assert score is not None
        assert abs(score - 0.5) < 0.05

    def test_bullish_market(self):
        """Extreme fear + shorts overcrowded + buy-heavy → bullish (score > 0.5)."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=10, classification="Extreme Fear")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=0.43, long_pct=0.30, short_pct=0.70,
        )
        feed._liquidations["BTCUSDT"] = LiquidationData(
            symbol="BTCUSDT", buy_sell_ratio=2.0, buy_volume=2000, sell_volume=1000,
        )

        score = feed.get_market_sentiment_score("BTC/USDT")
        assert score is not None
        assert score > 0.65

    def test_bearish_market(self):
        """Extreme greed + longs overcrowded + sell-heavy → bearish (score < 0.5)."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=90, classification="Extreme Greed")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=2.33, long_pct=0.70, short_pct=0.30,
        )
        feed._liquidations["BTCUSDT"] = LiquidationData(
            symbol="BTCUSDT", buy_sell_ratio=0.5, buy_volume=500, sell_volume=1000,
        )

        score = feed.get_market_sentiment_score("BTC/USDT")
        assert score is not None
        assert score < 0.35

    def test_fear_greed_only(self):
        """Score computed with only F&G (no per-symbol data)."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=20, classification="Extreme Fear")

        # No ETHUSDT data → falls back to F&G only (+ maybe BTC proxy)
        score = feed.get_market_sentiment_score("ETH/USDT")
        assert score is not None
        assert score > 0.5  # fear is bullish (contrarian)

    def test_btc_proxy_fallback(self):
        """When per-symbol L/S data unavailable, falls back to BTC as market proxy."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=50, classification="Neutral")
        # Only BTC data available
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.0, long_pct=0.5, short_pct=0.5,
        )

        # Query for SOL/USDT which has no direct data
        score = feed.get_market_sentiment_score("SOL/USDT")
        assert score is not None
        # Should include F&G + BTC proxy for L/S → roughly neutral
        assert abs(score - 0.5) < 0.1

    def test_btc_proxy_uses_lower_weight(self):
        """BTC proxy for L/S ratio uses weight 0.30 instead of 0.40."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=50, classification="Neutral")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=0.43, long_pct=0.30, short_pct=0.70,
        )

        # Score should be > 0.5 (shorts overcrowded), but less extreme than direct data
        score = feed.get_market_sentiment_score("SOL/USDT")
        assert score is not None
        assert score > 0.5

    def test_score_clamped_to_0_1(self):
        """Score is always between 0 and 1."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=0, classification="Extreme Fear")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=0.1, long_pct=0.1, short_pct=0.9,
        )
        feed._liquidations["BTCUSDT"] = LiquidationData(
            symbol="BTCUSDT", buy_sell_ratio=10.0, buy_volume=10000, sell_volume=1000,
        )

        score = feed.get_market_sentiment_score("BTC/USDT")
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_symbol_mapping(self):
        """Score lookup maps 'BTC/USDT' to Binance 'BTCUSDT'."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.0, long_pct=0.5, short_pct=0.5,
        )
        feed._liquidations["BTCUSDT"] = LiquidationData(
            symbol="BTCUSDT", buy_sell_ratio=1.0, buy_volume=1000, sell_volume=1000,
        )

        # BTC/USDT → BTCUSDT lookup should work
        score = feed.get_market_sentiment_score("BTC/USDT")
        assert score is not None


# ---------------------------------------------------------------------------
# Display / contributing factors
# ---------------------------------------------------------------------------

class TestContributingFactors:
    def test_full_factors(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=20, classification="Extreme Fear")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.5, long_pct=0.60, short_pct=0.40,
        )
        feed._liquidations["BTCUSDT"] = LiquidationData(
            symbol="BTCUSDT", buy_sell_ratio=1.3, buy_volume=1300, sell_volume=1000,
        )
        feed._top_trader_ls["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.2, long_pct=0.55, short_pct=0.45,
        )

        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["available"] is True
        assert "fear_greed" in factors
        assert "long_short" in factors
        assert "taker_volume" in factors
        assert "top_traders" in factors

        # Fear & Greed details
        fg = factors["fear_greed"]
        assert fg["value"] == 20
        assert fg["classification"] == "Extreme Fear"
        assert fg["signal"] == "bullish"
        assert "score" in fg
        assert "interpretation" in fg

        # Long/Short details
        ls = factors["long_short"]
        assert ls["long_pct"] == 60.0
        assert ls["short_pct"] == 40.0
        assert "score" in ls
        assert "signal" in ls
        assert "interpretation" in ls

        # Taker Volume details
        tv = factors["taker_volume"]
        assert tv["buy_sell_ratio"] == 1.3
        assert "score" in tv
        assert tv["signal"] == "bullish"

        # Top Traders
        tt = factors["top_traders"]
        assert tt["long_pct"] == 55.0
        assert tt["short_pct"] == 45.0
        assert tt["signal"] == "neutral"

    def test_partial_factors_no_binance(self):
        """When only F&G available, factors only include fear_greed."""
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=75, classification="Greed")

        factors = feed.get_contributing_factors("UNKNOWN/USDT")
        assert factors["available"] is True
        assert "fear_greed" in factors
        assert "long_short" not in factors
        assert "taker_volume" not in factors

    def test_fear_greed_signal_neutral(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=50, classification="Neutral")
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["fear_greed"]["signal"] == "neutral"

    def test_fear_greed_signal_bearish(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=80, classification="Extreme Greed")
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["fear_greed"]["signal"] == "bearish"

    def test_long_short_signal_bearish(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._long_short["ETHUSDT"] = LongShortData(
            symbol="ETHUSDT", long_short_ratio=2.0, long_pct=0.70, short_pct=0.30,
        )
        factors = feed.get_contributing_factors("ETH/USDT")
        assert factors["long_short"]["signal"] == "bearish"

    def test_long_short_signal_bullish(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._long_short["ETHUSDT"] = LongShortData(
            symbol="ETHUSDT", long_short_ratio=0.4, long_pct=0.30, short_pct=0.70,
        )
        factors = feed.get_contributing_factors("ETH/USDT")
        assert factors["long_short"]["signal"] == "bullish"


# ---------------------------------------------------------------------------
# Query helper methods
# ---------------------------------------------------------------------------

class TestQueryHelpers:
    def test_get_long_short_ratio(self):
        feed = MarketSentimentFeed.get_instance()
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.5, long_pct=0.60, short_pct=0.40,
        )

        result = feed.get_long_short_ratio("BTC/USDT")
        assert result is not None
        assert result["symbol"] == "BTCUSDT"
        assert result["long_pct"] == 0.6
        assert result["short_pct"] == 0.4
        assert "score" in result
        assert "signal" in result

    def test_get_liquidation_data(self):
        feed = MarketSentimentFeed.get_instance()
        feed._liquidations["ETHUSDT"] = LiquidationData(
            symbol="ETHUSDT", buy_sell_ratio=1.2, buy_volume=1200, sell_volume=1000,
        )

        result = feed.get_liquidation_data("ETH/USDT")
        assert result is not None
        assert result["symbol"] == "ETHUSDT"
        assert result["buy_sell_ratio"] == 1.2
        assert result["buy_volume"] == 1200.0
        assert result["sell_volume"] == 1000.0
        assert "score" in result

    def test_get_fear_greed_extreme_values(self):
        feed = MarketSentimentFeed.get_instance()
        feed._fear_greed = FearGreedData(value=5, classification="Extreme Fear")
        fg = feed.get_fear_greed()
        assert fg["value"] == 5
        assert fg["classification"] == "Extreme Fear"
        assert fg["score"] > 0.8  # contrarian: extreme fear = bullish


# ---------------------------------------------------------------------------
# Fetch methods (mocked HTTP via respx)
# ---------------------------------------------------------------------------

class TestFetchMethods:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_fear_greed_success(self):
        respx.get(_FEAR_GREED_URL).mock(
            return_value=Response(200, json={
                "data": [
                    {
                        "value": "25",
                        "value_classification": "Extreme Fear",
                        "timestamp": "1700000000",
                    }
                ]
            })
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_fear_greed()

        assert result is True
        assert feed._fear_greed.value == 25
        assert feed._fear_greed.classification == "Extreme Fear"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_fear_greed_empty_data(self):
        respx.get(_FEAR_GREED_URL).mock(
            return_value=Response(200, json={"data": []})
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_fear_greed()
        assert result is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_fear_greed_server_error(self):
        respx.get(_FEAR_GREED_URL).mock(
            return_value=Response(500, json={"error": "server error"})
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_fear_greed()
        assert result is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_binance_long_short_success(self):
        respx.get(_BINANCE_LONG_SHORT_URL).mock(
            return_value=Response(200, json=[
                {
                    "symbol": "BTCUSDT",
                    "longShortRatio": "1.5000",
                    "longAccount": "0.6000",
                    "shortAccount": "0.4000",
                    "timestamp": 1700000000000,
                }
            ])
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_binance_long_short()

        assert result is True
        assert "BTCUSDT" in feed._long_short
        assert feed._long_short["BTCUSDT"].long_pct == 0.6
        assert feed._long_short["BTCUSDT"].short_pct == 0.4

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_binance_taker_volume_success(self):
        respx.get(_BINANCE_TAKER_VOLUME_URL).mock(
            return_value=Response(200, json=[
                {
                    "buySellRatio": "1.2000",
                    "buyVol": "1200.5",
                    "sellVol": "1000.3",
                    "timestamp": 1700000000000,
                }
            ])
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_binance_taker_volume()

        assert result is True
        assert "BTCUSDT" in feed._liquidations
        assert feed._liquidations["BTCUSDT"].buy_sell_ratio == 1.2
        assert feed._liquidations["BTCUSDT"].buy_volume == 1200.5
        assert feed._liquidations["BTCUSDT"].sell_volume == 1000.3

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_binance_top_trader_ls_success(self):
        respx.get(_BINANCE_TOP_TRADER_URL).mock(
            return_value=Response(200, json=[
                {
                    "symbol": "BTCUSDT",
                    "longShortRatio": "1.1000",
                    "longAccount": "0.5238",
                    "shortAccount": "0.4762",
                    "timestamp": 1700000000000,
                }
            ])
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_binance_top_trader_ls()

        assert result is True
        assert "BTCUSDT" in feed._top_trader_ls

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_binance_server_error(self):
        """Server errors are handled gracefully."""
        respx.get(_BINANCE_LONG_SHORT_URL).mock(
            return_value=Response(500, json={"error": "internal"})
        )
        feed = MarketSentimentFeed.get_instance()
        result = await feed._fetch_binance_long_short()

        assert result is False
        assert len(feed._long_short) == 0


# ---------------------------------------------------------------------------
# Healthcheck and start/stop
# ---------------------------------------------------------------------------

class TestLifecycle:
    @pytest.mark.asyncio
    async def test_healthcheck_initially_false(self):
        feed = MarketSentimentFeed.get_instance()
        assert await feed.healthcheck() is False

    @pytest.mark.asyncio
    async def test_start_enables_feed(self):
        feed = MarketSentimentFeed.get_instance()

        # Mock all fetches to succeed
        with patch.object(feed, "_fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            await feed.start()

        assert feed.is_enabled is True
        assert feed._is_running is True

        # Clean up
        await feed.stop()
        assert feed._is_running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        feed = MarketSentimentFeed.get_instance()

        with patch.object(feed, "_fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = None
            await feed.start()

        assert feed._fetch_task is not None
        await feed.stop()
        assert feed._fetch_task is None


# ---------------------------------------------------------------------------
# get_all_scores
# ---------------------------------------------------------------------------

class TestGetAllScores:
    def test_returns_scores_for_tracked_symbols(self):
        feed = MarketSentimentFeed.get_instance()
        feed._enabled = True
        feed._fear_greed = FearGreedData(value=40, classification="Fear")
        feed._long_short["BTCUSDT"] = LongShortData(
            symbol="BTCUSDT", long_short_ratio=1.0, long_pct=0.5, short_pct=0.5,
        )
        feed._long_short["ETHUSDT"] = LongShortData(
            symbol="ETHUSDT", long_short_ratio=1.2, long_pct=0.55, short_pct=0.45,
        )

        scores = feed.get_all_scores()
        assert "BTC/USDT" in scores
        assert "ETH/USDT" in scores
        assert 0.0 <= scores["BTC/USDT"] <= 1.0
        assert 0.0 <= scores["ETH/USDT"] <= 1.0
