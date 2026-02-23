"""On-chain metrics feed — fetches blockchain data from free APIs.

Sources (all free, no auth required):
- blockchain.info (BTC): hash rate, mempool size, daily tx count
- CoinGecko market data (all coins): volume, market cap, supply

Follows the same singleton/BaseFeed pattern as :class:`CoinMarketCapFeed`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, ClassVar

import httpx

from ctrade.analysis.onchain.engine import OnChainEngine
from ctrade.core.models import OnChainMetric

logger = logging.getLogger(__name__)

# ---- API endpoints (all free, no key required) ----

_BLOCKCHAIN_INFO_STATS = "https://api.blockchain.info/stats"
_BLOCKCHAIN_INFO_MEMPOOL = "https://api.blockchain.info/mempool"
_COINGECKO_MARKET_URL = "https://api.coingecko.com/api/v3/coins/markets"

# Map of CoinGecko IDs to our ticker symbols
_CG_ID_MAP: dict[str, str] = {
    "bitcoin": "BTC",
    "ethereum": "ETH",
    "solana": "SOL",
    "binancecoin": "BNB",
    "ripple": "XRP",
    "cardano": "ADA",
    "dogecoin": "DOGE",
    "polkadot": "DOT",
    "avalanche-2": "AVAX",
    "chainlink": "LINK",
    "tron": "TRX",
    "litecoin": "LTC",
    "uniswap": "UNI",
    "stellar": "XLM",
    "cosmos": "ATOM",
    "near": "NEAR",
    "sui": "SUI",
    "aptos": "APT",
}

_CG_IDS_CSV = ",".join(_CG_ID_MAP.keys())


class OnChainFeed:
    """Singleton feed that fetches on-chain metrics from free APIs.

    Implements the ``BaseFeed`` protocol (start / stop / healthcheck / name).
    """

    _instance: ClassVar[OnChainFeed | None] = None

    def __init__(self) -> None:
        self._metrics: dict[str, list[OnChainMetric]] = {}  # asset -> metrics
        self._is_running: bool = False
        self._fetch_task: asyncio.Task[None] | None = None
        self._healthy: bool = False
        self._enabled: bool = False
        self._last_fetch_time: float = 0
        self._engine = OnChainEngine()
        self._poll_interval: int = 900

    @classmethod
    def get_instance(cls) -> OnChainFeed:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ---- BaseFeed protocol ----

    @property
    def name(self) -> str:
        return "onchain"

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> None:
        """Start periodic fetching.  Always enabled (free APIs, no key needed)."""
        from ctrade.settings import get_settings

        settings = get_settings()
        self._poll_interval = settings.feeds.onchain_poll_interval_seconds

        self._enabled = True
        self._is_running = True
        # Start background polling — first fetch happens after a short delay
        # so the server can begin accepting healthcheck requests immediately.
        self._fetch_task = asyncio.create_task(self._polling_loop())
        logger.info("On-chain feed started (poll interval=%ds, first fetch in ~10s)", self._poll_interval)

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
        logger.info("On-chain feed stopped")

    async def healthcheck(self) -> bool:
        return self._healthy

    # ---- Public query methods ----

    def get_onchain_score(self, pair_symbol: str) -> float | None:
        """Get composite on-chain score (0-1) for a trading pair."""
        if not self._enabled:
            return None

        base_symbol = pair_symbol.split("/")[0]
        metrics = self._metrics.get(base_symbol, [])
        if not metrics:
            return None

        return self._engine.compute_score(metrics)

    def get_metrics(self, asset: str, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent on-chain metrics for display."""
        metrics = self._metrics.get(asset, [])
        sorted_m = sorted(metrics, key=lambda m: m.timestamp, reverse=True)[:limit]
        return [
            {
                "metric_name": m.metric_name,
                "metric_value": float(m.metric_value),
                "source": m.source,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in sorted_m
        ]

    def get_all_scores(self) -> dict[str, float]:
        """Get on-chain scores for all tracked assets."""
        result: dict[str, float] = {}
        for asset, metrics in self._metrics.items():
            if metrics:
                result[asset] = self._engine.compute_score(metrics)
        return result

    def get_contributing_factors(self, pair_symbol: str) -> dict[str, Any]:
        """Get detailed contributing factors for a pair."""
        base_symbol = pair_symbol.split("/")[0]
        metrics = self._metrics.get(base_symbol, [])
        return self._engine.compute_contributing_factors(metrics)

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
            "metrics_count": sum(len(m) for m in self._metrics.values()),
            "assets_tracked": len(self._metrics),
        }

    # ---- Internal polling ----

    async def _polling_loop(self) -> None:
        # Short initial delay so the server can start accepting requests first
        try:
            await asyncio.sleep(10)
            if self._is_running:
                await self._fetch_all_sources()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("On-chain feed initial fetch error")

        while self._is_running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._is_running:
                    await self._fetch_all_sources()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("On-chain feed polling error")

    async def _fetch_all_sources(self) -> None:
        """Fetch from all sources and store metrics."""
        new_metrics: list[OnChainMetric] = []

        results = await asyncio.gather(
            self._fetch_blockchain_info(),
            self._fetch_coingecko_market(),
            return_exceptions=True,
        )

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                source_name = ["blockchain.info", "coingecko"][i]
                logger.warning("Failed to fetch %s: %s", source_name, result)
            elif isinstance(result, list):
                new_metrics.extend(result)

        if not new_metrics:
            logger.debug("No new on-chain metrics fetched")
            return

        # Store metrics
        for metric in new_metrics:
            self._metrics.setdefault(metric.asset, []).append(metric)

        # Trim old metrics (keep last 100 per asset)
        for asset in self._metrics:
            if len(self._metrics[asset]) > 100:
                self._metrics[asset] = sorted(
                    self._metrics[asset],
                    key=lambda m: m.timestamp,
                    reverse=True,
                )[:100]

        self._last_fetch_time = time.time()
        self._healthy = True

        # Fire-and-forget persist
        self._persist_metrics(new_metrics)

        logger.debug(
            "On-chain feed: stored %d metrics across %d assets",
            len(new_metrics),
            len(self._metrics),
        )

    def _persist_metrics(self, metrics: list[OnChainMetric]) -> None:
        """Fire-and-forget persist on-chain metrics to DB."""
        from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation

        if not is_db_ready():
            return

        async def _do(session, _resolver):
            from ctrade.db.models import OnChainMetricModel

            for m in metrics:
                orm = OnChainMetricModel(
                    asset=m.asset,
                    metric_name=m.metric_name,
                    metric_value=float(m.metric_value),
                    source=m.source,
                )
                session.add(orm)

        fire_and_forget(run_db_operation(_do, description="persist on-chain metrics"))

    # ---- Source fetchers ----

    async def _fetch_blockchain_info(self) -> list[OnChainMetric]:
        """Fetch BTC network stats from blockchain.info (free, no key)."""
        metrics: list[OnChainMetric] = []
        now = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Fetch stats
                resp = await client.get(_BLOCKCHAIN_INFO_STATS)
                resp.raise_for_status()
                stats = resp.json()

                # Fetch mempool (separate endpoint)
                try:
                    resp2 = await client.get(_BLOCKCHAIN_INFO_MEMPOOL)
                    resp2.raise_for_status()
                    mempool = resp2.json()
                except Exception:
                    mempool = None

            # Hash rate (in TH/s from API, convert to H/s for normalization)
            hash_rate = stats.get("hash_rate", 0)
            if hash_rate > 0:
                metrics.append(OnChainMetric(
                    asset="BTC",
                    metric_name="hash_rate",
                    metric_value=Decimal(str(hash_rate * 1e9)),  # TH/s -> H/s (approx)
                    source="blockchain.info",
                    timestamp=now,
                ))

            # Transaction count (24h estimated from n_tx)
            n_tx = stats.get("n_tx", 0)
            if n_tx > 0:
                metrics.append(OnChainMetric(
                    asset="BTC",
                    metric_name="tx_count_24h",
                    metric_value=Decimal(str(n_tx)),
                    source="blockchain.info",
                    timestamp=now,
                ))

            # Market cap in USD (from API)
            market_cap = stats.get("market_price_usd", 0) * stats.get("totalbc", 0) / 1e8
            if market_cap > 0:
                metrics.append(OnChainMetric(
                    asset="BTC",
                    metric_name="market_cap",
                    metric_value=Decimal(str(market_cap)),
                    source="blockchain.info",
                    timestamp=now,
                ))

            # Mempool size
            if mempool and isinstance(mempool, dict):
                mempool_size = mempool.get("count", 0)
                if mempool_size > 0:
                    metrics.append(OnChainMetric(
                        asset="BTC",
                        metric_name="mempool_size",
                        metric_value=Decimal(str(mempool_size)),
                        source="blockchain.info",
                        timestamp=now,
                    ))

        except Exception as exc:
            logger.debug("blockchain.info fetch error: %s", exc)
            raise

        return metrics

    async def _fetch_coingecko_market(self) -> list[OnChainMetric]:
        """Fetch market data from CoinGecko (free, no key required)."""
        metrics: list[OnChainMetric] = []
        now = datetime.now(timezone.utc)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    _COINGECKO_MARKET_URL,
                    params={
                        "vs_currency": "usd",
                        "ids": _CG_IDS_CSV,
                        "order": "market_cap_desc",
                        "per_page": "30",
                        "page": "1",
                        "sparkline": "false",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            for coin in data:
                cg_id = coin.get("id", "")
                symbol = _CG_ID_MAP.get(cg_id)
                if not symbol:
                    continue

                # 24h volume
                volume = coin.get("total_volume", 0)
                if volume and volume > 0:
                    metrics.append(OnChainMetric(
                        asset=symbol,
                        metric_name="volume_24h",
                        metric_value=Decimal(str(volume)),
                        source="coingecko",
                        timestamp=now,
                    ))

                # Market cap
                mcap = coin.get("market_cap", 0)
                if mcap and mcap > 0:
                    metrics.append(OnChainMetric(
                        asset=symbol,
                        metric_name="market_cap",
                        metric_value=Decimal(str(mcap)),
                        source="coingecko",
                        timestamp=now,
                    ))

                # Circulating supply percentage
                total_supply = coin.get("total_supply")
                circ_supply = coin.get("circulating_supply")
                if total_supply and circ_supply and total_supply > 0:
                    pct = circ_supply / total_supply
                    metrics.append(OnChainMetric(
                        asset=symbol,
                        metric_name="circulating_supply_pct",
                        metric_value=Decimal(str(round(pct, 4))),
                        source="coingecko",
                        timestamp=now,
                    ))

        except Exception as exc:
            logger.debug("CoinGecko market fetch error: %s", exc)
            raise

        return metrics
