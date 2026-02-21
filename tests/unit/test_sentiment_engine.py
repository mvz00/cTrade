"""Tests for the sentiment composite score engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ctrade.analysis.sentiment.engine import SentimentEngine
from ctrade.core.enums import SentimentLabel
from ctrade.core.models import SentimentDataPoint


def _make_dp(
    asset: str = "BTC",
    source: str = "cryptocompare",
    score: float = 0.7,
    label: SentimentLabel = SentimentLabel.POSITIVE,
    age_hours: float = 0,
) -> SentimentDataPoint:
    """Create a SentimentDataPoint with a specific age."""
    ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return SentimentDataPoint(
        asset=asset,
        source=source,
        score=score,
        label=label,
        raw_text="test",
        model_used="test",
        timestamp=ts,
    )


class TestSentimentEngine:
    def setup_method(self):
        self.engine = SentimentEngine()

    def test_empty_data_returns_neutral(self):
        assert self.engine.compute_score([]) == 0.5

    def test_single_bullish_point(self):
        points = [_make_dp(score=0.8, source="cryptocompare")]
        score = self.engine.compute_score(points)
        assert 0.7 < score <= 1.0

    def test_single_bearish_point(self):
        points = [_make_dp(score=0.2, source="reddit")]
        score = self.engine.compute_score(points)
        assert 0.0 <= score < 0.3

    def test_mixed_sources(self):
        points = [
            _make_dp(score=0.8, source="cryptocompare"),  # weight 0.40
            _make_dp(score=0.3, source="reddit"),          # weight 0.35
            _make_dp(score=0.6, source="coingecko"),       # weight 0.25
        ]
        score = self.engine.compute_score(points)
        assert 0.3 < score < 0.8

    def test_time_decay_recent_higher(self):
        """Recent data points should have more influence than old ones."""
        recent = _make_dp(score=0.9, source="cryptocompare", age_hours=0.5)
        old = _make_dp(score=0.1, source="cryptocompare", age_hours=12.0)
        score = self.engine.compute_score([recent, old])
        # Recent bullish should dominate
        assert score > 0.5

    def test_time_decay_old_higher(self):
        """When old data is bullish but recent is bearish, recent should dominate."""
        old = _make_dp(score=0.9, source="reddit", age_hours=12.0)
        recent = _make_dp(score=0.1, source="reddit", age_hours=0.5)
        score = self.engine.compute_score([old, recent])
        # Recent bearish should dominate
        assert score < 0.5

    def test_max_age_filter(self):
        """Points older than max_age_hours should be excluded."""
        old = _make_dp(score=0.1, source="cryptocompare", age_hours=25)
        recent = _make_dp(score=0.8, source="cryptocompare", age_hours=1)
        score = self.engine.compute_score([old, recent], max_age_hours=24)
        # Only recent should count
        assert score > 0.7

    def test_all_expired_returns_neutral(self):
        points = [_make_dp(score=0.9, age_hours=30)]
        score = self.engine.compute_score(points, max_age_hours=24)
        assert score == 0.5

    def test_score_bounds(self):
        """Score should always be in [0, 1]."""
        for s in [0.0, 0.1, 0.5, 0.9, 1.0]:
            points = [_make_dp(score=s)]
            result = self.engine.compute_score(points)
            assert 0.0 <= result <= 1.0

    def test_unknown_source_uses_default_weight(self):
        points = [_make_dp(score=0.8, source="unknown_source")]
        score = self.engine.compute_score(points)
        assert 0.5 < score <= 1.0


class TestContributingFactors:
    def setup_method(self):
        self.engine = SentimentEngine()

    def test_empty_data(self):
        factors = self.engine.compute_contributing_factors([])
        assert factors["score"] == 0.5
        assert factors["signal"] == "neutral"
        assert factors["data_points"] == 0

    def test_bullish_signal(self):
        points = [_make_dp(score=0.85)]
        factors = self.engine.compute_contributing_factors(points)
        assert factors["signal"] == "bullish"
        assert factors["data_points"] == 1

    def test_bearish_signal(self):
        points = [_make_dp(score=0.15)]
        factors = self.engine.compute_contributing_factors(points)
        assert factors["signal"] == "bearish"

    def test_source_breakdown(self):
        points = [
            _make_dp(score=0.8, source="cryptocompare"),
            _make_dp(score=0.6, source="reddit"),
        ]
        factors = self.engine.compute_contributing_factors(points)
        assert "sources" in factors
        assert "cryptocompare" in factors["sources"]
        assert "reddit" in factors["sources"]
        assert "source_counts" in factors
