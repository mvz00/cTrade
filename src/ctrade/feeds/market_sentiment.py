"""Market sentiment feed — liquidations, long/short ratio, and Fear & Greed.

Phase 2 intelligence feeds — all free, no API key required:

* **Liquidation Data** — Cascading liquidations cause 5-15% moves in minutes.
  After a $10M+ flush, reversal follows within 1-4h.  Fetched from Binance
  Futures public API (aggregated taker buy/sell volume as liquidation proxy).

* **Long/Short Ratio** — When 75%+ of accounts are long, the crowd is usually
  wrong (contrarian).  Fetched from Binance globalLongShortAccountRatio.

* **Fear & Greed Index** — Regime filter: extreme fear (0-25) = be more
  aggressive buying; extreme greed (75-100) = be cautious selling.  Fetched
  from Alternative.me (no key needed, updates daily).

These three indicators form a *market regime* score (0-1) that modifies the
orchestrator's confidence thresholds — effectively a multiplier on existing
signal quality rather than a separate signal dimension.

Follows the same singleton/BaseFeed pattern as :class:`CoinMarketCapFeed`.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)

# ---- API endpoints (all free, no auth required) ----

_FEAR_GREED_URL = "https://api.alternative.me/fng/"

# Binance Futures public endpoints (no API key needed)
_BINANCE_LONG_SHORT_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
_BINANCE_TAKER_VOLUME_URL = "https://fapi.binance.com/futures/data/takerlongshortRatio"
_BINANCE_TOP_TRADER_URL = "https://fapi.binance.com/futures/data/topLongShortAccountRatio"

# Default poll intervals
_FEAR_GREED_POLL_SECONDS = 3600   # Updates daily, check hourly
_BINANCE_POLL_SECONDS = 300       # 5 minutes for L/S ratio and liquidations

# Top symbols to track on Binance (no USDT suffix for query)
_TRACKED_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "DOTUSDT", "AVAXUSDT", "LINKUSDT",
    "ATOMUSDT", "NEARUSDT", "SUIUSDT", "APTUSDT",
]

# Symbol mapping: Binance futures format -> our pair format
_BINANCE_TO_PAIR: dict[str, str] = {
    s: f"{s.replace('USDT', '')}/USDT" for s in _TRACKED_SYMBOLS
}


@dataclass
class FearGreedData:
    """Current Fear & Greed Index reading."""

    value: int = 50           # 0-100
    classification: str = "Neutral"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LongShortData:
    """Long/short ratio for a symbol."""

    symbol: str = ""
    long_short_ratio: float = 1.0   # > 1 means more longs
    long_pct: float = 0.5           # 0-1
    short_pct: float = 0.5          # 0-1
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LiquidationData:
    """Taker buy/sell volume data (liquidation proxy) for a symbol."""

    symbol: str = ""
    buy_sell_ratio: float = 1.0     # taker buy / sell ratio
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class MarketSentimentFeed:
    """Singleton feed for market-wide sentiment: Fear & Greed, L/S ratio, liquidations.

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[MarketSentimentFeed | None] = None

    def __init__(self) -> None:
        self._fear_greed: FearGreedData = FearGreedData()
        self._long_short: dict[str, LongShortData] = {}     # symbol -> latest
        self._liquidations: dict[str, LiquidationData] = {} # symbol -> latest
        self._top_trader_ls: dict[str, LongShortData] = {}  # top trader L/S
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False
        self._last_fetch_time: float = 0
        self._last_fg_fetch_time: float = 0
        self._poll_interval: int = _BINANCE_POLL_SECONDS

    @classmethod
    def get_instance(cls) -> MarketSentimentFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------ BaseFeed protocol ------

    @property
    def name(self) -> str:
        return "market_sentiment"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic fetching.  Always enabled (all free APIs, no key needed)."""
        self._enabled = True
        self._is_running = True

        # Start background polling — first fetch happens after a short delay
        # so the server can begin accepting healthcheck requests immediately.
        self._fetch_task = asyncio.create_task(self._polling_loop())
        logger.info("Market sentiment feed started (poll interval=%ds, first fetch in ~10s)", self._poll_interval)

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
        logger.info("Market sentiment feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ------ Public query methods ------

    def get_market_sentiment_score(self, pair_symbol: str) -> float | None:
        """Compute a composite 0-1 market sentiment score for a trading pair.

        Blends three signals:
        * Fear & Greed Index (weight 0.35) — contrarian regime filter
        * Long/Short Ratio (weight 0.40) — contrarian crowd positioning
        * Taker Volume Ratio (weight 0.25) — liquidation/momentum proxy

        Interpretation:
        * score > 0.5 → market conditions favor buying (fear, shorts overcrowded)
        * score < 0.5 → market conditions favor caution (greed, longs overcrowded)
        * score = 0.5 → neutral market conditions

        Returns ``None`` if the feed is not enabled.
        """
        if not self._enabled:
            return None

        scores: dict[str, float] = {}
        weights: dict[str, float] = {}

        # 1. Fear & Greed (contrarian: fear = buy opportunity)
        fg_score = self._fear_greed_to_score(self._fear_greed.value)
        scores["fear_greed"] = fg_score
        weights["fear_greed"] = 0.35

        # 2. Long/Short Ratio (contrarian: overcrowded longs = bearish)
        base_symbol = pair_symbol.split("/")[0]
        binance_symbol = f"{base_symbol}USDT"
        ls_data = self._long_short.get(binance_symbol)
        if ls_data is not None:
            scores["long_short"] = self._long_short_to_score(ls_data.long_pct)
            weights["long_short"] = 0.40
        # If no per-symbol data, try BTC as market proxy
        elif self._long_short.get("BTCUSDT") is not None:
            btc_ls = self._long_short["BTCUSDT"]
            scores["long_short"] = self._long_short_to_score(btc_ls.long_pct)
            weights["long_short"] = 0.30  # lower weight for proxy

        # 3. Taker Volume Ratio (momentum/liquidation proxy)
        liq_data = self._liquidations.get(binance_symbol)
        if liq_data is not None:
            scores["taker_volume"] = self._taker_volume_to_score(liq_data.buy_sell_ratio)
            weights["taker_volume"] = 0.25

        if not scores:
            return None

        # Normalize weights
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return None

        composite = sum(
            scores[k] * (weights[k] / total_weight)
            for k in scores
        )
        return round(max(0.0, min(1.0, composite)), 4)

    def get_fear_greed(self) -> dict[str, Any]:
        """Get current Fear & Greed Index reading."""
        return {
            "value": self._fear_greed.value,
            "classification": self._fear_greed.classification,
            "score": round(self._fear_greed_to_score(self._fear_greed.value), 4),
            "timestamp": self._fear_greed.timestamp.isoformat(),
        }

    def get_long_short_ratio(self, pair_symbol: str) -> dict[str, Any] | None:
        """Get long/short ratio for a specific symbol."""
        base = pair_symbol.split("/")[0]
        binance_sym = f"{base}USDT"
        ls = self._long_short.get(binance_sym)
        if ls is None:
            return None
        return {
            "symbol": ls.symbol,
            "long_short_ratio": round(ls.long_short_ratio, 4),
            "long_pct": round(ls.long_pct, 4),
            "short_pct": round(ls.short_pct, 4),
            "score": round(self._long_short_to_score(ls.long_pct), 4),
            "signal": (
                "bearish" if ls.long_pct > 0.65
                else "bullish" if ls.long_pct < 0.35
                else "neutral"
            ),
            "timestamp": ls.timestamp.isoformat(),
        }

    def get_liquidation_data(self, pair_symbol: str) -> dict[str, Any] | None:
        """Get taker buy/sell volume data for a symbol."""
        base = pair_symbol.split("/")[0]
        binance_sym = f"{base}USDT"
        liq = self._liquidations.get(binance_sym)
        if liq is None:
            return None
        return {
            "symbol": liq.symbol,
            "buy_sell_ratio": round(liq.buy_sell_ratio, 4),
            "buy_volume": round(liq.buy_volume, 2),
            "sell_volume": round(liq.sell_volume, 2),
            "score": round(self._taker_volume_to_score(liq.buy_sell_ratio), 4),
            "timestamp": liq.timestamp.isoformat(),
        }

    def get_contributing_factors(self, pair_symbol: str) -> dict[str, Any]:
        """Get detailed contributing factors for display."""
        factors: dict[str, Any] = {"available": self._enabled}

        if not self._enabled:
            return factors

        # Fear & Greed
        fg = self._fear_greed
        fg_score = self._fear_greed_to_score(fg.value)
        factors["fear_greed"] = {
            "value": fg.value,
            "classification": fg.classification,
            "score": round(fg_score, 4),
            "signal": (
                "bullish" if fg.value < 25
                else "bearish" if fg.value > 75
                else "neutral"
            ),
            "interpretation": (
                "extreme fear — contrarian buy opportunity"
                if fg.value < 25
                else "fear — favor buying"
                if fg.value < 45
                else "greed — favor caution"
                if fg.value > 55
                else "extreme greed — contrarian sell signal"
                if fg.value > 75
                else "neutral market sentiment"
            ),
        }

        # Long/Short Ratio
        base = pair_symbol.split("/")[0]
        binance_sym = f"{base}USDT"
        ls = self._long_short.get(binance_sym)
        if ls is not None:
            ls_score = self._long_short_to_score(ls.long_pct)
            factors["long_short"] = {
                "long_pct": round(ls.long_pct * 100, 1),
                "short_pct": round(ls.short_pct * 100, 1),
                "ratio": round(ls.long_short_ratio, 3),
                "score": round(ls_score, 4),
                "signal": (
                    "bearish" if ls.long_pct > 0.65
                    else "bullish" if ls.long_pct < 0.35
                    else "neutral"
                ),
                "interpretation": (
                    f"{ls.long_pct*100:.0f}% long — crowd is overcrowded long (contrarian sell)"
                    if ls.long_pct > 0.65
                    else f"{ls.short_pct*100:.0f}% short — crowd is overcrowded short (contrarian buy)"
                    if ls.long_pct < 0.35
                    else f"balanced positioning ({ls.long_pct*100:.0f}% long)"
                ),
            }

        # Taker Volume
        liq = self._liquidations.get(binance_sym)
        if liq is not None:
            tv_score = self._taker_volume_to_score(liq.buy_sell_ratio)
            factors["taker_volume"] = {
                "buy_sell_ratio": round(liq.buy_sell_ratio, 4),
                "buy_volume": round(liq.buy_volume, 2),
                "sell_volume": round(liq.sell_volume, 2),
                "score": round(tv_score, 4),
                "signal": (
                    "bullish" if liq.buy_sell_ratio > 1.2
                    else "bearish" if liq.buy_sell_ratio < 0.8
                    else "neutral"
                ),
            }

        # Top trader L/S ratio
        top_ls = self._top_trader_ls.get(binance_sym)
        if top_ls is not None:
            factors["top_traders"] = {
                "long_pct": round(top_ls.long_pct * 100, 1),
                "short_pct": round(top_ls.short_pct * 100, 1),
                "ratio": round(top_ls.long_short_ratio, 3),
                "signal": (
                    "bearish" if top_ls.long_pct > 0.65
                    else "bullish" if top_ls.long_pct < 0.35
                    else "neutral"
                ),
            }

        return factors

    def get_all_scores(self) -> dict[str, float]:
        """Get market sentiment scores for all tracked pairs."""
        result: dict[str, float] = {}
        for binance_sym in _TRACKED_SYMBOLS:
            pair = _BINANCE_TO_PAIR.get(binance_sym)
            if pair:
                score = self.get_market_sentiment_score(pair)
                if score is not None:
                    result[pair] = score
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
            "fear_greed_value": self._fear_greed.value,
            "fear_greed_class": self._fear_greed.classification,
            "long_short_symbols": len(self._long_short),
            "liquidation_symbols": len(self._liquidations),
            "poll_interval": self._poll_interval,
        }

    # ------ Internal polling ------

    async def _polling_loop(self) -> None:
        # Short initial delay so the server can start accepting requests first
        try:
            await asyncio.sleep(10)
            if self._is_running:
                await self._fetch_all()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Market sentiment feed initial fetch error")

        while self._is_running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._is_running:
                    await self._fetch_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Market sentiment feed polling error")

    async def _fetch_all(self) -> None:
        """Fetch from all sources in parallel."""
        tasks = [
            self._fetch_binance_long_short(),
            self._fetch_binance_taker_volume(),
            self._fetch_binance_top_trader_ls(),
        ]

        # Only fetch Fear & Greed hourly (it updates daily)
        now = time.time()
        if now - self._last_fg_fetch_time >= _FEAR_GREED_POLL_SECONDS:
            tasks.append(self._fetch_fear_greed())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        any_success = False
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.debug("Market sentiment fetch %d failed: %s", i, result)
            elif result is True:
                any_success = True

        if any_success:
            self._healthy = True
            self._last_fetch_time = time.time()

    # ------ Source fetchers ------

    async def _fetch_fear_greed(self) -> bool:
        """Fetch Fear & Greed Index from Alternative.me."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(_FEAR_GREED_URL, params={"limit": "1"})
                resp.raise_for_status()
                data = resp.json()

            entries = data.get("data", [])
            if not entries:
                return False

            entry = entries[0]
            value = int(entry.get("value", "50"))
            classification = entry.get("value_classification", "Neutral")
            ts = int(entry.get("timestamp", "0"))

            self._fear_greed = FearGreedData(
                value=value,
                classification=classification,
                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc),
            )
            self._last_fg_fetch_time = time.time()

            logger.debug("Fear & Greed Index: %d (%s)", value, classification)
            return True
        except Exception as exc:
            logger.debug("Fear & Greed fetch error: %s", exc)
            return False

    async def _fetch_binance_long_short(self) -> bool:
        """Fetch global long/short account ratios from Binance Futures."""
        any_success = False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for binance_sym in _TRACKED_SYMBOLS[:8]:  # Limit to top 8 to respect rate limits
                    try:
                        resp = await client.get(
                            _BINANCE_LONG_SHORT_URL,
                            params={
                                "symbol": binance_sym,
                                "period": "1h",
                                "limit": "1",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        if data and isinstance(data, list) and len(data) > 0:
                            entry = data[-1]  # latest
                            self._long_short[binance_sym] = LongShortData(
                                symbol=binance_sym,
                                long_short_ratio=float(entry.get("longShortRatio", "1.0")),
                                long_pct=float(entry.get("longAccount", "0.5")),
                                short_pct=float(entry.get("shortAccount", "0.5")),
                                timestamp=datetime.fromtimestamp(
                                    entry.get("timestamp", 0) / 1000, tz=timezone.utc
                                ),
                            )
                            any_success = True
                    except Exception:
                        logger.debug("L/S ratio fetch failed for %s", binance_sym)
        except Exception as exc:
            logger.debug("Binance L/S ratio fetch error: %s", exc)

        return any_success

    async def _fetch_binance_taker_volume(self) -> bool:
        """Fetch taker buy/sell volume ratio from Binance Futures.

        This serves as a liquidation proxy — heavy sell volume often
        accompanies liquidation cascades.
        """
        any_success = False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for binance_sym in _TRACKED_SYMBOLS[:8]:
                    try:
                        resp = await client.get(
                            _BINANCE_TAKER_VOLUME_URL,
                            params={
                                "symbol": binance_sym,
                                "period": "1h",
                                "limit": "1",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        if data and isinstance(data, list) and len(data) > 0:
                            entry = data[-1]
                            buy_vol = float(entry.get("buyVol", "0"))
                            sell_vol = float(entry.get("sellVol", "0"))
                            ratio = float(entry.get("buySellRatio", "1.0"))

                            self._liquidations[binance_sym] = LiquidationData(
                                symbol=binance_sym,
                                buy_sell_ratio=ratio,
                                buy_volume=buy_vol,
                                sell_volume=sell_vol,
                                timestamp=datetime.fromtimestamp(
                                    entry.get("timestamp", 0) / 1000, tz=timezone.utc
                                ),
                            )
                            any_success = True
                    except Exception:
                        logger.debug("Taker volume fetch failed for %s", binance_sym)
        except Exception as exc:
            logger.debug("Binance taker volume fetch error: %s", exc)

        return any_success

    async def _fetch_binance_top_trader_ls(self) -> bool:
        """Fetch top trader long/short account ratio from Binance Futures.

        Top 20% of traders by margin balance — "smart money" positioning.
        """
        any_success = False
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                for binance_sym in _TRACKED_SYMBOLS[:8]:
                    try:
                        resp = await client.get(
                            _BINANCE_TOP_TRADER_URL,
                            params={
                                "symbol": binance_sym,
                                "period": "1h",
                                "limit": "1",
                            },
                        )
                        resp.raise_for_status()
                        data = resp.json()

                        if data and isinstance(data, list) and len(data) > 0:
                            entry = data[-1]
                            self._top_trader_ls[binance_sym] = LongShortData(
                                symbol=binance_sym,
                                long_short_ratio=float(entry.get("longShortRatio", "1.0")),
                                long_pct=float(entry.get("longAccount", "0.5")),
                                short_pct=float(entry.get("shortAccount", "0.5")),
                                timestamp=datetime.fromtimestamp(
                                    entry.get("timestamp", 0) / 1000, tz=timezone.utc
                                ),
                            )
                            any_success = True
                    except Exception:
                        logger.debug("Top trader L/S fetch failed for %s", binance_sym)
        except Exception as exc:
            logger.debug("Binance top trader L/S fetch error: %s", exc)

        return any_success

    # ------ Scoring functions ------

    @staticmethod
    def _fear_greed_to_score(value: int) -> float:
        """Convert Fear & Greed Index (0-100) to a 0-1 score.

        **Contrarian**: extreme fear = buy opportunity (score > 0.5),
        extreme greed = caution (score < 0.5).

        Uses inverted linear mapping: score = 1 - (value / 100)
        with mild sigmoid shaping around extremes.
        """
        # Invert: 0 (extreme fear) -> 1.0 (very bullish)
        #         100 (extreme greed) -> 0.0 (very bearish)
        normalized = value / 100.0
        # Sigmoid shaping to amplify extremes
        # x = normalized * 6 - 3  gives us a -3 to 3 range
        x = normalized * 6 - 3
        sigmoid_shaped = 1.0 / (1.0 + math.exp(x))
        return max(0.0, min(1.0, sigmoid_shaped))

    @staticmethod
    def _long_short_to_score(long_pct: float) -> float:
        """Convert long percentage (0-1) to a 0-1 score.

        **Contrarian**: when most accounts are long, price tends to drop.
        - long_pct > 0.65 (65%+ long) → bearish → score < 0.5
        - long_pct < 0.35 (65%+ short) → bullish → score > 0.5
        - long_pct = 0.50 → neutral → 0.5

        Uses inverted sigmoid centered at 0.5.
        """
        # Invert: more longs = lower score (contrarian)
        deviation = (long_pct - 0.5) * 10  # scale for sigmoid sensitivity
        return 1.0 / (1.0 + math.exp(deviation))

    @staticmethod
    def _taker_volume_to_score(buy_sell_ratio: float) -> float:
        """Convert taker buy/sell volume ratio to a 0-1 score.

        This is a **momentum** indicator (not contrarian):
        - ratio > 1 → more taker buys → bullish → score > 0.5
        - ratio < 1 → more taker sells (liquidation proxy) → bearish → score < 0.5

        Heavy sell-side taker volume often accompanies liquidation cascades.
        """
        if buy_sell_ratio <= 0:
            return 0.0
        log_ratio = math.log(buy_sell_ratio)
        return 1.0 / (1.0 + math.exp(-log_ratio * 3))
