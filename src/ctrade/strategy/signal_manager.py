"""Signal store with optional database persistence.

Stores and retrieves trading signals.  Primary state is in-memory for fast
reads; new signals are written through to the database asynchronously.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, ClassVar

from ctrade.core.models import Signal
from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation

logger = logging.getLogger(__name__)


class SignalManager:
    """Stores and retrieves trading signals in memory."""

    _instance: ClassVar[SignalManager | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()
    MAX_SIGNALS = 500

    def __init__(self) -> None:
        self._signals: list[Signal] = []
        self._indicators_cache: dict[str, dict[str, Any]] = {}
        self._data_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SignalManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def add_signal(self, signal: Signal, indicators: dict[str, Any] | None = None) -> None:
        with self._data_lock:
            self._signals.append(signal)
            if len(self._signals) > self.MAX_SIGNALS:
                self._signals = self._signals[-self.MAX_SIGNALS:]
            if indicators and signal.pair_symbol:
                self._indicators_cache[signal.pair_symbol] = indicators
        # Write-through to DB (async, non-blocking)
        fire_and_forget(self._persist_signal(signal))

    def list_signals(
        self,
        symbol: str | None = None,
        action: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._data_lock:
            signals = list(reversed(self._signals))
            if symbol:
                signals = [s for s in signals if s.pair_symbol == symbol]
            if action:
                signals = [s for s in signals if s.action == action]
            return [self._signal_to_dict(s) for s in signals[:limit]]

    def get_latest(self, symbol: str) -> dict[str, Any] | None:
        with self._data_lock:
            for s in reversed(self._signals):
                if s.pair_symbol == symbol:
                    return self._signal_to_dict(s)
            return None

    def get_indicators(self, symbol: str) -> dict[str, Any] | None:
        with self._data_lock:
            return self._indicators_cache.get(symbol)

    # ---- Database persistence ----

    async def hydrate_from_db(self) -> None:
        """Load recent signals from database.  Called once at startup."""
        if not is_db_ready():
            logger.info("DB not available — SignalManager starting with empty state")
            return

        async def _load(session, resolver):
            from sqlalchemy import select
            from ctrade.db.mappers import orm_to_signal
            from ctrade.db.models import SignalModel

            stmt = (
                select(SignalModel)
                .order_by(SignalModel.created_at.desc())
                .limit(self.MAX_SIGNALS)
            )
            orm_signals = (await session.execute(stmt)).scalars().all()
            return [orm_to_signal(o, resolver) for o in reversed(orm_signals)]

        loaded = await run_db_operation(_load, description="hydrate SignalManager")
        if loaded:
            with self._data_lock:
                self._signals = loaded
            logger.info("Hydrated SignalManager from DB: %d signals", len(loaded))

    async def _persist_signal(self, signal: Signal) -> None:
        """Write-through: persist a single signal to the database."""
        async def _do(session, resolver):
            from ctrade.db.mappers import signal_to_orm
            orm_sig = await signal_to_orm(signal, resolver)
            session.add(orm_sig)
        await run_db_operation(_do, description="persist signal")

    # ---- Serialization ----

    @staticmethod
    def _signal_to_dict(s: Signal) -> dict[str, Any]:
        return {
            "id": str(s.id),
            "pair_symbol": s.pair_symbol,
            "action": s.action,
            "confidence": s.confidence,
            "technical_score": s.technical_score,
            "sentiment_score": s.sentiment_score,
            "onchain_score": s.onchain_score,
            "derivatives_score": s.derivatives_score,
            "strategy_name": s.strategy_name,
            "contributing_factors": s.contributing_factors,
            "created_at": s.created_at.isoformat(),
        }
