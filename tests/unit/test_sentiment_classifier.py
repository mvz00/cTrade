"""Tests for the sentiment classifier (keyword fallback mode)."""

from __future__ import annotations

import pytest

from ctrade.analysis.sentiment.classifier import SentimentClassifier
from ctrade.core.enums import SentimentLabel


@pytest.fixture(autouse=True)
def reset_classifier():
    """Reset the singleton between tests."""
    SentimentClassifier.reset()
    yield
    SentimentClassifier.reset()


def _get_fallback_classifier() -> SentimentClassifier:
    """Get a classifier in keyword fallback mode (no FinBERT)."""
    clf = SentimentClassifier.get_instance()
    # Force fallback mode without loading FinBERT
    clf._loaded = True
    clf._using_fallback = True
    return clf


class TestSentimentClassifierSingleton:
    def test_get_instance_returns_same(self):
        a = SentimentClassifier.get_instance()
        b = SentimentClassifier.get_instance()
        assert a is b

    def test_reset_creates_new_instance(self):
        a = SentimentClassifier.get_instance()
        SentimentClassifier.reset()
        b = SentimentClassifier.get_instance()
        assert a is not b

    def test_initial_state(self):
        clf = SentimentClassifier.get_instance()
        assert not clf.is_loaded
        assert not clf.using_fallback


class TestKeywordFallback:
    def test_bullish_text(self):
        clf = _get_fallback_classifier()
        label, score = clf.classify("Bitcoin is surging and rally continues, bullish breakout expected")
        assert label == SentimentLabel.POSITIVE
        assert score > 0.5

    def test_bearish_text(self):
        clf = _get_fallback_classifier()
        label, score = clf.classify("Market crash, massive sell-off and liquidation fear")
        assert label == SentimentLabel.NEGATIVE
        assert score < 0.5

    def test_neutral_text(self):
        clf = _get_fallback_classifier()
        label, score = clf.classify("The quick brown fox jumps over the lazy dog")
        assert label == SentimentLabel.NEUTRAL
        assert score == 0.5

    def test_mixed_text(self):
        clf = _get_fallback_classifier()
        label, score = clf.classify("Rally but also fear of crash")
        # Has both bullish and bearish keywords — should be somewhere near 0.5
        assert 0.2 <= score <= 0.8

    def test_empty_text(self):
        clf = _get_fallback_classifier()
        label, score = clf.classify("")
        assert label == SentimentLabel.NEUTRAL
        assert score == 0.5

    def test_score_bounds(self):
        clf = _get_fallback_classifier()
        for text in [
            "bull surge rally moon pump gain rise breakout",
            "crash dump bear sell-off plunge decline tank",
            "neutral boring text nothing interesting",
        ]:
            label, score = clf.classify(text)
            assert 0.0 <= score <= 1.0

    def test_classify_batch(self):
        clf = _get_fallback_classifier()
        results = clf.classify_batch([
            "Bitcoin rally to the moon",
            "Market crash imminent",
            "Regular news article",
        ])
        assert len(results) == 3
        assert results[0][0] == SentimentLabel.POSITIVE
        assert results[1][0] == SentimentLabel.NEGATIVE
        assert all(0.0 <= r[1] <= 1.0 for r in results)

    def test_classify_batch_empty(self):
        clf = _get_fallback_classifier()
        assert clf.classify_batch([]) == []

    def test_model_name_in_fallback(self):
        clf = _get_fallback_classifier()
        assert clf.model_name == "keyword-fallback"


class TestFinBERTMapping:
    """Test the static _map_finbert_result method."""

    def test_positive_result(self):
        label, score = SentimentClassifier._map_finbert_result(
            {"label": "positive", "score": 0.9}
        )
        assert label == SentimentLabel.POSITIVE
        assert 0.9 <= score <= 1.0

    def test_negative_result(self):
        label, score = SentimentClassifier._map_finbert_result(
            {"label": "negative", "score": 0.8}
        )
        assert label == SentimentLabel.NEGATIVE
        assert 0.0 <= score <= 0.2

    def test_neutral_result(self):
        label, score = SentimentClassifier._map_finbert_result(
            {"label": "neutral", "score": 0.7}
        )
        assert label == SentimentLabel.NEUTRAL
        assert score == 0.5

    def test_score_clamping(self):
        label, score = SentimentClassifier._map_finbert_result(
            {"label": "positive", "score": 1.0}
        )
        assert 0.0 <= score <= 1.0
