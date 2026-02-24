"""Periodic portfolio snapshot task — persists per-exchange values to DB.

Runs as a background asyncio task.  Every ``interval_seconds`` (default
300 = 5 minutes) it:

1. Fetches portfolio for each configured exchange via
   ``MarketDataProvider.fetch_per_exchange_portfolios()``.
2. Persists a ``PortfolioSnapshotModel`` row per exchange to the database.

The task is resilient — individual iteration failures are logged and do
not kill the loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL = 300  # 5 minutes


async def run_snapshot_loop(interval_seconds: int = _DEFAULT_INTERVAL) -> None:
    """Run indefinitely, snapshotting per-exchange portfolios at a fixed
    interval.

    Parameters
    ----------
    interval_seconds:
        Seconds between snapshots (default 300 = 5 min).
    """
    logger.info(
        "Portfolio snapshot task started (interval=%ds)", interval_seconds,
    )

    # Small initial delay so the rest of the app finishes startup.
    await asyncio.sleep(10)

    while True:
        try:
            await _take_snapshot()
        except asyncio.CancelledError:
            logger.info("Portfolio snapshot task cancelled — exiting")
            return
        except Exception:
            logger.exception("Portfolio snapshot iteration failed")

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("Portfolio snapshot task cancelled during sleep — exiting")
            return


async def _take_snapshot() -> None:
    """Single snapshot iteration: fetch + persist."""
    from ctrade.core.config_store import RuntimeConfigStore
    from ctrade.db.engine import _session_factory
    from ctrade.db.models import PortfolioSnapshotModel
    from ctrade.db.repositories.portfolio import PortfolioRepository
    from ctrade.exchange.market_data import MarketDataProvider

    if _session_factory is None:
        logger.debug("Snapshot skipped — database not available")
        return

    try:
        store = RuntimeConfigStore.get()
        trading_mode = store.get_trading().get("mode", "paper")
    except RuntimeError:
        logger.debug("Snapshot skipped — config store not ready")
        return

    market = MarketDataProvider.get_instance()
    per_exchange = await market.fetch_per_exchange_portfolios()

    if not per_exchange:
        logger.debug("Snapshot skipped — no exchange portfolios returned")
        return

    now = datetime.now(timezone.utc)

    async with _session_factory() as session:
        repo = PortfolioRepository(session)
        count = 0

        for ex_name, portfolio in per_exchange.items():
            # Resolve the exchange_id from config store
            exchange_id = _resolve_exchange_id(store, ex_name)
            if exchange_id is None:
                logger.warning(
                    "Snapshot: could not resolve exchange_id for '%s'", ex_name,
                )
                continue

            snapshot = PortfolioSnapshotModel(
                time=now,
                exchange_id=exchange_id,
                trading_mode=trading_mode,
                total_value_usd=portfolio["total_value_usd"],
                cash_balance=portfolio["cash_balance"],
                open_positions=portfolio.get("open_positions", 0),
                unrealized_pnl=portfolio.get("unrealized_pnl", 0.0),
            )
            await repo.create(snapshot)
            count += 1

        await session.commit()
        logger.info(
            "Portfolio snapshot saved: %d exchange(s), mode=%s",
            count, trading_mode,
        )


def _resolve_exchange_id(store: object, exchange_name: str) -> uuid.UUID | None:
    """Look up the exchange UUID from RuntimeConfigStore by name."""
    from ctrade.core.config_store import RuntimeConfigStore

    typed_store: RuntimeConfigStore = store  # type: ignore[assignment]
    for ex in typed_store.list_exchanges():
        if ex.get("name", "").lower() == exchange_name.lower():
            raw = ex.get("id")
            if isinstance(raw, uuid.UUID):
                return raw
            if raw:
                return uuid.UUID(str(raw))
    return None
