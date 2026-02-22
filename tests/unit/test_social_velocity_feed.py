"""Tests for the social velocity feed (mention rate-of-change scoring)."""

from __future__ import annotations

import time

import pytest

from ctrade.feeds.social_velocity import (
    MentionBucket,
    SocialVelocityFeed,
    VelocitySnapshot,
    _SPIKE_THRESHOLD,
    _VELOCITY_SIGMOID_SCALE,
)


@pytest.fixture(autouse=True)
def reset_feed():
    """Reset the singleton between tests."""
    SocialVelocityFeed.reset()
    yield
    SocialVelocityFeed.reset()


# ---------------------------------------------------------------------------
# Singleton tests
# ---------------------------------------------------------------------------

class TestSocialVelocityFeedSingleton:
    def test_get_instance(self):
        a = SocialVelocityFeed.get_instance()
        b = SocialVelocityFeed.get_instance()
        assert a is b

    def test_reset(self):
        a = SocialVelocityFeed.get_instance()
        SocialVelocityFeed.reset()
        b = SocialVelocityFeed.get_instance()
        assert a is not b

    def test_initial_state(self):
        feed = SocialVelocityFeed.get_instance()
        assert feed.name == "social_velocity"
        assert not feed.is_enabled


# ---------------------------------------------------------------------------
# Score queries when disabled / empty
# ---------------------------------------------------------------------------

class TestSocialVelocityQueries:
    def test_get_score_when_disabled(self):
        feed = SocialVelocityFeed.get_instance()
        assert feed.get_social_velocity_score("BTC/USDT") is None

    def test_get_score_when_enabled_but_no_data(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        assert feed.get_social_velocity_score("BTC/USDT") is None

    def test_get_velocity_data_when_no_data(self):
        feed = SocialVelocityFeed.get_instance()
        assert feed.get_velocity_data("BTC") is None

    def test_get_all_scores_empty(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        assert feed.get_all_scores() == {}


# ---------------------------------------------------------------------------
# Scoring function: _velocity_to_score
# ---------------------------------------------------------------------------

class TestVelocityToScore:
    """Velocity ratio mapped to 0-1 score via log-sigmoid."""

    def test_zero_ratio_returns_neutral(self):
        """velocity_ratio <= 0 should return 0.5 (guard clause)."""
        assert SocialVelocityFeed._velocity_to_score(0) == 0.5

    def test_negative_ratio_returns_neutral(self):
        assert SocialVelocityFeed._velocity_to_score(-1.0) == 0.5

    def test_normal_rate_is_neutral(self):
        """velocity_ratio = 1.0 (baseline rate) should map to 0.5."""
        score = SocialVelocityFeed._velocity_to_score(1.0)
        assert abs(score - 0.5) < 0.001

    def test_accelerating_above_neutral(self):
        """velocity_ratio = 2.0 (double baseline) should score > 0.5."""
        score = SocialVelocityFeed._velocity_to_score(2.0)
        assert score > 0.5

    def test_strong_spike_above_neutral(self):
        """velocity_ratio = 5.0 (viral spike) should score > 0.6."""
        score = SocialVelocityFeed._velocity_to_score(5.0)
        assert score > 0.6

    def test_decelerating_below_neutral(self):
        """velocity_ratio = 0.5 (half baseline) should score < 0.5."""
        score = SocialVelocityFeed._velocity_to_score(0.5)
        assert score < 0.5

    def test_monotonicity(self):
        """Higher velocity ratio should always produce a higher score."""
        ratios = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]
        scores = [SocialVelocityFeed._velocity_to_score(r) for r in ratios]
        for i in range(len(scores) - 1):
            assert scores[i] < scores[i + 1], (
                f"score({ratios[i]})={scores[i]} >= score({ratios[i+1]})={scores[i+1]}"
            )

    def test_bounded_for_extreme_values(self):
        """Score is always clamped to [0, 1] regardless of input."""
        for ratio in [0.001, 0.01, 0.1, 1.0, 10.0, 100.0, 10_000.0]:
            score = SocialVelocityFeed._velocity_to_score(ratio)
            assert 0.0 <= score <= 1.0, f"ratio={ratio} produced score={score}"

    def test_symmetry_around_1(self):
        """Doubling and halving should deviate equally from 0.5 (log-sigmoid property)."""
        score_double = SocialVelocityFeed._velocity_to_score(2.0)
        score_half = SocialVelocityFeed._velocity_to_score(0.5)
        deviation_up = score_double - 0.5
        deviation_down = 0.5 - score_half
        assert abs(deviation_up - deviation_down) < 0.001


# ---------------------------------------------------------------------------
# Velocity computation with injected buckets
# ---------------------------------------------------------------------------

class TestVelocityComputation:
    """Inject MentionBucket objects and verify velocity computation."""

    def _make_feed_with_buckets(
        self, buckets: list[MentionBucket]
    ) -> SocialVelocityFeed:
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        for b in buckets:
            feed._buckets.append(b)
        return feed

    def test_single_bucket_baseline_too_low(self):
        """With only one bucket, baseline is 0 so ratio defaults to 1.0."""
        now = time.time()
        feed = self._make_feed_with_buckets([
            MentionBucket(timestamp=now, counts={"BTC": 10}),
        ])
        feed._compute_all_velocities()

        snap = feed._velocities.get("BTC")
        assert snap is not None
        assert snap.velocity_ratio == 1.0  # baseline < 0.5 → default
        assert not snap.spike_detected

    def test_steady_rate_produces_ratio_near_one(self):
        """Uniform mentions across buckets should give ratio near 1.0."""
        now = time.time()
        buckets = [
            MentionBucket(timestamp=now - 600, counts={"ETH": 5}),
            MentionBucket(timestamp=now - 300, counts={"ETH": 5}),
            MentionBucket(timestamp=now, counts={"ETH": 5}),
        ]
        feed = self._make_feed_with_buckets(buckets)
        feed._compute_all_velocities()

        snap = feed._velocities["ETH"]
        assert abs(snap.velocity_ratio - 1.0) < 0.01
        assert not snap.spike_detected

    def test_spike_detected_when_current_exceeds_threshold(self):
        """A large spike in the latest bucket should trigger spike_detected."""
        now = time.time()
        buckets = [
            MentionBucket(timestamp=now - 900, counts={"SOL": 5}),
            MentionBucket(timestamp=now - 600, counts={"SOL": 5}),
            MentionBucket(timestamp=now - 300, counts={"SOL": 5}),
            MentionBucket(timestamp=now, counts={"SOL": 50}),  # 10x spike
        ]
        feed = self._make_feed_with_buckets(buckets)
        feed._compute_all_velocities()

        snap = feed._velocities["SOL"]
        assert snap.velocity_ratio >= _SPIKE_THRESHOLD
        assert snap.spike_detected

    def test_score_reflects_velocity_ratio(self):
        """After computation, querying the score should reflect the ratio."""
        now = time.time()
        buckets = [
            MentionBucket(timestamp=now - 600, counts={"BTC": 5}),
            MentionBucket(timestamp=now - 300, counts={"BTC": 5}),
            MentionBucket(timestamp=now, counts={"BTC": 20}),  # 4x spike
        ]
        feed = self._make_feed_with_buckets(buckets)
        feed._compute_all_velocities()

        score = feed.get_social_velocity_score("BTC/USDT")
        assert score is not None
        assert score > 0.5  # accelerating mentions

    def test_decelerating_score_below_neutral(self):
        """When current bucket has fewer mentions than baseline, score < 0.5."""
        now = time.time()
        buckets = [
            MentionBucket(timestamp=now - 600, counts={"ADA": 20}),
            MentionBucket(timestamp=now - 300, counts={"ADA": 20}),
            MentionBucket(timestamp=now, counts={"ADA": 2}),  # 0.1x drop
        ]
        feed = self._make_feed_with_buckets(buckets)
        feed._compute_all_velocities()

        score = feed.get_social_velocity_score("ADA/USDT")
        assert score is not None
        assert score < 0.5  # decelerating mentions

    def test_multiple_assets_tracked(self):
        """Different assets in the same buckets are tracked independently."""
        now = time.time()
        buckets = [
            MentionBucket(timestamp=now - 300, counts={"BTC": 10, "ETH": 5}),
            MentionBucket(timestamp=now, counts={"BTC": 10, "ETH": 25}),
        ]
        feed = self._make_feed_with_buckets(buckets)
        feed._compute_all_velocities()

        assert "BTC" in feed._velocities
        assert "ETH" in feed._velocities
        # ETH spiked 5x, BTC stayed flat
        assert feed._velocities["ETH"].velocity_ratio > feed._velocities["BTC"].velocity_ratio


# ---------------------------------------------------------------------------
# Asset extraction
# ---------------------------------------------------------------------------

class TestExtractAssets:
    """Test _extract_assets text parsing."""

    def test_bitcoin_alias(self):
        assets = SocialVelocityFeed._extract_assets("bitcoin is pumping today")
        assert "BTC" in assets

    def test_ethereum_alias(self):
        assets = SocialVelocityFeed._extract_assets("I just bought some ethereum")
        assert "ETH" in assets

    def test_uppercase_ticker(self):
        assets = SocialVelocityFeed._extract_assets("SOL is the future")
        assert "SOL" in assets

    def test_btc_ticker(self):
        assets = SocialVelocityFeed._extract_assets("BTC hitting new highs")
        assert "BTC" in assets

    def test_multiple_assets(self):
        assets = SocialVelocityFeed._extract_assets("bitcoin and ethereum are mooning")
        assert "BTC" in assets
        assert "ETH" in assets

    def test_no_false_positives_short_words(self):
        """Common short words should not trigger false asset matches."""
        assets = SocialVelocityFeed._extract_assets("the cat sat on a mat")
        assert len(assets) == 0

    def test_case_insensitive_alias(self):
        assets = SocialVelocityFeed._extract_assets("BITCOIN is trending")
        assert "BTC" in assets

    def test_solana_alias(self):
        assets = SocialVelocityFeed._extract_assets("solana network upgrade")
        assert "SOL" in assets


# ---------------------------------------------------------------------------
# Contributing factors
# ---------------------------------------------------------------------------

class TestContributingFactors:
    def test_factors_when_disabled(self):
        feed = SocialVelocityFeed.get_instance()
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors == {"available": False}

    def test_factors_when_no_data(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["available"] is True
        assert factors["data"] is False

    def test_factors_structure_with_data(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC",
            velocity_ratio=3.0,
            current_mentions=30,
            baseline_avg=10.0,
            spike_detected=True,
        )

        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["available"] is True
        assert factors["data"] is True
        assert factors["asset"] == "BTC"
        assert factors["velocity_ratio"] == 3.0
        assert factors["current_mentions"] == 30
        assert factors["baseline_avg"] == 10.0
        assert factors["spike_detected"] is True
        assert "score" in factors
        assert "signal" in factors
        assert "interpretation" in factors
        assert "buckets_available" in factors

    def test_signal_label_spike(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=3.0, spike_detected=True,
        )
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["signal"] == "spike"

    def test_signal_label_elevated(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=1.6, spike_detected=False,
        )
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["signal"] == "elevated"

    def test_signal_label_quiet(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=0.3, spike_detected=False,
        )
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["signal"] == "quiet"

    def test_signal_label_normal(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=1.0, spike_detected=False,
        )
        factors = feed.get_contributing_factors("BTC/USDT")
        assert factors["signal"] == "normal"


# ---------------------------------------------------------------------------
# get_all_scores
# ---------------------------------------------------------------------------

class TestGetAllScores:
    def test_returns_scores_for_all_tracked(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=2.0,
        )
        feed._velocities["ETH"] = VelocitySnapshot(
            asset="ETH", velocity_ratio=0.5,
        )

        scores = feed.get_all_scores()
        assert "BTC/USDT" in scores
        assert "ETH/USDT" in scores
        assert 0.0 <= scores["BTC/USDT"] <= 1.0
        assert 0.0 <= scores["ETH/USDT"] <= 1.0

    def test_scores_reflect_velocity(self):
        """Asset with higher velocity should have higher score."""
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=5.0,
        )
        feed._velocities["ETH"] = VelocitySnapshot(
            asset="ETH", velocity_ratio=1.0,
        )

        scores = feed.get_all_scores()
        assert scores["BTC/USDT"] > scores["ETH/USDT"]


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus:
    def test_status_structure(self):
        feed = SocialVelocityFeed.get_instance()
        status = feed.get_status()
        assert "enabled" in status
        assert "healthy" in status
        assert "last_fetch" in status
        assert "assets_tracked" in status
        assert "buckets_available" in status
        assert "subreddits" in status
        assert "poll_interval" in status
        assert "spikes" in status

    def test_status_reflects_state(self):
        feed = SocialVelocityFeed.get_instance()
        feed._enabled = True
        feed._healthy = True
        feed._velocities["BTC"] = VelocitySnapshot(
            asset="BTC", velocity_ratio=3.0, spike_detected=True,
        )
        feed._velocities["ETH"] = VelocitySnapshot(
            asset="ETH", velocity_ratio=1.0, spike_detected=False,
        )

        status = feed.get_status()
        assert status["enabled"] is True
        assert status["healthy"] is True
        assert status["assets_tracked"] == 2
        assert "BTC" in status["spikes"]
        assert "ETH" not in status["spikes"]

    def test_last_fetch_none_when_no_fetch(self):
        feed = SocialVelocityFeed.get_instance()
        status = feed.get_status()
        assert status["last_fetch"] is None
