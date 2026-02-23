"""Social Trend Velocity feed — detects sudden spikes in crypto mentions.

Fundamentally different from ``SentimentFeed``:

* **SentimentFeed**: "What is the sentiment?" (positive / negative / neutral)
* **SocialVelocityFeed**: "How fast are mentions accelerating?" (rate of change)

When social mentions go from 100/h to 2000/h, it precedes price moves by
15-60 minutes.  This feed tracks mention velocity across multiple free sources
and produces a 0-1 score where deviations from 0.5 indicate anomalous mention
rates.

Sources (all free, no API keys required):

* Reddit public JSON — r/cryptocurrency, r/bitcoin, r/ethtrader, r/altcoin
* CoinGecko trending — ``/api/v3/search/trending``

Follows the same singleton/BaseFeed pattern as :class:`MarketSentimentFeed`.
"""

from __future__ import annotations

import asyncio
import logging
import math
import re
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)

# ---- Data sources (all free, no auth) ----

_REDDIT_SUBREDDITS = ["cryptocurrency", "bitcoin", "ethtrader", "altcoin"]
_REDDIT_URL_TEMPLATE = "https://old.reddit.com/r/{sub}/hot.json?limit=25"
_REDDIT_FALLBACK_TEMPLATE = "https://www.reddit.com/r/{sub}/hot.json?limit=25"
_COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"

# ---- Timing constants ----

_DEFAULT_POLL_SECONDS = 150   # 2.5 minutes
_BUCKET_SIZE_SECONDS = 300    # 5-minute buckets
_LOOKBACK_SECONDS = 7200      # 2-hour baseline window
_MAX_BUCKETS = 48             # 4 hours of 5-min buckets

# ---- Scoring ----

_VELOCITY_SIGMOID_SCALE = 1.5   # sigmoid sensitivity for velocity ratio
_SPIKE_THRESHOLD = 2.0          # velocity ratio > 2x = spike detected


@dataclass
class MentionBucket:
    """A time-bucketed collection of asset mention counts."""

    timestamp: float = 0.0                             # bucket start time (unix)
    counts: dict[str, int] = field(default_factory=dict)  # asset -> count


@dataclass
class VelocitySnapshot:
    """Social velocity data for a single asset."""

    asset: str = ""
    velocity_ratio: float = 1.0       # current / baseline
    current_mentions: int = 0
    baseline_avg: float = 0.0
    spike_detected: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SocialVelocityFeed:
    """Singleton feed for social mention velocity detection.

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[SocialVelocityFeed | None] = None

    def __init__(self) -> None:
        self._buckets: deque[MentionBucket] = deque(maxlen=_MAX_BUCKETS)
        self._velocities: dict[str, VelocitySnapshot] = {}
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False
        self._last_fetch_time: float = 0
        self._poll_interval: int = _DEFAULT_POLL_SECONDS
        self._seen_post_ids: set[str] = set()

    @classmethod
    def get_instance(cls) -> SocialVelocityFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------ BaseFeed protocol ------

    @property
    def name(self) -> str:
        return "social_velocity"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic mention velocity tracking."""
        self._enabled = True
        self._is_running = True

        # Start background polling — first fetch happens after a short delay
        # so the server can begin accepting healthcheck requests immediately.
        self._fetch_task = asyncio.create_task(self._polling_loop())
        logger.info("Social velocity feed started (poll=%ds, first fetch in ~10s)", self._poll_interval)

    async def stop(self) -> None:
        """Stop periodic fetching."""
        self._is_running = False
        if self._fetch_task:
            self._fetch_task.cancel()
            try:
                await self._fetch_task
            except asyncio.CancelledError:
                pass
            self._fetch_task = None
        logger.info("Social velocity feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ------ Public query methods ------

    def get_social_velocity_score(self, pair_symbol: str) -> float | None:
        """Compute 0-1 social velocity score for a trading pair.

        Interpretation:
        * score > 0.5 → mentions are accelerating (anomalous activity)
        * score < 0.5 → mentions are decelerating (quieter than usual)
        * score ≈ 0.5 → normal mention rate

        Note: This is a *signal amplifier*, not a directional indicator.
        Direction comes from other feeds (sentiment, technical, etc.).

        Returns ``None`` if the feed is not enabled.
        """
        if not self._enabled:
            return None

        base = pair_symbol.split("/")[0]
        snapshot = self._velocities.get(base)
        if snapshot is None:
            return None

        return round(self._velocity_to_score(snapshot.velocity_ratio), 4)

    def get_velocity_data(self, asset: str) -> dict[str, Any] | None:
        """Get velocity data for a specific asset."""
        snapshot = self._velocities.get(asset)
        if snapshot is None:
            return None

        return {
            "asset": snapshot.asset,
            "velocity_ratio": round(snapshot.velocity_ratio, 4),
            "current_mentions": snapshot.current_mentions,
            "baseline_avg": round(snapshot.baseline_avg, 2),
            "spike_detected": snapshot.spike_detected,
            "score": round(self._velocity_to_score(snapshot.velocity_ratio), 4),
            "timestamp": snapshot.timestamp.isoformat(),
        }

    def get_contributing_factors(self, pair_symbol: str) -> dict[str, Any]:
        """Get detailed contributing factors for display."""
        if not self._enabled:
            return {"available": False}

        base = pair_symbol.split("/")[0]
        snapshot = self._velocities.get(base)
        if snapshot is None:
            return {"available": True, "data": False}

        score = self._velocity_to_score(snapshot.velocity_ratio)
        return {
            "available": True,
            "data": True,
            "asset": base,
            "velocity_ratio": round(snapshot.velocity_ratio, 4),
            "current_mentions": snapshot.current_mentions,
            "baseline_avg": round(snapshot.baseline_avg, 2),
            "spike_detected": snapshot.spike_detected,
            "score": round(score, 4),
            "signal": (
                "spike" if snapshot.spike_detected
                else "elevated" if snapshot.velocity_ratio > 1.5
                else "quiet" if snapshot.velocity_ratio < 0.5
                else "normal"
            ),
            "interpretation": (
                f"social spike: {snapshot.velocity_ratio:.1f}x baseline mentions"
                if snapshot.spike_detected
                else f"elevated: {snapshot.velocity_ratio:.1f}x baseline"
                if snapshot.velocity_ratio > 1.5
                else f"quiet: {snapshot.velocity_ratio:.1f}x baseline"
                if snapshot.velocity_ratio < 0.5
                else "normal mention rate"
            ),
            "buckets_available": len(self._buckets),
        }

    def get_all_scores(self) -> dict[str, float]:
        """Get social velocity scores for all tracked assets."""
        result: dict[str, float] = {}
        for asset, snapshot in self._velocities.items():
            pair = f"{asset}/USDT"
            score = self._velocity_to_score(snapshot.velocity_ratio)
            result[pair] = round(score, 4)
        return result

    def get_status(self) -> dict[str, Any]:
        """Get feed status info."""
        return {
            "enabled": self._enabled,
            "healthy": self._healthy,
            "last_fetch": (
                datetime.fromtimestamp(self._last_fetch_time, tz=timezone.utc).isoformat()
                if self._last_fetch_time > 0
                else None
            ),
            "assets_tracked": len(self._velocities),
            "buckets_available": len(self._buckets),
            "subreddits": _REDDIT_SUBREDDITS,
            "poll_interval": self._poll_interval,
            "spikes": [
                asset for asset, snap in self._velocities.items()
                if snap.spike_detected
            ],
        }

    # ------ Internal polling ------

    async def _polling_loop(self) -> None:
        # Short initial delay so the server can start accepting requests first
        try:
            await asyncio.sleep(10)
            if self._is_running:
                await self._fetch_and_count()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Social velocity feed initial fetch error")

        while self._is_running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._is_running:
                    await self._fetch_and_count()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Social velocity feed polling error")

    async def _fetch_and_count(self) -> None:
        """Fetch from all sources and record mention counts in current bucket."""
        now = time.time()
        bucket = MentionBucket(timestamp=now)

        async with httpx.AsyncClient(
            timeout=15.0,
            headers={
                "User-Agent": "cTrade:v0.1.0 (by /u/cTrade_bot)",
                "Accept": "application/json",
            },
            follow_redirects=True,
        ) as client:
            results = await asyncio.gather(
                self._fetch_reddit_mentions(client),
                self._fetch_coingecko_trending(client),
                return_exceptions=True,
            )

        for result in results:
            if isinstance(result, dict):
                for asset, count in result.items():
                    bucket.counts[asset] = bucket.counts.get(asset, 0) + count

        self._buckets.append(bucket)

        # Prune old buckets beyond lookback + one extra bucket
        cutoff = now - _LOOKBACK_SECONDS - _BUCKET_SIZE_SECONDS
        while self._buckets and self._buckets[0].timestamp < cutoff:
            self._buckets.popleft()

        # Recompute velocities for all assets
        self._compute_all_velocities()

        if bucket.counts:
            self._healthy = True
            self._last_fetch_time = now

        # Cap seen IDs to prevent unbounded memory growth
        if len(self._seen_post_ids) > 5000:
            self._seen_post_ids = set(list(self._seen_post_ids)[-2500:])

    # ------ Source fetchers ------

    async def _fetch_reddit_mentions(
        self, client: httpx.AsyncClient
    ) -> dict[str, int]:
        """Fetch hot posts from multiple crypto subreddits and count mentions."""
        counts: dict[str, int] = {}

        for sub in _REDDIT_SUBREDDITS:
            try:
                url = _REDDIT_URL_TEMPLATE.format(sub=sub)
                resp = await client.get(url)

                # Fallback to www.reddit.com if old.reddit.com fails
                if resp.status_code == 403:
                    url = _REDDIT_FALLBACK_TEMPLATE.format(sub=sub)
                    resp = await client.get(url)

                resp.raise_for_status()
                data = resp.json()

                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    post_data = post.get("data", {})
                    post_id = post_data.get("id", "")

                    # Deduplicate — only count new posts
                    if post_id in self._seen_post_ids:
                        continue
                    self._seen_post_ids.add(post_id)

                    title = post_data.get("title", "")
                    flair = post_data.get("link_flair_text", "") or ""
                    text = f"{title} {flair}".lower()

                    # Extract mentioned assets
                    for asset in self._extract_assets(text):
                        counts[asset] = counts.get(asset, 0) + 1

            except Exception:
                logger.debug("Reddit fetch failed for r/%s", sub)

        return counts

    async def _fetch_coingecko_trending(
        self, client: httpx.AsyncClient
    ) -> dict[str, int]:
        """Fetch CoinGecko trending coins and count as mentions."""
        counts: dict[str, int] = {}

        try:
            resp = await client.get(_COINGECKO_TRENDING_URL)
            resp.raise_for_status()
            data = resp.json()

            coins = data.get("coins", [])
            for entry in coins:
                item = entry.get("item", {})
                symbol = item.get("symbol", "").upper()
                if symbol:
                    # Trending = 2 mentions (boosted — trending is a signal)
                    counts[symbol] = counts.get(symbol, 0) + 2

        except Exception:
            logger.debug("CoinGecko trending fetch failed")

        return counts

    # ------ Velocity computation ------

    def _compute_all_velocities(self) -> None:
        """Recompute velocity ratios for all seen assets."""
        # Collect all assets mentioned across buckets
        all_assets: set[str] = set()
        for bucket in self._buckets:
            all_assets.update(bucket.counts.keys())

        for asset in all_assets:
            ratio = self._compute_velocity_ratio(asset)
            current = self._get_current_mentions(asset)
            baseline = self._get_baseline_avg(asset)

            self._velocities[asset] = VelocitySnapshot(
                asset=asset,
                velocity_ratio=ratio,
                current_mentions=current,
                baseline_avg=baseline,
                spike_detected=ratio >= _SPIKE_THRESHOLD,
            )

    def _compute_velocity_ratio(self, asset: str) -> float:
        """Compute velocity ratio = current bucket rate / baseline rate."""
        now = time.time()

        # Current: mentions in most recent bucket
        current = self._get_current_mentions(asset)

        # Baseline: average per-bucket over lookback (excluding most recent)
        baseline = self._get_baseline_avg(asset)

        if baseline < 0.5:
            return 1.0  # baseline too low to be meaningful

        return current / baseline

    def _get_current_mentions(self, asset: str) -> int:
        """Get mention count in the most recent bucket."""
        if not self._buckets:
            return 0
        return self._buckets[-1].counts.get(asset, 0)

    def _get_baseline_avg(self, asset: str) -> float:
        """Get average mentions per bucket over baseline window (excluding current)."""
        if len(self._buckets) < 2:
            return 0.0

        now = time.time()
        baseline_buckets = [
            b for b in list(self._buckets)[:-1]  # exclude most recent
            if now - b.timestamp < _LOOKBACK_SECONDS
        ]

        if not baseline_buckets:
            return 0.0

        total = sum(b.counts.get(asset, 0) for b in baseline_buckets)
        return total / len(baseline_buckets)

    # ------ Scoring ------

    @staticmethod
    def _velocity_to_score(velocity_ratio: float) -> float:
        """Convert velocity ratio to a 0-1 score.

        velocity_ratio = 1.0 → normal mention rate → neutral → 0.5
        velocity_ratio = 2.0 → double the baseline → mild signal → ~0.6
        velocity_ratio = 5.0+ → viral spike → strong signal → ~0.8
        velocity_ratio < 0.5 → decreasing mentions → slight contrarian → ~0.45

        This is purely a "signal amplifier" — deviates from 0.5 based on
        how anomalous the mention rate is.  Direction is determined by
        other feeds (sentiment, technical, etc.).
        """
        if velocity_ratio <= 0:
            return 0.5

        # Log-scale the ratio for symmetry (ratio=2 same distance as ratio=0.5)
        log_ratio = math.log(velocity_ratio)
        # Map to 0-1 via sigmoid, centered at ratio=1 (log=0)
        score = 1.0 / (1.0 + math.exp(-log_ratio * _VELOCITY_SIGMOID_SCALE))
        return max(0.0, min(1.0, score))

    # ------ Asset extraction ------

    @staticmethod
    def _extract_assets(text: str) -> list[str]:
        """Extract asset symbols from text using the shared alias map.

        Reuses ``ASSET_ALIASES`` from the sentiment feed for consistency.
        """
        from ctrade.feeds.sentiment import ASSET_ALIASES

        found: set[str] = set()
        text_lower = text.lower()

        for alias, symbol in ASSET_ALIASES.items():
            # Word boundary matching to avoid false positives
            if re.search(rf"\b{re.escape(alias)}\b", text_lower):
                found.add(symbol)

        # Also check for uppercase tickers directly (BTC, ETH, SOL, etc.)
        all_symbols = set(ASSET_ALIASES.values())
        for word in text.upper().split():
            # Strip punctuation
            clean = re.sub(r"[^\w]", "", word)
            if clean in all_symbols:
                found.add(clean)

        return list(found)
