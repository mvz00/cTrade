"""In-memory signal store for generated trading signals."""

from __future__ import annotations

import threading
from typing import Any, ClassVar

from ctrade.core.models import Signal


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
            "strategy_name": s.strategy_name,
            "contributing_factors": s.contributing_factors,
            "created_at": s.created_at.isoformat(),
        }
