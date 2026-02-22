"""Derivatives data feed — funding rate, open interest, and order book depth via ccxt.

All three indicators are free and available from most exchanges that support
perpetual futures.  Together they form a powerful short-term directional signal:

* **Funding Rate** — Contrarian indicator.  Extreme positive rates (>0.05%)
  mean longs are overleveraged and a correction is likely within 4-24h.
  Extreme negative rates suggest shorts are overleveraged (reversal up).

* **Open Interest** — Trend strength confirmation.  Rising price + rising OI
  = strong trend.  Rising price + falling OI = weak rally about to reverse.

* **Order Book Depth** — Bid/ask imbalance predicts direction within minutes.
  A 3:1 bid ratio signals imminent price increase.

The feed produces a composite 0-1 score per symbol that the orchestrator
blends into the signal fusion system alongside technical, sentiment, and
on-chain scores.

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

logger = logging.getLogger(__name__)

# Polling interval — 2 minutes (funding rate changes every 8h, but OI and
# order book are more dynamic; 2 min strikes a balance).
_DEFAULT_POLL_SECONDS = 120

# Order book depth to fetch (number of price levels on each side)
_ORDER_BOOK_DEPTH = 25

# Funding rate thresholds (per 8-hour period)
_FUNDING_EXTREME_HIGH = 0.05   # 0.05% — longs overleveraged
_FUNDING_EXTREME_LOW = -0.05   # -0.05% — shorts overleveraged
_FUNDING_SCALE = 0.10          # sigmoid scale for funding rate scoring

# Open interest change thresholds (percent change for scoring)
_OI_CHANGE_SCALE = 10.0  # percent change scale for sigmoid

# Order book imbalance thresholds
_BOOK_IMBALANCE_SCALE = 2.0  # ratio scale for sigmoid


@dataclass
class DerivativesSnapshot:
    """Point-in-time derivatives data for a single symbol."""

    symbol: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Funding rate (per 8h period, as a percentage, e.g. 0.01 = 0.01%)
    funding_rate: float | None = None
    funding_timestamp: float | None = None  # next funding time (unix)

    # Open interest
    open_interest_usd: float | None = None
    prev_open_interest_usd: float | None = None  # for change calculation

    # Order book depth
    bid_volume: float | None = None   # total bid volume in top N levels
    ask_volume: float | None = None   # total ask volume in top N levels
    bid_ask_ratio: float | None = None  # bid_volume / ask_volume


class DerivativesFeed:
    """Singleton feed that fetches derivatives data via ccxt.

    Uses ``MarketDataProvider._create_ccxt_exchange()`` for exchange connectivity.
    Only works when an exchange is configured (e.g. Kraken, Binance).

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[DerivativesFeed | None] = None

    def __init__(self) -> None:
        self._snapshots: dict[str, DerivativesSnapshot] = {}  # symbol -> latest
        self._prev_oi: dict[str, float] = {}  # symbol -> previous OI for change calc
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False
        self._last_fetch_time: float = 0
        self._poll_interval: int = _DEFAULT_POLL_SECONDS
        self._watched_symbols: list[str] = []  # symbols to track (set from watched pairs)

    @classmethod
    def get_instance(cls) -> DerivativesFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------ BaseFeed protocol ------

    @property
    def name(self) -> str:
        return "derivatives"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic fetching.  Enabled only when an exchange is configured."""
        # Check if we have an exchange configured
        has_exchange = await self._check_exchange_available()
        if not has_exchange:
            logger.info("Derivatives feed disabled — no exchange configured")
            self._enabled = False
            return

        self._enabled = True
        self._is_running = True

        # Get initial watched symbols
        self._refresh_watched_symbols()

        # Fetch immediately, then start background loop
        await self._fetch_all()
        self._fetch_task = asyncio.create_task(self._polling_loop())
        logger.info(
            "Derivatives feed started (poll interval=%ds, %d symbols tracked)",
            self._poll_interval,
            len(self._watched_symbols),
        )

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
        logger.info("Derivatives feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ------ Public query methods ------

    def get_derivatives_score(self, pair_symbol: str) -> float | None:
        """Compute a composite 0-1 derivatives score for a trading pair.

        The score blends three sub-scores:

        * Funding rate score (weight 0.35) — Contrarian: high funding = bearish
        * Open interest change score (weight 0.30) — Rising OI = trend strength
        * Order book imbalance score (weight 0.35) — Bid-heavy = bullish

        Returns ``None`` if no derivatives data is available.
        """
        if not self._enabled:
            return None

        snapshot = self._snapshots.get(pair_symbol)
        if snapshot is None:
            # Try base symbol with /USDT suffix
            base = pair_symbol.split("/")[0]
            for key in self._snapshots:
                if key.startswith(base):
                    snapshot = self._snapshots[key]
                    break

        if snapshot is None:
            return None

        scores: dict[str, float] = {}
        weights: dict[str, float] = {}

        # 1. Funding rate score (contrarian — high positive funding is bearish)
        if snapshot.funding_rate is not None:
            scores["funding"] = self._funding_rate_to_score(snapshot.funding_rate)
            weights["funding"] = 0.35

        # 2. Open interest change score (rising OI with direction = trend confirmation)
        if snapshot.open_interest_usd is not None and snapshot.prev_open_interest_usd is not None:
            oi_change_pct = 0.0
            if snapshot.prev_open_interest_usd > 0:
                oi_change_pct = (
                    (snapshot.open_interest_usd - snapshot.prev_open_interest_usd)
                    / snapshot.prev_open_interest_usd
                    * 100
                )
            scores["open_interest"] = self._oi_change_to_score(oi_change_pct)
            weights["open_interest"] = 0.30

        # 3. Order book imbalance score
        if snapshot.bid_ask_ratio is not None:
            scores["order_book"] = self._book_imbalance_to_score(snapshot.bid_ask_ratio)
            weights["order_book"] = 0.35

        if not scores:
            return None

        # Normalize weights to sum to 1.0
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return None

        composite = sum(
            scores[k] * (weights[k] / total_weight)
            for k in scores
        )
        return round(max(0.0, min(1.0, composite)), 4)

    def get_snapshot(self, pair_symbol: str) -> dict[str, Any] | None:
        """Get the raw derivatives snapshot for a pair (for display/debugging)."""
        snapshot = self._snapshots.get(pair_symbol)
        if snapshot is None:
            base = pair_symbol.split("/")[0]
            for key in self._snapshots:
                if key.startswith(base):
                    snapshot = self._snapshots[key]
                    break

        if snapshot is None:
            return None

        oi_change_pct = None
        if snapshot.open_interest_usd is not None and snapshot.prev_open_interest_usd:
            oi_change_pct = round(
                (snapshot.open_interest_usd - snapshot.prev_open_interest_usd)
                / snapshot.prev_open_interest_usd * 100,
                2,
            )

        return {
            "symbol": snapshot.symbol,
            "funding_rate": snapshot.funding_rate,
            "funding_rate_pct": (
                round(snapshot.funding_rate * 100, 4) if snapshot.funding_rate is not None else None
            ),
            "open_interest_usd": snapshot.open_interest_usd,
            "oi_change_pct": oi_change_pct,
            "bid_volume": snapshot.bid_volume,
            "ask_volume": snapshot.ask_volume,
            "bid_ask_ratio": (
                round(snapshot.bid_ask_ratio, 3) if snapshot.bid_ask_ratio is not None else None
            ),
            "timestamp": snapshot.timestamp.isoformat(),
        }

    def get_contributing_factors(self, pair_symbol: str) -> dict[str, Any]:
        """Get detailed contributing factors for signal fusion display."""
        snapshot = self._snapshots.get(pair_symbol)
        if snapshot is None:
            base = pair_symbol.split("/")[0]
            for key in self._snapshots:
                if key.startswith(base):
                    snapshot = self._snapshots[key]
                    break

        if snapshot is None:
            return {"available": False}

        factors: dict[str, Any] = {"available": True}

        if snapshot.funding_rate is not None:
            fr_score = self._funding_rate_to_score(snapshot.funding_rate)
            factors["funding_rate"] = {
                "raw": round(snapshot.funding_rate * 100, 4),
                "score": round(fr_score, 4),
                "signal": (
                    "bearish" if snapshot.funding_rate > _FUNDING_EXTREME_HIGH / 100
                    else "bullish" if snapshot.funding_rate < _FUNDING_EXTREME_LOW / 100
                    else "neutral"
                ),
                "interpretation": (
                    "longs overleveraged (contrarian sell)"
                    if snapshot.funding_rate > _FUNDING_EXTREME_HIGH / 100
                    else "shorts overleveraged (contrarian buy)"
                    if snapshot.funding_rate < _FUNDING_EXTREME_LOW / 100
                    else "balanced funding"
                ),
            }

        if snapshot.open_interest_usd is not None:
            oi_change_pct = 0.0
            if snapshot.prev_open_interest_usd and snapshot.prev_open_interest_usd > 0:
                oi_change_pct = (
                    (snapshot.open_interest_usd - snapshot.prev_open_interest_usd)
                    / snapshot.prev_open_interest_usd * 100
                )
            oi_score = self._oi_change_to_score(oi_change_pct)
            factors["open_interest"] = {
                "usd": round(snapshot.open_interest_usd, 2),
                "change_pct": round(oi_change_pct, 2),
                "score": round(oi_score, 4),
                "signal": (
                    "bullish" if oi_change_pct > 2 else
                    "bearish" if oi_change_pct < -2 else "neutral"
                ),
            }

        if snapshot.bid_ask_ratio is not None:
            book_score = self._book_imbalance_to_score(snapshot.bid_ask_ratio)
            factors["order_book"] = {
                "bid_volume": round(snapshot.bid_volume or 0, 2),
                "ask_volume": round(snapshot.ask_volume or 0, 2),
                "ratio": round(snapshot.bid_ask_ratio, 3),
                "score": round(book_score, 4),
                "signal": (
                    "bullish" if snapshot.bid_ask_ratio > 1.5 else
                    "bearish" if snapshot.bid_ask_ratio < 0.67 else "neutral"
                ),
            }

        return factors

    def get_all_scores(self) -> dict[str, float]:
        """Get derivatives scores for all tracked symbols."""
        result: dict[str, float] = {}
        for symbol in self._snapshots:
            score = self.get_derivatives_score(symbol)
            if score is not None:
                result[symbol] = score
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
            "symbols_tracked": len(self._snapshots),
            "watched_symbols": len(self._watched_symbols),
            "poll_interval": self._poll_interval,
        }

    # ------ Internal polling ------

    async def _polling_loop(self) -> None:
        while self._is_running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._is_running:
                    # Refresh symbol list in case watched pairs changed
                    self._refresh_watched_symbols()
                    await self._fetch_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Derivatives feed polling error")

    def _refresh_watched_symbols(self) -> None:
        """Update the list of symbols to track from the engine's watched pairs."""
        try:
            from ctrade.exchange.paper_engine import PaperEngine
            pairs = PaperEngine.get_instance().get_watched_pairs()
            self._watched_symbols = list(pairs) if pairs else []
        except Exception:
            logger.debug("Could not refresh watched symbols for derivatives feed")

    async def _check_exchange_available(self) -> bool:
        """Check if an exchange is configured."""
        try:
            from ctrade.exchange.market_data import MarketDataProvider
            exchange = await MarketDataProvider.get_instance()._create_ccxt_exchange()
            if exchange:
                await exchange.close()
                return True
            return False
        except Exception:
            return False

    async def _fetch_all(self) -> None:
        """Fetch derivatives data for all watched symbols."""
        if not self._watched_symbols:
            return

        from ctrade.exchange.market_data import MarketDataProvider
        market = MarketDataProvider.get_instance()

        exchange = await market._create_ccxt_exchange()
        if not exchange:
            logger.debug("No exchange available for derivatives feed")
            return

        try:
            # Load markets to know what's available
            try:
                await exchange.load_markets()
            except Exception as e:
                logger.debug("Could not load markets for derivatives: %s", e)
                return

            fetched_count = 0
            for pair in self._watched_symbols:
                try:
                    snapshot = await self._fetch_symbol_data(exchange, pair)
                    if snapshot:
                        self._snapshots[pair] = snapshot
                        fetched_count += 1
                except Exception:
                    logger.debug("Failed to fetch derivatives for %s", pair, exc_info=True)

            if fetched_count > 0:
                self._healthy = True
                self._last_fetch_time = time.time()
                logger.debug(
                    "Derivatives feed: updated %d/%d symbols",
                    fetched_count, len(self._watched_symbols),
                )
            else:
                # If we got nothing but didn't error, still mark time
                self._last_fetch_time = time.time()

        except Exception:
            self._healthy = False
            logger.exception("Derivatives feed fetch error")
        finally:
            try:
                await exchange.close()
            except Exception:
                pass

    async def _fetch_symbol_data(self, exchange: Any, pair: str) -> DerivativesSnapshot | None:
        """Fetch all derivatives data for a single symbol.

        Tries each data source independently — partial data is better than none.
        Not all exchanges support all endpoints (e.g. Kraken spot doesn't have
        funding rates), so failures are handled gracefully.
        """
        snapshot = DerivativesSnapshot(symbol=pair)
        got_any = False

        # 1. Funding rate
        try:
            funding = await self._fetch_funding_rate(exchange, pair)
            if funding is not None:
                snapshot.funding_rate = funding["rate"]
                snapshot.funding_timestamp = funding.get("timestamp")
                got_any = True
        except Exception:
            logger.debug("Funding rate unavailable for %s", pair)

        # 2. Open interest
        try:
            oi = await self._fetch_open_interest(exchange, pair)
            if oi is not None:
                snapshot.open_interest_usd = oi
                # Store previous OI for change calculation
                prev = self._prev_oi.get(pair)
                if prev is not None:
                    snapshot.prev_open_interest_usd = prev
                self._prev_oi[pair] = oi
                got_any = True
        except Exception:
            logger.debug("Open interest unavailable for %s", pair)

        # 3. Order book depth
        try:
            book = await self._fetch_order_book(exchange, pair)
            if book is not None:
                snapshot.bid_volume = book["bid_volume"]
                snapshot.ask_volume = book["ask_volume"]
                snapshot.bid_ask_ratio = book["ratio"]
                got_any = True
        except Exception:
            logger.debug("Order book unavailable for %s", pair)

        return snapshot if got_any else None

    async def _fetch_funding_rate(self, exchange: Any, pair: str) -> dict[str, Any] | None:
        """Fetch funding rate via ccxt.fetch_funding_rate().

        Not all exchanges support this (e.g. Kraken spot). Returns None
        if unavailable.
        """
        if not hasattr(exchange, "fetch_funding_rate"):
            return None

        try:
            data = await exchange.fetch_funding_rate(pair)
            rate = data.get("fundingRate")
            if rate is None:
                return None
            return {
                "rate": float(rate),
                "timestamp": data.get("fundingTimestamp"),
            }
        except Exception:
            # Try with perpetual symbol format (e.g. BTC/USDT:USDT)
            try:
                perp_symbol = pair + ":USDT" if ":USDT" not in pair else pair
                data = await exchange.fetch_funding_rate(perp_symbol)
                rate = data.get("fundingRate")
                if rate is None:
                    return None
                return {
                    "rate": float(rate),
                    "timestamp": data.get("fundingTimestamp"),
                }
            except Exception:
                return None

    async def _fetch_open_interest(self, exchange: Any, pair: str) -> float | None:
        """Fetch open interest via ccxt.fetch_open_interest().

        Returns open interest in USD. Not all exchanges support this.
        """
        if not hasattr(exchange, "fetch_open_interest"):
            return None

        try:
            data = await exchange.fetch_open_interest(pair)
            # ccxt returns openInterestAmount and openInterestValue
            oi_value = data.get("openInterestValue")
            if oi_value is not None:
                return float(oi_value)

            # Fall back to amount * mark price estimate
            oi_amount = data.get("openInterestAmount")
            if oi_amount is not None:
                return float(oi_amount)  # raw amount, not ideal but usable
            return None
        except Exception:
            # Try with perpetual symbol format
            try:
                perp_symbol = pair + ":USDT" if ":USDT" not in pair else pair
                data = await exchange.fetch_open_interest(perp_symbol)
                oi_value = data.get("openInterestValue")
                if oi_value is not None:
                    return float(oi_value)
                oi_amount = data.get("openInterestAmount")
                if oi_amount is not None:
                    return float(oi_amount)
                return None
            except Exception:
                return None

    async def _fetch_order_book(self, exchange: Any, pair: str) -> dict[str, float] | None:
        """Fetch order book and compute bid/ask volume imbalance.

        Uses the spot order book (available on virtually all exchanges).
        Returns bid volume, ask volume, and their ratio.
        """
        if not hasattr(exchange, "fetch_order_book"):
            return None

        try:
            book = await exchange.fetch_order_book(pair, limit=_ORDER_BOOK_DEPTH)

            bids = book.get("bids", [])
            asks = book.get("asks", [])

            if not bids or not asks:
                return None

            # Sum volume (quantity) on each side
            # Each entry is [price, quantity]
            bid_volume = sum(float(b[1]) * float(b[0]) for b in bids)  # USD volume
            ask_volume = sum(float(a[1]) * float(a[0]) for a in asks)  # USD volume

            if ask_volume <= 0:
                return None

            ratio = bid_volume / ask_volume

            return {
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "ratio": ratio,
            }
        except Exception:
            return None

    # ------ Scoring functions ------

    @staticmethod
    def _funding_rate_to_score(funding_rate: float) -> float:
        """Convert funding rate to a 0-1 score.

        This is a **contrarian** indicator:
        - High positive funding (longs pay shorts) → bearish → score < 0.5
        - Negative funding (shorts pay longs) → bullish → score > 0.5
        - Zero funding → neutral → 0.5

        Uses inverted sigmoid: score = 1 / (1 + exp(rate * 100 / scale))
        Note the *positive* exponent (inverted) because high funding is bearish.
        """
        # Convert from decimal to percentage basis points for scaling
        rate_pct = funding_rate * 100  # e.g. 0.0001 -> 0.01%
        return 1.0 / (1.0 + math.exp(rate_pct / _FUNDING_SCALE))

    @staticmethod
    def _oi_change_to_score(oi_change_pct: float) -> float:
        """Convert open interest change (%) to a 0-1 score.

        Rising OI → score > 0.5 (trend is strengthening)
        Falling OI → score < 0.5 (trend is weakening)

        Note: This is a *directional* indicator — it tells you the trend is
        strong, but not which direction.  Combined with price direction from
        technical analysis, rising OI confirms the move.
        """
        return 1.0 / (1.0 + math.exp(-oi_change_pct / _OI_CHANGE_SCALE))

    @staticmethod
    def _book_imbalance_to_score(bid_ask_ratio: float) -> float:
        """Convert order book bid/ask ratio to a 0-1 score.

        bid_ask_ratio > 1 → more buying pressure → bullish → score > 0.5
        bid_ask_ratio < 1 → more selling pressure → bearish → score < 0.5
        bid_ask_ratio = 1 → balanced → 0.5

        Uses log-ratio for symmetry: ratio of 2 = same distance from 0.5
        as ratio of 0.5.
        """
        if bid_ask_ratio <= 0:
            return 0.0
        log_ratio = math.log(bid_ask_ratio)
        return 1.0 / (1.0 + math.exp(-log_ratio / _BOOK_IMBALANCE_SCALE))
