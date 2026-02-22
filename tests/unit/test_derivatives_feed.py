"""Tests for the derivatives data feed (funding rate, OI, order book)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ctrade.feeds.derivatives import (
    DerivativesFeed,
    DerivativesSnapshot,
    _BOOK_IMBALANCE_SCALE,
    _FUNDING_SCALE,
    _OI_CHANGE_SCALE,
)


@pytest.fixture(autouse=True)
def reset_feed():
    """Reset the singleton between tests."""
    DerivativesFeed.reset()
    yield
    DerivativesFeed.reset()


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestDerivativesFeedSingleton:
    def test_get_instance(self):
        a = DerivativesFeed.get_instance()
        b = DerivativesFeed.get_instance()
        assert a is b

    def test_reset(self):
        a = DerivativesFeed.get_instance()
        DerivativesFeed.reset()
        b = DerivativesFeed.get_instance()
        assert a is not b

    def test_initial_state(self):
        feed = DerivativesFeed.get_instance()
        assert feed.name == "derivatives"
        assert not feed.is_enabled


# ---------------------------------------------------------------------------
# Score queries when disabled / empty
# ---------------------------------------------------------------------------

class TestDerivativesFeedQueries:
    def test_get_score_when_disabled(self):
        feed = DerivativesFeed.get_instance()
        assert feed.get_derivatives_score("BTC/USDT") is None

    def test_get_score_when_enabled_but_no_data(self):
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        assert feed.get_derivatives_score("BTC/USDT") is None

    def test_get_snapshot_when_no_data(self):
        feed = DerivativesFeed.get_instance()
        assert feed.get_snapshot("BTC/USDT") is None

    def test_get_all_scores_empty(self):
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        assert feed.get_all_scores() == {}

    def test_get_status(self):
        feed = DerivativesFeed.get_instance()
        status = feed.get_status()
        assert "enabled" in status
        assert "healthy" in status
        assert "symbols_tracked" in status
        assert "watched_symbols" in status
        assert "poll_interval" in status

    def test_get_contributing_factors_no_data(self):
        feed = DerivativesFeed.get_instance()
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors == {"available": False}


# ---------------------------------------------------------------------------
# Scoring functions (unit tests for sigmoid transforms)
# ---------------------------------------------------------------------------

class TestFundingRateScoring:
    """Funding rate is a contrarian indicator: high positive funding → bearish → low score."""

    def test_zero_funding_is_neutral(self):
        score = DerivativesFeed._funding_rate_to_score(0.0)
        assert abs(score - 0.5) < 0.001

    def test_positive_funding_is_bearish(self):
        """High positive funding (longs overleveraged) → score < 0.5."""
        score = DerivativesFeed._funding_rate_to_score(0.001)  # 0.1%
        assert score < 0.5

    def test_negative_funding_is_bullish(self):
        """Negative funding (shorts overleveraged) → score > 0.5."""
        score = DerivativesFeed._funding_rate_to_score(-0.001)  # -0.1%
        assert score > 0.5

    def test_extreme_positive_funding(self):
        """Very high funding → strongly bearish → score well below 0.5."""
        score = DerivativesFeed._funding_rate_to_score(0.005)  # 0.5%
        assert score < 0.3

    def test_extreme_negative_funding(self):
        """Very negative funding → strongly bullish → score well above 0.5."""
        score = DerivativesFeed._funding_rate_to_score(-0.005)  # -0.5%
        assert score > 0.7

    def test_score_bounded_0_1(self):
        """Score is always between 0 and 1."""
        for rate in [-0.1, -0.01, 0, 0.01, 0.1]:
            score = DerivativesFeed._funding_rate_to_score(rate)
            assert 0.0 <= score <= 1.0


class TestOIChangeScoring:
    """Open interest change: rising OI = trend strength → score > 0.5."""

    def test_zero_change_is_neutral(self):
        score = DerivativesFeed._oi_change_to_score(0.0)
        assert abs(score - 0.5) < 0.001

    def test_rising_oi_is_bullish(self):
        """Rising OI → trend strengthening → score > 0.5."""
        score = DerivativesFeed._oi_change_to_score(5.0)
        assert score > 0.5

    def test_falling_oi_is_bearish(self):
        """Falling OI → trend weakening → score < 0.5."""
        score = DerivativesFeed._oi_change_to_score(-5.0)
        assert score < 0.5

    def test_extreme_rising_oi(self):
        score = DerivativesFeed._oi_change_to_score(20.0)
        assert score > 0.7

    def test_score_bounded_0_1(self):
        for pct in [-50, -10, 0, 10, 50]:
            score = DerivativesFeed._oi_change_to_score(pct)
            assert 0.0 <= score <= 1.0


class TestOrderBookScoring:
    """Order book imbalance: bid-heavy → bullish → score > 0.5."""

    def test_balanced_book_is_neutral(self):
        score = DerivativesFeed._book_imbalance_to_score(1.0)
        assert abs(score - 0.5) < 0.001

    def test_bid_heavy_is_bullish(self):
        """More bids than asks → buying pressure → score > 0.5."""
        score = DerivativesFeed._book_imbalance_to_score(2.0)
        assert score > 0.5

    def test_ask_heavy_is_bearish(self):
        """More asks than bids → selling pressure → score < 0.5."""
        score = DerivativesFeed._book_imbalance_to_score(0.5)
        assert score < 0.5

    def test_extreme_bid_ratio(self):
        """3:1 bid ratio → imminent price increase → high score."""
        score = DerivativesFeed._book_imbalance_to_score(3.0)
        assert score > 0.6

    def test_zero_ratio_is_zero(self):
        score = DerivativesFeed._book_imbalance_to_score(0.0)
        assert score == 0.0

    def test_score_bounded_0_1(self):
        for ratio in [0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]:
            score = DerivativesFeed._book_imbalance_to_score(ratio)
            assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Composite score calculation
# ---------------------------------------------------------------------------

class TestCompositeScore:
    """Test the composite derivatives score computation."""

    def test_full_data_neutral(self):
        """All neutral data → composite near 0.5."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.0,
            open_interest_usd=1_000_000,
            prev_open_interest_usd=1_000_000,  # 0% change
            bid_volume=100_000,
            ask_volume=100_000,
            bid_ask_ratio=1.0,
        )

        score = feed.get_derivatives_score("BTC/USDT")
        assert score is not None
        assert abs(score - 0.5) < 0.05  # close to neutral

    def test_bullish_data(self):
        """Negative funding + rising OI + bid-heavy book → bullish (score > 0.5)."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=-0.002,  # shorts overleveraged → bullish
            open_interest_usd=1_100_000,
            prev_open_interest_usd=1_000_000,  # +10% OI
            bid_volume=300_000,
            ask_volume=100_000,
            bid_ask_ratio=3.0,  # strong bid dominance
        )

        score = feed.get_derivatives_score("BTC/USDT")
        assert score is not None
        assert score > 0.55

    def test_bearish_data(self):
        """Positive funding + falling OI + ask-heavy book → bearish (score < 0.5)."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.002,  # longs overleveraged → bearish
            open_interest_usd=900_000,
            prev_open_interest_usd=1_000_000,  # -10% OI
            bid_volume=100_000,
            ask_volume=300_000,
            bid_ask_ratio=0.333,  # strong ask dominance
        )

        score = feed.get_derivatives_score("BTC/USDT")
        assert score is not None
        assert score < 0.45

    def test_partial_data_funding_only(self):
        """Score computed with only funding rate available."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["ETH/USDT"] = DerivativesSnapshot(
            symbol="ETH/USDT",
            funding_rate=-0.001,
        )

        score = feed.get_derivatives_score("ETH/USDT")
        assert score is not None
        assert score > 0.5  # negative funding is bullish

    def test_partial_data_order_book_only(self):
        """Score computed with only order book data available."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["SOL/USDT"] = DerivativesSnapshot(
            symbol="SOL/USDT",
            bid_volume=200_000,
            ask_volume=100_000,
            bid_ask_ratio=2.0,
        )

        score = feed.get_derivatives_score("SOL/USDT")
        assert score is not None
        assert score > 0.5  # bid-heavy is bullish

    def test_score_clamped_to_0_1(self):
        """Score is always between 0 and 1 regardless of extreme inputs."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.1,  # extreme
            open_interest_usd=10,
            prev_open_interest_usd=1_000_000,  # massive drop
            bid_volume=1,
            ask_volume=1_000_000,
            bid_ask_ratio=0.000001,  # extreme
        )

        score = feed.get_derivatives_score("BTC/USDT")
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_symbol_lookup_by_base(self):
        """Score lookup works with base symbol prefix matching."""
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.0,
            bid_volume=100_000,
            ask_volume=100_000,
            bid_ask_ratio=1.0,
        )

        # Should find BTC/USDT when querying BTC/USD (prefix match)
        score = feed.get_derivatives_score("BTC/USD")
        assert score is not None


# ---------------------------------------------------------------------------
# Snapshot and contributing factors display
# ---------------------------------------------------------------------------

class TestDerivativesDisplay:
    def test_get_snapshot_with_full_data(self):
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.0001,
            open_interest_usd=1_000_000,
            prev_open_interest_usd=900_000,
            bid_volume=150_000,
            ask_volume=100_000,
            bid_ask_ratio=1.5,
        )

        snap = feed.get_snapshot("BTC/USDT")
        assert snap is not None
        assert snap["symbol"] == "BTC/USDT"
        assert snap["funding_rate"] == 0.0001
        assert snap["funding_rate_pct"] == pytest.approx(0.01, abs=0.001)
        assert snap["open_interest_usd"] == 1_000_000
        assert snap["oi_change_pct"] == pytest.approx(11.11, abs=0.1)
        assert snap["bid_volume"] == 150_000
        assert snap["ask_volume"] == 100_000
        assert snap["bid_ask_ratio"] == 1.5

    def test_get_contributing_factors_full(self):
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.0001,
            open_interest_usd=1_100_000,
            prev_open_interest_usd=1_000_000,
            bid_volume=200_000,
            ask_volume=100_000,
            bid_ask_ratio=2.0,
        )

        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["available"] is True
        assert "funding_rate" in factors
        assert "open_interest" in factors
        assert "order_book" in factors

        # Check funding rate factor
        assert "raw" in factors["funding_rate"]
        assert "score" in factors["funding_rate"]
        assert "signal" in factors["funding_rate"]

        # Check order book factor
        assert factors["order_book"]["ratio"] == 2.0
        assert factors["order_book"]["signal"] == "bullish"


# ---------------------------------------------------------------------------
# Fetch methods (mocked exchange)
# ---------------------------------------------------------------------------

class TestDerivativesFeedFetch:
    """Test the fetch methods with mocked ccxt exchange."""

    @pytest.mark.asyncio
    async def test_fetch_funding_rate_success(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()
        mock_exchange.fetch_funding_rate = AsyncMock(return_value={
            "fundingRate": 0.0001,
            "fundingTimestamp": 1700000000,
        })

        result = await feed._fetch_funding_rate(mock_exchange, "BTC/USDT")
        assert result is not None
        assert result["rate"] == 0.0001
        assert result["timestamp"] == 1700000000

    @pytest.mark.asyncio
    async def test_fetch_funding_rate_not_supported(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = MagicMock(spec=[])  # no fetch_funding_rate attribute

        result = await feed._fetch_funding_rate(mock_exchange, "BTC/USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_funding_rate_fallback_to_perp_symbol(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()
        # First call (spot symbol) fails, second call (perp) succeeds
        mock_exchange.fetch_funding_rate = AsyncMock(
            side_effect=[
                Exception("Not found"),
                {"fundingRate": -0.0002, "fundingTimestamp": None},
            ]
        )

        result = await feed._fetch_funding_rate(mock_exchange, "BTC/USDT")
        assert result is not None
        assert result["rate"] == -0.0002

    @pytest.mark.asyncio
    async def test_fetch_open_interest_success(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()
        mock_exchange.fetch_open_interest = AsyncMock(return_value={
            "openInterestValue": 5_000_000.0,
            "openInterestAmount": 100.0,
        })

        result = await feed._fetch_open_interest(mock_exchange, "BTC/USDT")
        assert result == 5_000_000.0

    @pytest.mark.asyncio
    async def test_fetch_open_interest_amount_fallback(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()
        mock_exchange.fetch_open_interest = AsyncMock(return_value={
            "openInterestValue": None,
            "openInterestAmount": 100.0,
        })

        result = await feed._fetch_open_interest(mock_exchange, "BTC/USDT")
        assert result == 100.0

    @pytest.mark.asyncio
    async def test_fetch_open_interest_not_supported(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = MagicMock(spec=[])

        result = await feed._fetch_open_interest(mock_exchange, "BTC/USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_order_book_success(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()
        mock_exchange.fetch_order_book = AsyncMock(return_value={
            "bids": [[50000, 1.0], [49900, 2.0], [49800, 1.5]],
            "asks": [[50100, 0.5], [50200, 1.0], [50300, 0.5]],
        })

        result = await feed._fetch_order_book(mock_exchange, "BTC/USDT")
        assert result is not None
        assert result["bid_volume"] > 0
        assert result["ask_volume"] > 0
        assert result["ratio"] > 0

        # Verify USD volume calculation
        expected_bid = 50000 * 1.0 + 49900 * 2.0 + 49800 * 1.5
        expected_ask = 50100 * 0.5 + 50200 * 1.0 + 50300 * 0.5
        assert result["bid_volume"] == pytest.approx(expected_bid, rel=0.001)
        assert result["ask_volume"] == pytest.approx(expected_ask, rel=0.001)
        assert result["ratio"] == pytest.approx(expected_bid / expected_ask, rel=0.001)

    @pytest.mark.asyncio
    async def test_fetch_order_book_empty(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()
        mock_exchange.fetch_order_book = AsyncMock(return_value={
            "bids": [],
            "asks": [],
        })

        result = await feed._fetch_order_book(mock_exchange, "BTC/USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_order_book_not_supported(self):
        feed = DerivativesFeed.get_instance()
        mock_exchange = MagicMock(spec=[])

        result = await feed._fetch_order_book(mock_exchange, "BTC/USDT")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_symbol_data_partial(self):
        """Test that partial data (only order book) still produces a snapshot."""
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()

        # Funding rate and OI fail, order book succeeds
        mock_exchange.fetch_funding_rate = AsyncMock(side_effect=Exception("Not supported"))
        mock_exchange.fetch_open_interest = AsyncMock(side_effect=Exception("Not supported"))
        mock_exchange.fetch_order_book = AsyncMock(return_value={
            "bids": [[50000, 2.0], [49900, 1.0]],
            "asks": [[50100, 1.0], [50200, 0.5]],
        })

        snapshot = await feed._fetch_symbol_data(mock_exchange, "BTC/USDT")
        assert snapshot is not None
        assert snapshot.funding_rate is None
        assert snapshot.open_interest_usd is None
        assert snapshot.bid_ask_ratio is not None

    @pytest.mark.asyncio
    async def test_fetch_symbol_data_all_fail(self):
        """When all fetches fail, returns None."""
        feed = DerivativesFeed.get_instance()
        mock_exchange = MagicMock(spec=[])  # no methods at all

        snapshot = await feed._fetch_symbol_data(mock_exchange, "BTC/USDT")
        assert snapshot is None

    @pytest.mark.asyncio
    async def test_oi_change_tracking(self):
        """Previous OI is tracked for change calculation."""
        feed = DerivativesFeed.get_instance()
        mock_exchange = AsyncMock()

        # First fetch: OI = 1,000,000
        mock_exchange.fetch_funding_rate = AsyncMock(side_effect=Exception("N/A"))
        mock_exchange.fetch_open_interest = AsyncMock(return_value={
            "openInterestValue": 1_000_000.0,
        })
        mock_exchange.fetch_order_book = AsyncMock(side_effect=Exception("N/A"))

        snap1 = await feed._fetch_symbol_data(mock_exchange, "BTC/USDT")
        assert snap1 is not None
        assert snap1.open_interest_usd == 1_000_000.0
        assert snap1.prev_open_interest_usd is None  # first fetch, no prev

        # Second fetch: OI = 1,100,000
        mock_exchange.fetch_open_interest = AsyncMock(return_value={
            "openInterestValue": 1_100_000.0,
        })

        snap2 = await feed._fetch_symbol_data(mock_exchange, "BTC/USDT")
        assert snap2 is not None
        assert snap2.open_interest_usd == 1_100_000.0
        assert snap2.prev_open_interest_usd == 1_000_000.0  # from first fetch


# ---------------------------------------------------------------------------
# Test get_all_scores
# ---------------------------------------------------------------------------

class TestGetAllScores:
    def test_returns_scores_for_all_tracked(self):
        feed = DerivativesFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = DerivativesSnapshot(
            symbol="BTC/USDT",
            funding_rate=0.0,
            bid_volume=100_000,
            ask_volume=100_000,
            bid_ask_ratio=1.0,
        )
        feed._snapshots["ETH/USDT"] = DerivativesSnapshot(
            symbol="ETH/USDT",
            funding_rate=-0.001,
        )

        scores = feed.get_all_scores()
        assert "BTC/USDT" in scores
        assert "ETH/USDT" in scores
        assert 0.0 <= scores["BTC/USDT"] <= 1.0
        assert 0.0 <= scores["ETH/USDT"] <= 1.0
