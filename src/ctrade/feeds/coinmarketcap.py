"""CoinMarketCap data feed — fetches market listings and computes momentum scores.

Fetches the top 200 cryptocurrencies by market cap every 5 minutes
(well within the free-tier limit of 333 calls/day).  Each listing
includes percent-change figures and volume which are combined into
a single 0-1 *momentum score* that the orchestrator can blend into
the composite trading signal.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any, ClassVar

import httpx

logger = logging.getLogger(__name__)

# CMC free tier: 333 calls/day.  5-minute cache = max 288 calls/day.
_CACHE_TTL_SECONDS = 300  # 5 minutes
_CMC_BASE_URL = "https://pro-api.coinmarketcap.com"
_LISTINGS_ENDPOINT = "/v1/cryptocurrency/listings/latest"


class CMCListing:
    """Parsed listing for a single cryptocurrency from CoinMarketCap."""

    __slots__ = (
        "symbol",
        "name",
        "cmc_rank",
        "market_cap",
        "volume_24h",
        "pct_change_1h",
        "pct_change_24h",
        "pct_change_7d",
        "volume_change_24h",
        "market_cap_dominance",
    )

    def __init__(self, raw: dict[str, Any]) -> None:
        self.symbol: str = raw.get("symbol", "")
        self.name: str = raw.get("name", "")
        self.cmc_rank: int = raw.get("cmc_rank", 9999)
        quote = raw.get("quote", {}).get("USD", {})
        self.market_cap: float = quote.get("market_cap", 0) or 0
        self.volume_24h: float = quote.get("volume_24h", 0) or 0
        self.pct_change_1h: float = quote.get("percent_change_1h", 0) or 0
        self.pct_change_24h: float = quote.get("percent_change_24h", 0) or 0
        self.pct_change_7d: float = quote.get("percent_change_7d", 0) or 0
        self.volume_change_24h: float = quote.get("volume_change_24h", 0) or 0
        self.market_cap_dominance: float = quote.get("market_cap_dominance", 0) or 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "cmc_rank": self.cmc_rank,
            "market_cap": self.market_cap,
            "volume_24h": self.volume_24h,
            "pct_change_1h": self.pct_change_1h,
            "pct_change_24h": self.pct_change_24h,
            "pct_change_7d": self.pct_change_7d,
            "volume_change_24h": self.volume_change_24h,
        }


class CoinMarketCapFeed:
    """Singleton feed that fetches CMC listings and computes momentum scores.

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[CoinMarketCapFeed | None] = None

    def __init__(self) -> None:
        self._listings: list[CMCListing] = []
        self._listings_by_symbol: dict[str, CMCListing] = {}
        self._last_fetch_time: float = 0
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False  # Set based on whether API key exists

    @classmethod
    def get_instance(cls) -> CoinMarketCapFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ------ BaseFeed protocol ------

    @property
    def name(self) -> str:
        return "coinmarketcap"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic fetching.  No-op if no API key configured."""
        from ctrade.settings import get_settings

        settings = get_settings()
        api_key = settings.feeds.coinmarketcap_api_key.get_secret_value()
        if not api_key:
            logger.info("CMC feed disabled — no API key configured")
            self._enabled = False
            return

        self._enabled = True
        self._is_running = True
        # Fetch immediately, then start background loop
        await self._fetch_listings(api_key)
        self._fetch_task = asyncio.create_task(self._polling_loop(api_key))
        logger.info(
            "CMC feed started (cache TTL=%ds, %d listings loaded)",
            _CACHE_TTL_SECONDS,
            len(self._listings),
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
        logger.info("CMC feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ------ Internal polling ------

    async def _polling_loop(self, api_key: str) -> None:
        while self._is_running:
            try:
                await asyncio.sleep(_CACHE_TTL_SECONDS)
                if self._is_running:
                    await self._fetch_listings(api_key)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("CMC polling error")

    async def _fetch_listings(self, api_key: str) -> None:
        """Fetch top 200 coins by market cap from CoinMarketCap."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{_CMC_BASE_URL}{_LISTINGS_ENDPOINT}",
                    params={"start": "1", "limit": "200", "convert": "USD"},
                    headers={
                        "X-CMC_PRO_API_KEY": api_key,
                        "Accept": "application/json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw_listings = data.get("data", [])
            listings = [CMCListing(item) for item in raw_listings]
            by_symbol = {listing.symbol: listing for listing in listings}

            self._listings = listings
            self._listings_by_symbol = by_symbol
            self._last_fetch_time = time.time()
            self._healthy = True
            logger.debug("CMC fetched %d listings", len(listings))

        except Exception:
            self._healthy = False
            logger.exception("Failed to fetch CMC listings")

    # ------ Public query methods ------

    def get_listing(self, symbol: str) -> CMCListing | None:
        """Get CMC listing for a base symbol (e.g. ``'BTC'``, not ``'BTC/USDT'``)."""
        return self._listings_by_symbol.get(symbol)

    def get_momentum_score(self, pair_symbol: str) -> float | None:
        """Compute a 0-1 momentum score for a trading pair.

        Returns ``None`` if CMC data is not available for this symbol.

        Scoring factors (sigmoid-normalised to 0-1):

        - pct_change_1h:  short-term momentum  (weight 0.20)
        - pct_change_24h: medium-term momentum  (weight 0.40)
        - pct_change_7d:  trend confirmation    (weight 0.20)
        - volume_surge:   volume vs median       (weight 0.20)
        """
        if not self._enabled or not self._listings:
            return None

        base_symbol = pair_symbol.split("/")[0]
        listing = self._listings_by_symbol.get(base_symbol)
        if listing is None:
            return None

        # Normalise each factor to 0-1 range using a sigmoid
        score_1h = self._pct_to_score(listing.pct_change_1h, scale=5.0)
        score_24h = self._pct_to_score(listing.pct_change_24h, scale=10.0)
        score_7d = self._pct_to_score(listing.pct_change_7d, scale=20.0)
        volume_score = self._volume_score(listing)

        composite = (
            0.20 * score_1h
            + 0.40 * score_24h
            + 0.20 * score_7d
            + 0.20 * volume_score
        )
        return round(max(0.0, min(1.0, composite)), 4)

    def get_volatility_info(self, pair_symbol: str) -> dict[str, Any] | None:
        """Get short-term volatility info for a trading pair.

        Returns key CMC metrics used for momentum-based pair ranking,
        or ``None`` if no CMC data is available.
        """
        if not self._enabled or not self._listings:
            return None

        base_symbol = pair_symbol.split("/")[0]
        listing = self._listings_by_symbol.get(base_symbol)
        if listing is None:
            return None

        return {
            "pct_change_1h": listing.pct_change_1h,
            "pct_change_24h": listing.pct_change_24h,
            "pct_change_7d": listing.pct_change_7d,
            "volume_change_24h": listing.volume_change_24h,
            "volume_24h": listing.volume_24h,
            "market_cap": listing.market_cap,
            "direction": (
                "bullish" if listing.pct_change_1h > 1.0
                else "bearish" if listing.pct_change_1h < -1.0
                else "neutral"
            ),
        }

    def get_top_gainers(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return top gainers by 24h percent change."""
        sorted_listings = sorted(
            self._listings,
            key=lambda x: x.pct_change_24h,
            reverse=True,
        )
        return self._listings_to_dicts(sorted_listings[:limit])

    def get_top_losers(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return top losers by 24h percent change."""
        sorted_listings = sorted(
            self._listings,
            key=lambda x: x.pct_change_24h,
        )
        return self._listings_to_dicts(sorted_listings[:limit])

    def get_screener_data(
        self,
        sort_by: str = "pct_change_24h",
        sort_dir: str = "desc",
        limit: int = 50,
        min_market_cap: float = 0,
        min_volume: float = 0,
    ) -> list[dict[str, Any]]:
        """Market screener: filter and sort CMC listings."""
        filtered = [
            item
            for item in self._listings
            if item.market_cap >= min_market_cap and item.volume_24h >= min_volume
        ]

        sort_key_map: dict[str, Any] = {
            "pct_change_1h": lambda x: x.pct_change_1h,
            "pct_change_24h": lambda x: x.pct_change_24h,
            "pct_change_7d": lambda x: x.pct_change_7d,
            "volume_24h": lambda x: x.volume_24h,
            "market_cap": lambda x: x.market_cap,
            "cmc_rank": lambda x: x.cmc_rank,
        }
        sort_fn = sort_key_map.get(sort_by, lambda x: x.pct_change_24h)
        sorted_listings = sorted(filtered, key=sort_fn, reverse=(sort_dir == "desc"))

        return self._listings_to_dicts(sorted_listings[:limit])

    # ------ Helpers ------

    def _listings_to_dicts(self, listings: list[CMCListing]) -> list[dict[str, Any]]:
        """Convert listings to dicts with momentum scores attached."""
        results: list[dict[str, Any]] = []
        for listing in listings:
            d = listing.to_dict()
            d["momentum_score"] = self.get_momentum_score(f"{listing.symbol}/USDT")
            results.append(d)
        return results

    @staticmethod
    def _pct_to_score(pct_change: float, scale: float) -> float:
        """Convert a percent change to a 0-1 score using a sigmoid.

        Mapping: 0% → 0.5, +scale → ~0.73, -scale → ~0.27, ±2×scale → ~0.88/0.12
        """
        return 1.0 / (1.0 + math.exp(-pct_change / scale))

    def _volume_score(self, listing: CMCListing) -> float:
        """Score a coin's volume relative to the median of all listings."""
        if not self._listings:
            return 0.5
        volumes = sorted(item.volume_24h for item in self._listings if item.volume_24h > 0)
        if not volumes:
            return 0.5
        median_vol = volumes[len(volumes) // 2]
        if median_vol <= 0:
            return 0.5
        ratio = listing.volume_24h / median_vol
        # Log-ratio: ratio=1 → 0.5, ratio=10 → ~0.73, ratio=0.1 → ~0.27
        return 1.0 / (1.0 + math.exp(-math.log(max(ratio, 0.01)) / 2.0))
