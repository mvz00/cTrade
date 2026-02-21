"""Sentiment composite score calculator.

Aggregates classified :class:`SentimentDataPoint` instances into a single
0-1 score per asset using time-weighted averaging across sources.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from ctrade.core.models import SentimentDataPoint

# Source weights for composite scoring
_SOURCE_WEIGHTS: dict[str, float] = {
    "cryptocompare": 0.40,
    "reddit": 0.35,
    "coingecko": 0.25,
}

# Time-decay half-life in hours
_HALF_LIFE_HOURS = 6.0


class SentimentEngine:
    """Computes composite sentiment scores from classified data points.

    Scoring strategy:
    * Weight recent items higher than older ones (exponential time decay)
    * Weight sources differently (news > social > trending)
    * Produce a single 0-1 score per asset
    """

    def compute_score(
        self,
        data_points: list[SentimentDataPoint],
        max_age_hours: int = 24,
    ) -> float:
        """Compute time-weighted average sentiment score.

        Args:
            data_points: Classified sentiment data points for a single asset.
            max_age_hours: Ignore data points older than this (hours).

        Returns:
            Composite score in [0, 1].  Returns 0.5 (neutral) if no data.
        """
        if not data_points:
            return 0.5

        now = datetime.now(timezone.utc)
        total_weight = 0.0
        weighted_sum = 0.0

        for dp in data_points:
            age_hours = (now - dp.timestamp).total_seconds() / 3600.0
            if age_hours > max_age_hours or age_hours < 0:
                continue

            # Time decay: weight = 2^(-age / half_life)
            time_weight = math.pow(2, -age_hours / _HALF_LIFE_HOURS)

            # Source weight
            source_weight = _SOURCE_WEIGHTS.get(dp.source, 0.25)

            combined_weight = time_weight * source_weight
            weighted_sum += dp.score * combined_weight
            total_weight += combined_weight

        if total_weight == 0:
            return 0.5

        return round(max(0.0, min(1.0, weighted_sum / total_weight)), 4)

    def compute_contributing_factors(
        self,
        data_points: list[SentimentDataPoint],
        max_age_hours: int = 24,
    ) -> dict[str, Any]:
        """Build contributing-factors breakdown for the Signal.

        Returns a dict suitable for ``Signal.contributing_factors["sentiment"]``.
        """
        if not data_points:
            return {"score": 0.5, "signal": "neutral", "data_points": 0}

        now = datetime.now(timezone.utc)

        # Group by source
        source_scores: dict[str, list[float]] = {}
        source_counts: dict[str, int] = {}
        total_used = 0

        for dp in data_points:
            age_hours = (now - dp.timestamp).total_seconds() / 3600.0
            if age_hours > max_age_hours or age_hours < 0:
                continue

            source_scores.setdefault(dp.source, []).append(dp.score)
            source_counts[dp.source] = source_counts.get(dp.source, 0) + 1
            total_used += 1

        # Average per source
        source_avgs = {}
        for src, scores in source_scores.items():
            source_avgs[src] = round(sum(scores) / len(scores), 4) if scores else 0.5

        composite = self.compute_score(data_points, max_age_hours)

        if composite > 0.6:
            signal = "bullish"
        elif composite < 0.4:
            signal = "bearish"
        else:
            signal = "neutral"

        return {
            "score": composite,
            "signal": signal,
            "data_points": total_used,
            "sources": source_avgs,
            "source_counts": source_counts,
        }
