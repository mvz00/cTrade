"""Tests for the on-chain composite score engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ctrade.analysis.onchain.engine import OnChainEngine
from ctrade.core.models import OnChainMetric


def _make_metric(
    asset: str = "BTC",
    name: str = "hash_rate",
    value: float = 500e18,
    source: str = "blockchain.info",
    age_hours: float = 0,
) -> OnChainMetric:
    """Create an OnChainMetric with a specific age."""
    ts = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return OnChainMetric(
        asset=asset,
        metric_name=name,
        metric_value=Decimal(str(value)),
        source=source,
        timestamp=ts,
    )


class TestOnChainEngine:
    def setup_method(self):
        self.engine = OnChainEngine()

    def test_empty_metrics_returns_neutral(self):
        assert self.engine.compute_score([]) == 0.5

    def test_single_baseline_metric(self):
        """Baseline values should score around 0.5."""
        metrics = [_make_metric(name="hash_rate", value=500e18)]
        score = self.engine.compute_score(metrics)
        assert 0.45 <= score <= 0.55

    def test_high_hash_rate_bullish(self):
        metrics = [_make_metric(name="hash_rate", value=800e18)]
        score = self.engine.compute_score(metrics)
        assert score > 0.55

    def test_low_hash_rate_bearish(self):
        metrics = [_make_metric(name="hash_rate", value=200e18)]
        score = self.engine.compute_score(metrics)
        assert score < 0.45

    def test_multiple_metrics(self):
        metrics = [
            _make_metric(name="hash_rate", value=600e18),
            _make_metric(name="tx_count_24h", value=400000),
            _make_metric(name="volume_24h", value=50e9),
        ]
        score = self.engine.compute_score(metrics)
        # All above baseline -> bullish
        assert score > 0.55

    def test_max_age_filter(self):
        old = _make_metric(name="hash_rate", value=800e18, age_hours=30)
        recent = _make_metric(name="hash_rate", value=300e18, age_hours=1)
        score = self.engine.compute_score([old, recent], max_age_hours=24)
        # Only recent (low) should count
        assert score < 0.5

    def test_all_expired_returns_neutral(self):
        metrics = [_make_metric(age_hours=30)]
        score = self.engine.compute_score(metrics, max_age_hours=24)
        assert score == 0.5

    def test_latest_value_per_metric(self):
        """When multiple values exist for the same metric, only the latest counts."""
        older = _make_metric(name="volume_24h", value=10e9, age_hours=5)
        newer = _make_metric(name="volume_24h", value=60e9, age_hours=1)
        score = self.engine.compute_score([older, newer])
        # Newer (high volume) should be used -> bullish
        assert score > 0.55

    def test_unknown_metric_defaults_to_neutral(self):
        metrics = [_make_metric(name="unknown_metric_xyz", value=12345)]
        score = self.engine.compute_score(metrics)
        assert 0.45 <= score <= 0.55

    def test_score_bounds(self):
        for value in [0, 1, 1e6, 1e18, 1e24]:
            metrics = [_make_metric(value=value)]
            score = self.engine.compute_score(metrics)
            assert 0.0 <= score <= 1.0


class TestOnChainContributingFactors:
    def setup_method(self):
        self.engine = OnChainEngine()

    def test_empty_metrics(self):
        factors = self.engine.compute_contributing_factors([])
        assert factors["score"] == 0.5
        assert factors["signal"] == "neutral"
        assert factors["metrics_count"] == 0

    def test_bullish_signal(self):
        metrics = [
            _make_metric(name="hash_rate", value=800e18),
            _make_metric(name="volume_24h", value=60e9),
        ]
        factors = self.engine.compute_contributing_factors(metrics)
        assert factors["signal"] == "bullish"
        assert factors["metrics_count"] == 2
        assert "metrics" in factors

    def test_per_metric_breakdown(self):
        metrics = [_make_metric(name="hash_rate", value=500e18)]
        factors = self.engine.compute_contributing_factors(metrics)
        assert "hash_rate" in factors["metrics"]
        hr = factors["metrics"]["hash_rate"]
        assert "value" in hr
        assert "score" in hr
        assert "source" in hr


class TestSigmoidScore:
    def test_baseline_gives_half(self):
        score = OnChainEngine._sigmoid_score(100, 100, 50)
        assert 0.49 <= score <= 0.51

    def test_above_baseline_bullish(self):
        score = OnChainEngine._sigmoid_score(200, 100, 50)
        assert score > 0.8

    def test_below_baseline_bearish(self):
        score = OnChainEngine._sigmoid_score(0, 100, 50)
        assert score < 0.2

    def test_extreme_values_clamped(self):
        score_high = OnChainEngine._sigmoid_score(1e30, 100, 50)
        score_low = OnChainEngine._sigmoid_score(-1e30, 100, 50)
        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0

    def test_zero_scale(self):
        score = OnChainEngine._sigmoid_score(100, 100, 0)
        assert score == 0.5
