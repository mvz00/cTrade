"""On-chain composite score calculator.

Aggregates on-chain metrics (hash rate, tx count, volume, etc.) into a
single 0-1 score per asset using sigmoid normalization.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ctrade.core.models import OnChainMetric

# Metric normalization parameters (name -> (baseline, scale))
# baseline = typical value where score = 0.5
# scale = how much change yields a significant score shift
_METRIC_PARAMS: dict[str, tuple[float, float]] = {
    "hash_rate":     (500e18, 100e18),     # ~500 EH/s baseline for BTC
    "mempool_size":  (5000, 3000),          # ~5k tx in mempool
    "tx_count_24h":  (300000, 100000),      # ~300k daily BTC tx
    "volume_24h":    (30e9, 15e9),          # ~$30B daily volume
    "market_cap":    (1e12, 500e9),         # ~$1T market cap
    "circulating_supply_pct": (0.85, 0.10), # 85% typical
}

# Weights for each metric in the composite score
_METRIC_WEIGHTS: dict[str, float] = {
    "hash_rate":     0.25,
    "tx_count_24h":  0.25,
    "volume_24h":    0.30,
    "mempool_size":  0.10,
    "market_cap":    0.10,
}


class OnChainEngine:
    """Computes composite on-chain scores from metric data points.

    Scoring strategy:
    * Normalize each metric to 0-1 using sigmoid
    * Weight metrics by importance
    * Produce a single 0-1 score per asset
    """

    def compute_score(
        self,
        metrics: list[OnChainMetric],
        max_age_hours: int = 24,
    ) -> float:
        """Compute weighted on-chain score from metrics.

        Args:
            metrics: On-chain metric data points for a single asset.
            max_age_hours: Ignore metrics older than this (hours).

        Returns:
            Composite score in [0, 1].  Returns 0.5 (neutral) if no data.
        """
        if not metrics:
            return 0.5

        now = datetime.now(timezone.utc)
        latest: dict[str, OnChainMetric] = {}

        # Keep only the most recent value per metric name
        for m in metrics:
            age_hours = (now - m.timestamp).total_seconds() / 3600.0
            if age_hours > max_age_hours or age_hours < 0:
                continue
            existing = latest.get(m.metric_name)
            if existing is None or m.timestamp > existing.timestamp:
                latest[m.metric_name] = m

        if not latest:
            return 0.5

        total_weight = 0.0
        weighted_sum = 0.0

        for name, metric in latest.items():
            weight = _METRIC_WEIGHTS.get(name, 0.15)
            value = float(metric.metric_value)

            params = _METRIC_PARAMS.get(name)
            if params:
                baseline, scale = params
                score = self._sigmoid_score(value, baseline, scale)
            else:
                # Unknown metric — just use 0.5
                score = 0.5

            weighted_sum += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.5

        return round(max(0.0, min(1.0, weighted_sum / total_weight)), 4)

    def compute_contributing_factors(
        self,
        metrics: list[OnChainMetric],
        max_age_hours: int = 24,
    ) -> dict[str, Any]:
        """Build contributing-factors breakdown for the Signal.

        Returns a dict suitable for ``Signal.contributing_factors["onchain"]``.
        """
        if not metrics:
            return {"score": 0.5, "signal": "neutral", "metrics_count": 0}

        now = datetime.now(timezone.utc)
        latest: dict[str, OnChainMetric] = {}

        for m in metrics:
            age_hours = (now - m.timestamp).total_seconds() / 3600.0
            if age_hours > max_age_hours or age_hours < 0:
                continue
            existing = latest.get(m.metric_name)
            if existing is None or m.timestamp > existing.timestamp:
                latest[m.metric_name] = m

        # Per-metric scores
        metric_scores: dict[str, dict[str, Any]] = {}
        for name, metric in latest.items():
            value = float(metric.metric_value)
            params = _METRIC_PARAMS.get(name)
            if params:
                baseline, scale = params
                score = self._sigmoid_score(value, baseline, scale)
            else:
                score = 0.5

            metric_scores[name] = {
                "value": value,
                "score": round(score, 4),
                "source": metric.source,
            }

        composite = self.compute_score(metrics, max_age_hours)

        if composite > 0.6:
            signal = "bullish"
        elif composite < 0.4:
            signal = "bearish"
        else:
            signal = "neutral"

        return {
            "score": composite,
            "signal": signal,
            "metrics_count": len(latest),
            "metrics": metric_scores,
        }

    @staticmethod
    def _sigmoid_score(value: float, baseline: float, scale: float) -> float:
        """Normalize a raw value to 0-1 using a sigmoid centered on *baseline*.

        score = sigmoid((value - baseline) / scale)

        * value == baseline → 0.5
        * value >> baseline → approaches 1.0
        * value << baseline → approaches 0.0
        """
        if scale <= 0:
            return 0.5
        x = (value - baseline) / scale
        # Clamp to prevent overflow
        x = max(-10.0, min(10.0, x))
        return 1.0 / (1.0 + math.exp(-x))
