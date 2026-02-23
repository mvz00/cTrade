"""Cumulative Volume Delta (CVD) feed — detects price-CVD divergences.

CVD = running sum of (taker buy volume - taker sell volume).  The key trading
signal is *divergence* between price and CVD:

* **Price up + CVD down** → distribution (smart money selling into strength).
  Bearish reversal coming within hours.

* **Price down + CVD up** → accumulation (smart money buying the dip).
  Bullish reversal coming within hours.

* **Price and CVD aligned** → trend confirmation (weaker signal, in direction).

Data source: Binance Futures public ``/fapi/v1/klines`` endpoint (no auth).
Each kline includes ``takerBuyBaseAssetVolume`` at index 9, which lets us
compute per-candle delta = taker_buy - taker_sell.

Follows the same singleton/BaseFeed pattern as :class:`DerivativesFeed`.
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

# ---- API endpoint (free, no auth required) ----

_BINANCE_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"

# Defaults
_DEFAULT_POLL_SECONDS = 120   # 2 minutes
_CVD_WINDOW = 12              # candles for divergence detection
_KLINES_LIMIT = 24            # fetch last 24 1h candles
_MAX_SYMBOLS = 8              # limit to top 8 watched pairs

# Scoring parameters
_PRICE_NORM_SCALE = 5.0       # tanh scale for price change %
_CVD_NORM_SCALE = 10.0        # tanh scale for CVD change %
_DIVERGENCE_SENSITIVITY = 2.0 # sigmoid sensitivity for divergence


@dataclass
class CVDSnapshot:
    """CVD data for a single symbol."""

    symbol: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cvd_values: list[float] = field(default_factory=list)
    closes: list[float] = field(default_factory=list)
    price_change_pct: float = 0.0
    cvd_change_pct: float = 0.0
    divergence_type: str = "none"  # "bullish_div", "bearish_div", "confirmation_bull", "confirmation_bear", "none"
    cvd_acceleration: float = 0.0  # rate of change of CVD (recent vs prior half)


class CVDFeed:
    """Singleton feed for Cumulative Volume Delta divergence detection.

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[CVDFeed | None] = None

    def __init__(self) -> None:
        self._snapshots: dict[str, CVDSnapshot] = {}
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False
        self._last_fetch_time: float = 0
        self._poll_interval: int = _DEFAULT_POLL_SECONDS
        self._watched_symbols: list[str] = []

    @classmethod
    def get_instance(cls) -> CVDFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------ BaseFeed protocol ------

    @property
    def name(self) -> str:
        return "cvd"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic CVD fetching.  Always enabled (Binance klines are free)."""
        self._enabled = True
        self._is_running = True
        self._refresh_watched_symbols()

        # Start background polling — first fetch happens after a short delay
        # so the server can begin accepting healthcheck requests immediately.
        self._fetch_task = asyncio.create_task(self._polling_loop())
        logger.info("CVD feed started (poll=%ds, first fetch in ~10s)", self._poll_interval)

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
        logger.info("CVD feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ------ Public query methods ------

    def get_cvd_score(self, pair_symbol: str) -> float | None:
        """Compute 0-1 CVD divergence score for a trading pair.

        Interpretation:
        * score > 0.5 → CVD suggests bullish conditions (accumulation / confirmation)
        * score < 0.5 → CVD suggests bearish conditions (distribution / confirmation)
        * score ≈ 0.5 → no meaningful divergence or confirmation

        Returns ``None`` if the feed is not enabled or no data for this pair.
        """
        if not self._enabled:
            return None

        snapshot = self._find_snapshot(pair_symbol)
        if snapshot is None:
            return None

        # Primary score: divergence (90% weight)
        div_score = self._cvd_divergence_to_score(
            snapshot.price_change_pct, snapshot.cvd_change_pct
        )

        # Secondary: acceleration bonus (10% weight)
        accel_score = 0.5 + math.tanh(snapshot.cvd_acceleration) * 0.5

        composite = 0.90 * div_score + 0.10 * accel_score
        return round(max(0.0, min(1.0, composite)), 4)

    def get_snapshot(self, pair_symbol: str) -> dict[str, Any] | None:
        """Get raw CVD snapshot data for display."""
        snapshot = self._find_snapshot(pair_symbol)
        if snapshot is None:
            return None

        return {
            "symbol": snapshot.symbol,
            "price_change_pct": round(snapshot.price_change_pct, 2),
            "cvd_change_pct": round(snapshot.cvd_change_pct, 2),
            "divergence_type": snapshot.divergence_type,
            "cvd_acceleration": round(snapshot.cvd_acceleration, 4),
            "candles": len(snapshot.closes),
            "timestamp": snapshot.timestamp.isoformat(),
        }

    def get_contributing_factors(self, pair_symbol: str) -> dict[str, Any]:
        """Get detailed contributing factors for display."""
        if not self._enabled:
            return {"available": False}

        snapshot = self._find_snapshot(pair_symbol)
        if snapshot is None:
            return {"available": True, "data": False}

        div_score = self._cvd_divergence_to_score(
            snapshot.price_change_pct, snapshot.cvd_change_pct
        )

        return {
            "available": True,
            "data": True,
            "price_change_pct": round(snapshot.price_change_pct, 2),
            "cvd_change_pct": round(snapshot.cvd_change_pct, 2),
            "divergence_type": snapshot.divergence_type,
            "divergence_score": round(div_score, 4),
            "cvd_acceleration": round(snapshot.cvd_acceleration, 4),
            "signal": (
                "bullish" if snapshot.divergence_type == "bullish_div"
                else "bearish" if snapshot.divergence_type == "bearish_div"
                else "neutral"
            ),
            "interpretation": (
                "price falling but CVD rising — accumulation (bullish reversal expected)"
                if snapshot.divergence_type == "bullish_div"
                else "price rising but CVD falling — distribution (bearish reversal expected)"
                if snapshot.divergence_type == "bearish_div"
                else f"price and CVD aligned ({snapshot.divergence_type})"
                if "confirmation" in snapshot.divergence_type
                else "no significant divergence"
            ),
        }

    def get_all_scores(self) -> dict[str, float]:
        """Get CVD scores for all tracked pairs."""
        result: dict[str, float] = {}
        for pair in self._snapshots:
            score = self.get_cvd_score(pair)
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
            "symbols_tracked": len(self._snapshots),
            "watched_symbols": self._watched_symbols[:],
            "poll_interval": self._poll_interval,
        }

    # ------ Internal methods ------

    def _find_snapshot(self, pair_symbol: str) -> CVDSnapshot | None:
        """Look up snapshot by pair symbol with prefix matching."""
        snapshot = self._snapshots.get(pair_symbol)
        if snapshot is not None:
            return snapshot

        # Try prefix match (e.g., "BTC/USD" matches "BTC/USDT")
        base = pair_symbol.split("/")[0]
        for key, snap in self._snapshots.items():
            if key.startswith(base + "/"):
                return snap
        return None

    def _refresh_watched_symbols(self) -> None:
        """Get current watched pairs from the paper engine."""
        try:
            from ctrade.exchange.paper_engine import PaperEngine

            pairs = PaperEngine.get_instance().get_watched_pairs()
            self._watched_symbols = pairs[:_MAX_SYMBOLS]
        except Exception:
            self._watched_symbols = []

    async def _polling_loop(self) -> None:
        # Short initial delay so the server can start accepting requests first
        try:
            await asyncio.sleep(10)
            if self._is_running:
                self._refresh_watched_symbols()
                await self._fetch_all()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("CVD feed initial fetch error")

        while self._is_running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._is_running:
                    self._refresh_watched_symbols()
                    await self._fetch_all()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("CVD feed polling error")

    async def _fetch_all(self) -> None:
        """Fetch CVD data for all watched symbols."""
        if not self._watched_symbols:
            return

        any_success = False
        async with httpx.AsyncClient(timeout=15.0) as client:
            for pair in self._watched_symbols:
                try:
                    snapshot = await self._fetch_symbol_cvd(client, pair)
                    if snapshot is not None:
                        self._snapshots[pair] = snapshot
                        any_success = True
                except Exception:
                    logger.debug("CVD fetch failed for %s", pair)

        if any_success:
            self._healthy = True
            self._last_fetch_time = time.time()

    async def _fetch_symbol_cvd(
        self, client: httpx.AsyncClient, pair: str
    ) -> CVDSnapshot | None:
        """Fetch klines and compute CVD for a single symbol."""
        base = pair.split("/")[0]
        binance_sym = f"{base}USDT"

        resp = await client.get(
            _BINANCE_KLINES_URL,
            params={
                "symbol": binance_sym,
                "interval": "1h",
                "limit": str(_KLINES_LIMIT),
            },
        )
        resp.raise_for_status()
        klines = resp.json()

        if not klines or not isinstance(klines, list) or len(klines) < _CVD_WINDOW:
            return None

        # Compute running CVD from kline data
        cvd = 0.0
        cvd_values: list[float] = []
        closes: list[float] = []

        for k in klines:
            total_vol = float(k[5])       # total base asset volume
            taker_buy = float(k[9])       # taker buy base asset volume
            taker_sell = total_vol - taker_buy
            delta = taker_buy - taker_sell
            cvd += delta
            cvd_values.append(cvd)
            closes.append(float(k[4]))    # close price

        # Compute divergence over window
        price_change_pct, cvd_change_pct, divergence_type, acceleration = (
            self._compute_divergence(closes, cvd_values, _CVD_WINDOW)
        )

        return CVDSnapshot(
            symbol=pair,
            cvd_values=cvd_values,
            closes=closes,
            price_change_pct=price_change_pct,
            cvd_change_pct=cvd_change_pct,
            divergence_type=divergence_type,
            cvd_acceleration=acceleration,
        )

    # ------ Divergence computation ------

    @staticmethod
    def _compute_divergence(
        closes: list[float],
        cvd_values: list[float],
        window: int,
    ) -> tuple[float, float, str, float]:
        """Compute price-CVD divergence over a rolling window.

        Returns:
            (price_change_pct, cvd_change_pct, divergence_type, cvd_acceleration)
        """
        n = len(closes)
        if n < window:
            return 0.0, 0.0, "none", 0.0

        # Price change over window
        start_price = closes[n - window]
        end_price = closes[-1]
        if start_price > 0:
            price_change_pct = ((end_price - start_price) / start_price) * 100
        else:
            price_change_pct = 0.0

        # CVD change over window (as percentage of starting absolute value)
        start_cvd = cvd_values[n - window]
        end_cvd = cvd_values[-1]
        cvd_delta = end_cvd - start_cvd
        # Normalize CVD change relative to average volume for comparability
        avg_abs_cvd = max(
            1.0,
            sum(abs(cvd_values[i] - cvd_values[i - 1]) for i in range(1, n)) / (n - 1),
        )
        cvd_change_pct = (cvd_delta / avg_abs_cvd) * 100

        # Classify divergence
        price_thresh = 0.5   # minimum % change to consider meaningful
        cvd_thresh = 5.0     # minimum % change for CVD

        if abs(price_change_pct) < price_thresh and abs(cvd_change_pct) < cvd_thresh:
            divergence_type = "none"
        elif price_change_pct > price_thresh and cvd_change_pct < -cvd_thresh:
            divergence_type = "bearish_div"
        elif price_change_pct < -price_thresh and cvd_change_pct > cvd_thresh:
            divergence_type = "bullish_div"
        elif price_change_pct > price_thresh and cvd_change_pct > cvd_thresh:
            divergence_type = "confirmation_bull"
        elif price_change_pct < -price_thresh and cvd_change_pct < -cvd_thresh:
            divergence_type = "confirmation_bear"
        else:
            divergence_type = "none"

        # CVD acceleration: compare recent half vs prior half of window
        half = window // 2
        if n >= window and half > 0:
            recent_delta = cvd_values[-1] - cvd_values[-1 - half]
            prior_delta = cvd_values[-1 - half] - cvd_values[-1 - window]
            # Normalize by avg_abs_cvd for scale-independence
            acceleration = (recent_delta - prior_delta) / max(1.0, avg_abs_cvd)
        else:
            acceleration = 0.0

        return price_change_pct, cvd_change_pct, divergence_type, acceleration

    # ------ Scoring functions ------

    @staticmethod
    def _cvd_divergence_to_score(
        price_change_pct: float,
        cvd_change_pct: float,
    ) -> float:
        """Convert CVD-price divergence to a 0-1 score.

        Divergences (contrarian — CVD disagrees with price):
        - price up + CVD down → distribution → bearish → score < 0.5
        - price down + CVD up → accumulation → bullish → score > 0.5

        Confirmations (aligned — CVD confirms price):
        - both up → mild bullish → score slightly > 0.5
        - both down → mild bearish → score slightly < 0.5

        No movement → neutral → 0.5
        """
        if abs(price_change_pct) < 0.1 and abs(cvd_change_pct) < 0.1:
            return 0.5

        # Normalize both to comparable ±1 range via tanh
        price_norm = math.tanh(price_change_pct / _PRICE_NORM_SCALE)
        cvd_norm = math.tanh(cvd_change_pct / _CVD_NORM_SCALE)

        # Divergence = CVD direction minus price direction
        # Positive → CVD bullish relative to price → bullish signal
        # Negative → CVD bearish relative to price → bearish signal
        divergence = cvd_norm - price_norm

        # Map to 0-1 via sigmoid
        score = 1.0 / (1.0 + math.exp(-divergence * _DIVERGENCE_SENSITIVITY))
        return max(0.0, min(1.0, score))
