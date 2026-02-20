"""In-memory runtime configuration store.

Holds mutable copies of trading, risk, and strategy settings that can be
updated at runtime via the API.  Initialised from Pydantic AppSettings on
startup; changes persist until the server restarts.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from ctrade.security.vault import Vault
from ctrade.settings import AppSettings


@dataclass
class ExchangeEntry:
    """An exchange connection stored in memory."""

    id: str
    name: str
    exchange_type: str
    api_key_encrypted: bytes
    api_secret_encrypted: bytes
    passphrase_encrypted: bytes | None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_public_dict(self) -> dict[str, Any]:
        """Return a dict safe to expose via the API (no credentials)."""
        return {
            "id": self.id,
            "name": self.name,
            "exchange_type": self.exchange_type,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class RuntimeConfigStore:
    """Singleton store for mutable runtime configuration."""

    _instance: ClassVar[RuntimeConfigStore | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, settings: AppSettings) -> None:
        self._trading: dict[str, Any] = {
            "mode": settings.trading.mode,
            "default_quote_currency": settings.trading.default_quote_currency,
            "max_open_positions": settings.trading.max_open_positions,
            "order_timeout_seconds": settings.trading.order_timeout_seconds,
        }
        self._strategy: dict[str, Any] = {
            "active_strategy": settings.strategy.active_strategy,
            "technical_weight": settings.strategy.technical_weight,
            "sentiment_weight": settings.strategy.sentiment_weight,
            "onchain_weight": settings.strategy.onchain_weight,
            "entry_confidence_threshold": settings.strategy.entry_confidence_threshold,
            "exit_confidence_threshold": settings.strategy.exit_confidence_threshold,
        }
        self._risk: dict[str, Any] = {
            "max_position_pct": settings.risk.max_position_pct,
            "max_daily_loss_pct": settings.risk.max_daily_loss_pct,
            "max_drawdown_pct": settings.risk.max_drawdown_pct,
            "default_stop_loss_pct": settings.risk.default_stop_loss_pct,
            "default_take_profit_pct": settings.risk.default_take_profit_pct,
        }
        self._exchanges: list[ExchangeEntry] = []
        self._data_lock = threading.Lock()

    # ---- Singleton lifecycle ----

    @classmethod
    def initialize(cls, settings: AppSettings) -> RuntimeConfigStore:
        """Create the singleton instance from application settings."""
        with cls._lock:
            cls._instance = cls(settings)
            return cls._instance

    @classmethod
    def get(cls) -> RuntimeConfigStore:
        """Return the singleton instance.  Raises if not initialized."""
        if cls._instance is None:
            raise RuntimeError("RuntimeConfigStore not initialized. Call initialize() first.")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    # ---- Trading config ----

    def get_trading(self) -> dict[str, Any]:
        with self._data_lock:
            return dict(self._trading)

    def update_trading(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._data_lock:
            self._trading.update(updates)
            return dict(self._trading)

    # ---- Strategy config ----

    def get_strategy(self) -> dict[str, Any]:
        with self._data_lock:
            return dict(self._strategy)

    def update_strategy(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._data_lock:
            merged = {**self._strategy, **updates}
            # Validate weights sum to 1.0
            weights = (
                merged["technical_weight"]
                + merged["sentiment_weight"]
                + merged["onchain_weight"]
            )
            if abs(weights - 1.0) > 0.001:
                raise ValueError(
                    f"Strategy weights must sum to 1.0, got {weights:.3f}"
                )
            self._strategy.update(updates)
            return dict(self._strategy)

    # ---- Risk config ----

    def get_risk(self) -> dict[str, Any]:
        with self._data_lock:
            return dict(self._risk)

    def update_risk(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._data_lock:
            self._risk.update(updates)
            return dict(self._risk)

    # ---- Exchange management ----

    def list_exchanges(self) -> list[dict[str, Any]]:
        with self._data_lock:
            return [ex.to_public_dict() for ex in self._exchanges]

    def add_exchange(
        self,
        name: str,
        exchange_type: str,
        api_key: str,
        api_secret: str,
        vault: Vault,
        passphrase: str | None = None,
    ) -> dict[str, Any]:
        entry = ExchangeEntry(
            id=str(uuid.uuid4()),
            name=name,
            exchange_type=exchange_type,
            api_key_encrypted=vault.encrypt(api_key),
            api_secret_encrypted=vault.encrypt(api_secret),
            passphrase_encrypted=vault.encrypt(passphrase) if passphrase else None,
        )
        with self._data_lock:
            self._exchanges.append(entry)
            return entry.to_public_dict()

    def get_exchange_entry(self, exchange_id: str) -> ExchangeEntry | None:
        with self._data_lock:
            for ex in self._exchanges:
                if ex.id == exchange_id:
                    return ex
            return None

    def remove_exchange(self, exchange_id: str) -> bool:
        with self._data_lock:
            before = len(self._exchanges)
            self._exchanges = [ex for ex in self._exchanges if ex.id != exchange_id]
            return len(self._exchanges) < before
