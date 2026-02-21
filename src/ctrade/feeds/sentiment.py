"""Sentiment data feed — fetches text from free sources and classifies with FinBERT.

Sources (all free, no auth required):
- CryptoCompare News API
- CoinGecko Trending
- Reddit r/cryptocurrency (public JSON)

Follows the same singleton/BaseFeed pattern as :class:`CoinMarketCapFeed`.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx

from ctrade.analysis.sentiment.classifier import SentimentClassifier
from ctrade.analysis.sentiment.engine import SentimentEngine
from ctrade.core.enums import SentimentLabel
from ctrade.core.models import SentimentDataPoint

logger = logging.getLogger(__name__)

# ---- API endpoints (all free, no key required) ----

_CRYPTOCOMPARE_NEWS_URL = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
_COINGECKO_TRENDING_URL = "https://api.coingecko.com/api/v3/search/trending"
_REDDIT_HOT_URL = "https://www.reddit.com/r/cryptocurrency/hot.json?limit=25"

# ---- Asset alias map: human names -> ticker symbols ----

ASSET_ALIASES: dict[str, str] = {
    "bitcoin": "BTC",
    "btc": "BTC",
    "ethereum": "ETH",
    "eth": "ETH",
    "solana": "SOL",
    "sol": "SOL",
    "binance": "BNB",
    "bnb": "BNB",
    "ripple": "XRP",
    "xrp": "XRP",
    "cardano": "ADA",
    "ada": "ADA",
    "dogecoin": "DOGE",
    "doge": "DOGE",
    "polkadot": "DOT",
    "dot": "DOT",
    "avalanche": "AVAX",
    "avax": "AVAX",
    "chainlink": "LINK",
    "link": "LINK",
    "polygon": "MATIC",
    "matic": "MATIC",
    "litecoin": "LTC",
    "ltc": "LTC",
    "tron": "TRX",
    "trx": "TRX",
    "shiba": "SHIB",
    "shib": "SHIB",
    "uniswap": "UNI",
    "uni": "UNI",
    "stellar": "XLM",
    "xlm": "XLM",
    "cosmos": "ATOM",
    "atom": "ATOM",
    "near": "NEAR",
    "sui": "SUI",
    "aptos": "APT",
    "apt": "APT",
    "arbitrum": "ARB",
    "arb": "ARB",
    "optimism": "OP",
    "pepe": "PEPE",
}


@dataclass
class RawTextItem:
    """Pre-classification text item from a feed source."""

    text: str
    source: str
    source_id: str
    assets: list[str]  # detected asset symbols


class SentimentFeed:
    """Singleton feed that fetches news/social text and classifies sentiment.

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[SentimentFeed | None] = None

    def __init__(self) -> None:
        self._data_points: dict[str, list[SentimentDataPoint]] = {}  # asset -> points
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False
        self._last_fetch_time: float = 0
        self._classifier = SentimentClassifier.get_instance()
        self._engine = SentimentEngine()
        self._seen_ids: set[str] = set()  # dedup source_ids
        self._poll_interval: int = 300

    @classmethod
    def get_instance(cls) -> SentimentFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ---- BaseFeed protocol ----

    @property
    def name(self) -> str:
        return "sentiment"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic fetching.  Always enabled (free APIs, no key needed)."""
        from ctrade.settings import get_settings

        settings = get_settings()
        self._poll_interval = settings.feeds.news_poll_interval_seconds

        self._enabled = True
        self._is_running = True
        # Fetch immediately, then start background loop
        await self._fetch_all_sources()
        self._fetch_task = asyncio.create_task(self._polling_loop())
        logger.info(
            "Sentiment feed started (poll interval=%ds, %d data points loaded)",
            self._poll_interval,
            sum(len(pts) for pts in self._data_points.values()),
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
        logger.info("Sentiment feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ---- Public query methods ----

    def get_sentiment_score(self, pair_symbol: str) -> float | None:
        """Get composite sentiment score (0-1) for a trading pair."""
        if not self._enabled:
            return None

        base_symbol = pair_symbol.split("/")[0]
        data_points = self._data_points.get(base_symbol, [])
        if not data_points:
            return None

        return self._engine.compute_score(data_points)

    def get_recent_data(self, asset: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent sentiment data points for timeline display."""
        points = self._data_points.get(asset, [])
        sorted_pts = sorted(points, key=lambda p: p.timestamp, reverse=True)[:limit]
        return [
            {
                "source": p.source,
                "text": p.raw_text[:200] if p.raw_text else "",
                "label": p.label.value,
                "score": p.score,
                "model": p.model_used,
                "timestamp": p.timestamp.isoformat(),
            }
            for p in sorted_pts
        ]

    def get_all_scores(self) -> dict[str, float]:
        """Get sentiment scores for all tracked assets."""
        result: dict[str, float] = {}
        for asset, points in self._data_points.items():
            if points:
                result[asset] = self._engine.compute_score(points)
        return result

    def get_contributing_factors(self, pair_symbol: str) -> dict[str, Any]:
        """Get detailed contributing factors for a pair."""
        base_symbol = pair_symbol.split("/")[0]
        data_points = self._data_points.get(base_symbol, [])
        return self._engine.compute_contributing_factors(data_points)

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
            "data_points": sum(len(pts) for pts in self._data_points.values()),
            "assets_tracked": len(self._data_points),
            "classifier_model": self._classifier.model_name,
            "using_fallback": self._classifier.using_fallback,
        }

    # ---- Internal polling ----

    async def _polling_loop(self) -> None:
        while self._is_running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._is_running:
                    await self._fetch_all_sources()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Sentiment feed polling error")

    async def _fetch_all_sources(self) -> None:
        """Fetch from all sources, classify, and store."""
        raw_items: list[RawTextItem] = []

        # Fetch all sources in parallel
        results = await asyncio.gather(
            self._fetch_cryptocompare(),
            self._fetch_coingecko_trending(),
            self._fetch_reddit(),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                source_name = ["cryptocompare", "coingecko", "reddit"][i]
                logger.warning("Failed to fetch %s: %s", source_name, result)
            elif isinstance(result, list):
                raw_items.extend(result)

        if not raw_items:
            logger.debug("No new sentiment items fetched")
            return

        # Filter out already-seen items
        new_items = []
        for item in raw_items:
            if item.source_id not in self._seen_ids:
                self._seen_ids.add(item.source_id)
                new_items.append(item)

        if not new_items:
            self._last_fetch_time = time.time()
            self._healthy = True
            return

        # Classify all texts in batch
        texts = [item.text for item in new_items]
        classifications = self._classifier.classify_batch(texts)

        # Create data points and store
        for item, (label, score) in zip(new_items, classifications):
            for asset in item.assets:
                dp = SentimentDataPoint(
                    asset=asset,
                    source=item.source,
                    source_id=item.source_id,
                    raw_text=item.text[:500],
                    label=label,
                    score=score,
                    model_used=self._classifier.model_name,
                )
                self._data_points.setdefault(asset, []).append(dp)

        # Trim old data points (keep last 200 per asset)
        for asset in self._data_points:
            if len(self._data_points[asset]) > 200:
                self._data_points[asset] = sorted(
                    self._data_points[asset],
                    key=lambda p: p.timestamp,
                    reverse=True,
                )[:200]

        # Cap seen IDs cache
        if len(self._seen_ids) > 5000:
            self._seen_ids = set(list(self._seen_ids)[-2500:])

        self._last_fetch_time = time.time()
        self._healthy = True

        # Fire-and-forget persist new data points
        self._persist_new_points(new_items, classifications)

        logger.debug(
            "Sentiment feed: classified %d new items across %d assets",
            len(new_items),
            len(self._data_points),
        )

    def _persist_new_points(
        self,
        items: list[RawTextItem],
        classifications: list[tuple[SentimentLabel, float]],
    ) -> None:
        """Fire-and-forget persist new sentiment data points to DB."""
        from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation

        if not is_db_ready():
            return

        async def _do(session, _resolver):
            from ctrade.db.models import SentimentDataModel

            for item, (label, score) in zip(items, classifications):
                for asset in item.assets:
                    orm = SentimentDataModel(
                        asset=asset,
                        source=item.source,
                        source_id=item.source_id,
                        raw_text=item.text[:500],
                        sentiment_label=label.value,
                        sentiment_score=score,
                        model_used=self._classifier.model_name,
                    )
                    session.add(orm)

        fire_and_forget(run_db_operation(_do, description="persist sentiment data"))

    # ---- Source fetchers ----

    async def _fetch_cryptocompare(self) -> list[RawTextItem]:
        """Fetch news from CryptoCompare (free, no key required)."""
        items: list[RawTextItem] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(_CRYPTOCOMPARE_NEWS_URL)
                resp.raise_for_status()
                data = resp.json()

            for article in data.get("Data", [])[:30]:
                title = article.get("title", "")
                body = article.get("body", "")
                text = f"{title}. {body[:300]}" if body else title
                if not text.strip():
                    continue

                source_id = f"cc_{article.get('id', '')}"
                categories = article.get("categories", "")
                assets = self._extract_assets(text + " " + categories)

                if assets:
                    items.append(RawTextItem(
                        text=text[:500],
                        source="cryptocompare",
                        source_id=source_id,
                        assets=assets,
                    ))
        except Exception as exc:
            logger.debug("CryptoCompare fetch error: %s", exc)
            raise

        return items

    async def _fetch_coingecko_trending(self) -> list[RawTextItem]:
        """Fetch trending coins from CoinGecko (free, no key required)."""
        items: list[RawTextItem] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(_COINGECKO_TRENDING_URL)
                resp.raise_for_status()
                data = resp.json()

            for coin_wrapper in data.get("coins", []):
                coin = coin_wrapper.get("item", {})
                name = coin.get("name", "")
                symbol = coin.get("symbol", "").upper()
                score = coin.get("score", 0)

                if not symbol:
                    continue

                # Trending = positive sentiment signal
                text = f"{name} ({symbol}) is trending on CoinGecko, ranked #{score + 1} in trending searches"
                source_id = f"cg_trend_{symbol}_{int(time.time()) // 3600}"

                items.append(RawTextItem(
                    text=text,
                    source="coingecko",
                    source_id=source_id,
                    assets=[symbol],
                ))
        except Exception as exc:
            logger.debug("CoinGecko fetch error: %s", exc)
            raise

        return items

    async def _fetch_reddit(self) -> list[RawTextItem]:
        """Fetch hot posts from r/cryptocurrency (public JSON, no auth).

        Reddit increasingly blocks unauthenticated JSON requests (403).
        We try the ``old.reddit.com`` domain first as a more reliable
        alternative, then fall back to ``www.reddit.com``.  If both fail
        we log a warning and return an empty list instead of raising so
        the other two sources can still contribute data.
        """
        _REDDIT_URLS = [
            "https://old.reddit.com/r/cryptocurrency/hot.json?limit=25",
            _REDDIT_HOT_URL,
        ]
        items: list[RawTextItem] = []
        last_exc: Exception | None = None

        for url in _REDDIT_URLS:
            try:
                async with httpx.AsyncClient(
                    timeout=15.0,
                    headers={
                        "User-Agent": "cTrade:v0.1.0 (by /u/cTrade_bot)",
                        "Accept": "application/json",
                    },
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = post.get("title", "")
                    selftext = post.get("selftext", "")[:200]
                    post_id = post.get("id", "")

                    if not title:
                        continue

                    text = f"{title}. {selftext}" if selftext else title
                    source_id = f"reddit_{post_id}"
                    assets = self._extract_assets(text)

                    if assets:
                        items.append(RawTextItem(
                            text=text[:500],
                            source="reddit",
                            source_id=source_id,
                            assets=assets,
                        ))
                return items  # success — stop trying other URLs
            except Exception as exc:
                last_exc = exc
                logger.debug("Reddit fetch failed (%s): %s", url, exc)
                continue

        # All Reddit URLs failed — degrade gracefully
        logger.info(
            "Reddit source unavailable (all URLs returned errors). "
            "Sentiment will rely on CryptoCompare and CoinGecko. Last error: %s",
            last_exc,
        )
        return []

    # ---- Helpers ----

    @staticmethod
    def _extract_assets(text: str) -> list[str]:
        """Extract crypto asset symbols from text using alias matching."""
        found: set[str] = set()
        lower = text.lower()

        # Check for known aliases / coin names
        for alias, symbol in ASSET_ALIASES.items():
            # Word boundary match
            if re.search(rf"\b{re.escape(alias)}\b", lower):
                found.add(symbol)

        # Also check for ticker symbols in uppercase (e.g. $BTC, BTC/USDT)
        for match in re.finditer(r"\$?([A-Z]{2,6})(?:/[A-Z]{2,6})?", text):
            ticker = match.group(1)
            if ticker in {v for v in ASSET_ALIASES.values()}:
                found.add(ticker)

        return list(found)
