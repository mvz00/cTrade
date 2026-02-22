"""Tests for the CVD (Cumulative Volume Delta) divergence feed."""

from __future__ import annotations

import math

import pytest

from ctrade.feeds.cvd import (
    CVDFeed,
    CVDSnapshot,
    _CVD_NORM_SCALE,
    _DIVERGENCE_SENSITIVITY,
    _PRICE_NORM_SCALE,
)


@pytest.fixture(autouse=True)
def reset_feed():
    """Reset the singleton between tests."""
    CVDFeed.reset()
    yield
    CVDFeed.reset()


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestCVDFeedSingleton:
    def test_get_instance(self):
        a = CVDFeed.get_instance()
        b = CVDFeed.get_instance()
        assert a is b

    def test_reset(self):
        a = CVDFeed.get_instance()
        CVDFeed.reset()
        b = CVDFeed.get_instance()
        assert a is not b

    def test_initial_state(self):
        feed = CVDFeed.get_instance()
        assert feed.name == "cvd"
        assert not feed.is_enabled


# ---------------------------------------------------------------------------
# Score queries when disabled / empty
# ---------------------------------------------------------------------------

class TestCVDFeedQueries:
    def test_get_cvd_score_when_disabled(self):
        feed = CVDFeed.get_instance()
        assert feed.get_cvd_score("BTC/USDT") is None

    def test_get_cvd_score_when_enabled_but_no_data(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        assert feed.get_cvd_score("BTC/USDT") is None

    def test_get_snapshot_when_no_data(self):
        feed = CVDFeed.get_instance()
        assert feed.get_snapshot("BTC/USDT") is None

    def test_get_all_scores_empty(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        assert feed.get_all_scores() == {}

    def test_get_contributing_factors_disabled(self):
        feed = CVDFeed.get_instance()
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors == {"available": False}

    def test_get_contributing_factors_no_data(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors == {"available": True, "data": False}


# ---------------------------------------------------------------------------
# CVD divergence scoring (_cvd_divergence_to_score)
# ---------------------------------------------------------------------------

class TestCVDDivergenceScoring:
    """Price-CVD divergence is the primary signal: CVD disagrees with price."""

    def test_both_flat_returns_neutral(self):
        """Both price and CVD flat (abs < 0.1) -> 0.5."""
        score = CVDFeed._cvd_divergence_to_score(0.0, 0.0)
        assert score == 0.5

    def test_both_flat_near_threshold(self):
        """Both below 0.1 threshold -> still neutral."""
        score = CVDFeed._cvd_divergence_to_score(0.05, -0.09)
        assert score == 0.5

    def test_price_up_cvd_down_is_bearish(self):
        """Price up + CVD down -> distribution -> bearish -> score < 0.5."""
        score = CVDFeed._cvd_divergence_to_score(5.0, -10.0)
        assert score < 0.5

    def test_price_down_cvd_up_is_bullish(self):
        """Price down + CVD up -> accumulation -> bullish -> score > 0.5."""
        score = CVDFeed._cvd_divergence_to_score(-5.0, 10.0)
        assert score > 0.5

    def test_both_up_is_mildly_bullish(self):
        """Both up (confirmation) -> mild bullish -> score > 0.5."""
        score = CVDFeed._cvd_divergence_to_score(3.0, 8.0)
        assert score > 0.5

    def test_both_down_is_mildly_bearish(self):
        """Both down (confirmation) -> mild bearish -> score < 0.5."""
        score = CVDFeed._cvd_divergence_to_score(-3.0, -8.0)
        assert score < 0.5

    def test_extreme_values_bounded_low(self):
        """Extreme bearish divergence stays within [0, 1]."""
        score = CVDFeed._cvd_divergence_to_score(100.0, -100.0)
        assert 0.0 <= score <= 1.0

    def test_extreme_values_bounded_high(self):
        """Extreme bullish divergence stays within [0, 1]."""
        score = CVDFeed._cvd_divergence_to_score(-100.0, 100.0)
        assert 0.0 <= score <= 1.0

    def test_score_bounded_over_many_inputs(self):
        """Score is always bounded [0, 1] regardless of input magnitude."""
        for price in [-50, -10, -1, 0, 1, 10, 50]:
            for cvd in [-50, -10, -1, 0, 1, 10, 50]:
                score = CVDFeed._cvd_divergence_to_score(price, cvd)
                assert 0.0 <= score <= 1.0, f"Out of range at price={price}, cvd={cvd}"

    def test_monotonicity_increasing_bullish_divergence(self):
        """As CVD rises more (relative to falling price), score should increase."""
        scores = []
        for cvd_pct in [2.0, 5.0, 10.0, 20.0, 40.0]:
            score = CVDFeed._cvd_divergence_to_score(-3.0, cvd_pct)
            scores.append(score)

        for i in range(len(scores) - 1):
            assert scores[i] <= scores[i + 1], (
                f"Score should increase: {scores[i]} <= {scores[i+1]}"
            )

    def test_monotonicity_increasing_bearish_divergence(self):
        """As CVD falls more (relative to rising price), score should decrease."""
        scores = []
        for cvd_pct in [-2.0, -5.0, -10.0, -20.0, -40.0]:
            score = CVDFeed._cvd_divergence_to_score(3.0, cvd_pct)
            scores.append(score)

        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Score should decrease: {scores[i]} >= {scores[i+1]}"
            )

    def test_score_math_matches_formula(self):
        """Verify the score matches the expected sigmoid of divergence formula."""
        price_pct = 4.0
        cvd_pct = -8.0

        price_norm = math.tanh(price_pct / _PRICE_NORM_SCALE)
        cvd_norm = math.tanh(cvd_pct / _CVD_NORM_SCALE)
        divergence = cvd_norm - price_norm
        expected = 1.0 / (1.0 + math.exp(-divergence * _DIVERGENCE_SENSITIVITY))

        actual = CVDFeed._cvd_divergence_to_score(price_pct, cvd_pct)
        assert abs(actual - expected) < 1e-9


# ---------------------------------------------------------------------------
# CVD acceleration scoring (_cvd_acceleration_score via composite)
# ---------------------------------------------------------------------------

class TestCVDAccelerationScoring:
    """Acceleration is mapped via: 0.5 + tanh(accel) * 0.5."""

    @staticmethod
    def _accel_score(acceleration: float) -> float:
        """Replicate the inline acceleration score from get_cvd_score."""
        return 0.5 + math.tanh(acceleration) * 0.5

    def test_zero_acceleration_is_neutral(self):
        score = self._accel_score(0.0)
        assert abs(score - 0.5) < 0.001

    def test_positive_acceleration_is_bullish(self):
        score = self._accel_score(1.0)
        assert score > 0.5

    def test_negative_acceleration_is_bearish(self):
        score = self._accel_score(-1.0)
        assert score < 0.5

    def test_large_positive_bounded(self):
        score = self._accel_score(100.0)
        assert 0.0 <= score <= 1.0

    def test_large_negative_bounded(self):
        score = self._accel_score(-100.0)
        assert 0.0 <= score <= 1.0

    def test_symmetry(self):
        """Positive and negative of equal magnitude equidistant from 0.5."""
        pos = self._accel_score(0.5)
        neg = self._accel_score(-0.5)
        assert abs((pos - 0.5) + (neg - 0.5)) < 1e-9


# ---------------------------------------------------------------------------
# Composite score calculation
# ---------------------------------------------------------------------------

class TestCompositeScore:
    """Test the composite CVD score computation via injected snapshots."""

    def test_neutral_snapshot(self):
        """Flat price + flat CVD + zero acceleration -> composite near 0.5."""
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=0.0,
            cvd_change_pct=0.0,
            cvd_acceleration=0.0,
        )

        score = feed.get_cvd_score("BTC/USDT")
        assert score is not None
        assert abs(score - 0.5) < 0.01

    def test_bullish_divergence_snapshot(self):
        """Price down + CVD up -> composite > 0.5."""
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=-5.0,
            cvd_change_pct=15.0,
            divergence_type="bullish_div",
            cvd_acceleration=0.5,
        )

        score = feed.get_cvd_score("BTC/USDT")
        assert score is not None
        assert score > 0.55

    def test_bearish_divergence_snapshot(self):
        """Price up + CVD down -> composite < 0.5."""
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=5.0,
            cvd_change_pct=-15.0,
            divergence_type="bearish_div",
            cvd_acceleration=-0.5,
        )

        score = feed.get_cvd_score("BTC/USDT")
        assert score is not None
        assert score < 0.45

    def test_composite_formula_exact(self):
        """Verify composite = 0.90 * divergence + 0.10 * acceleration."""
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["ETH/USDT"] = CVDSnapshot(
            symbol="ETH/USDT",
            price_change_pct=-3.0,
            cvd_change_pct=12.0,
            cvd_acceleration=0.8,
        )

        score = feed.get_cvd_score("ETH/USDT")
        assert score is not None

        # Manually compute expected
        div_score = CVDFeed._cvd_divergence_to_score(-3.0, 12.0)
        accel_score = 0.5 + math.tanh(0.8) * 0.5
        expected = round(max(0.0, min(1.0, 0.90 * div_score + 0.10 * accel_score)), 4)

        assert score == expected

    def test_score_clamped_to_0_1(self):
        """Extreme inputs still produce a score in [0, 1]."""
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=100.0,
            cvd_change_pct=-100.0,
            cvd_acceleration=-50.0,
        )

        score = feed.get_cvd_score("BTC/USDT")
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_symbol_lookup_by_base(self):
        """Score lookup works with base symbol prefix matching."""
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=0.0,
            cvd_change_pct=0.0,
            cvd_acceleration=0.0,
        )

        # Should find BTC/USDT when querying BTC/USD (prefix match)
        score = feed.get_cvd_score("BTC/USD")
        assert score is not None


# ---------------------------------------------------------------------------
# Contributing factors
# ---------------------------------------------------------------------------

class TestContributingFactors:
    def test_contributing_factors_bullish_div(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=-4.0,
            cvd_change_pct=12.0,
            divergence_type="bullish_div",
            cvd_acceleration=0.3,
        )

        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["available"] is True
        assert factors["data"] is True
        assert factors["price_change_pct"] == -4.0
        assert factors["cvd_change_pct"] == 12.0
        assert factors["divergence_type"] == "bullish_div"
        assert "divergence_score" in factors
        assert factors["signal"] == "bullish"
        assert "accumulation" in factors["interpretation"]

    def test_contributing_factors_bearish_div(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["ETH/USDT"] = CVDSnapshot(
            symbol="ETH/USDT",
            price_change_pct=3.0,
            cvd_change_pct=-10.0,
            divergence_type="bearish_div",
            cvd_acceleration=-0.2,
        )

        factors = feed.get_contributing_factors("ETH/USDT")
        assert factors["signal"] == "bearish"
        assert "distribution" in factors["interpretation"]

    def test_contributing_factors_confirmation(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["SOL/USDT"] = CVDSnapshot(
            symbol="SOL/USDT",
            price_change_pct=2.0,
            cvd_change_pct=8.0,
            divergence_type="confirmation_bull",
            cvd_acceleration=0.1,
        )

        factors = feed.get_contributing_factors("SOL/USDT")
        assert factors["signal"] == "neutral"
        assert "aligned" in factors["interpretation"]

    def test_contributing_factors_none_divergence(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["DOGE/USDT"] = CVDSnapshot(
            symbol="DOGE/USDT",
            price_change_pct=0.1,
            cvd_change_pct=0.2,
            divergence_type="none",
            cvd_acceleration=0.0,
        )

        factors = feed.get_contributing_factors("DOGE/USDT")
        assert factors["signal"] == "neutral"
        assert "no significant divergence" in factors["interpretation"]


# ---------------------------------------------------------------------------
# get_all_scores
# ---------------------------------------------------------------------------

class TestGetAllScores:
    def test_returns_scores_for_all_tracked(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._snapshots["BTC/USDT"] = CVDSnapshot(
            symbol="BTC/USDT",
            price_change_pct=0.0,
            cvd_change_pct=0.0,
            cvd_acceleration=0.0,
        )
        feed._snapshots["ETH/USDT"] = CVDSnapshot(
            symbol="ETH/USDT",
            price_change_pct=-2.0,
            cvd_change_pct=8.0,
            cvd_acceleration=0.5,
        )

        scores = feed.get_all_scores()
        assert "BTC/USDT" in scores
        assert "ETH/USDT" in scores
        assert 0.0 <= scores["BTC/USDT"] <= 1.0
        assert 0.0 <= scores["ETH/USDT"] <= 1.0


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_get_status_structure(self):
        feed = CVDFeed.get_instance()
        status = feed.get_status()
        assert "enabled" in status
        assert "healthy" in status
        assert "last_fetch" in status
        assert "symbols_tracked" in status
        assert "watched_symbols" in status
        assert "poll_interval" in status

    def test_get_status_initial_values(self):
        feed = CVDFeed.get_instance()
        status = feed.get_status()
        assert status["enabled"] is False
        assert status["healthy"] is False
        assert status["last_fetch"] is None
        assert status["symbols_tracked"] == 0
        assert status["watched_symbols"] == []

    def test_get_status_with_data(self):
        feed = CVDFeed.get_instance()
        feed._enabled = True
        feed._healthy = True
        feed._watched_symbols = ["BTC/USDT", "ETH/USDT"]
        feed._snapshots["BTC/USDT"] = CVDSnapshot(symbol="BTC/USDT")

        status = feed.get_status()
        assert status["enabled"] is True
        assert status["healthy"] is True
        assert status["symbols_tracked"] == 1
        assert status["watched_symbols"] == ["BTC/USDT", "ETH/USDT"]
