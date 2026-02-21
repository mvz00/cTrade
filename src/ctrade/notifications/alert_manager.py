"""In-memory alert management system."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass
class AlertConfig:
    """An alert configuration."""
    id: str
    alert_type: str  # price_above, price_below, signal_buy, signal_sell, pnl_above, pnl_below
    symbol: str
    value: float
    message: str | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AlertTrigger:
    """A triggered alert record."""
    id: str
    alert_id: str
    alert_type: str
    symbol: str
    message: str
    triggered_value: float
    triggered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AlertManager:
    """In-memory alert system singleton."""

    _instance: ClassVar[AlertManager | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._configs: list[AlertConfig] = []
        self._history: list[AlertTrigger] = []
        self._data_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> AlertManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    def create_alert(
        self,
        alert_type: str,
        symbol: str,
        value: float,
        message: str | None = None,
    ) -> dict[str, Any]:
        config = AlertConfig(
            id=str(uuid.uuid4()),
            alert_type=alert_type,
            symbol=symbol,
            value=value,
            message=message,
        )
        with self._data_lock:
            self._configs.append(config)
            return self._config_to_dict(config)

    def list_alerts(self) -> list[dict[str, Any]]:
        with self._data_lock:
            return [self._config_to_dict(c) for c in self._configs]

    def delete_alert(self, alert_id: str) -> bool:
        with self._data_lock:
            before = len(self._configs)
            self._configs = [c for c in self._configs if c.id != alert_id]
            return len(self._configs) < before

    def toggle_alert(self, alert_id: str) -> dict[str, Any] | None:
        with self._data_lock:
            for c in self._configs:
                if c.id == alert_id:
                    c.is_active = not c.is_active
                    return self._config_to_dict(c)
            return None

    def check_price(self, symbol: str, price: float) -> list[dict[str, Any]]:
        """Check price alerts and trigger matching ones."""
        triggered: list[dict[str, Any]] = []
        with self._data_lock:
            for config in self._configs:
                if not config.is_active or config.symbol != symbol:
                    continue
                should_trigger = False
                if config.alert_type == "price_above" and price >= config.value:
                    should_trigger = True
                elif config.alert_type == "price_below" and price <= config.value:
                    should_trigger = True

                if should_trigger:
                    trigger = AlertTrigger(
                        id=str(uuid.uuid4()),
                        alert_id=config.id,
                        alert_type=config.alert_type,
                        symbol=symbol,
                        message=config.message or f"{config.alert_type}: {symbol} @ ${price:.2f}",
                        triggered_value=price,
                    )
                    self._history.append(trigger)
                    triggered.append(self._trigger_to_dict(trigger))
                    config.is_active = False  # One-shot trigger
        return triggered

    def check_signal(self, symbol: str, action: str) -> list[dict[str, Any]]:
        """Check signal alerts."""
        triggered: list[dict[str, Any]] = []
        with self._data_lock:
            for config in self._configs:
                if not config.is_active or config.symbol != symbol:
                    continue
                should_trigger = False
                if config.alert_type == "signal_buy" and action == "BUY":
                    should_trigger = True
                elif config.alert_type == "signal_sell" and action == "SELL":
                    should_trigger = True

                if should_trigger:
                    trigger = AlertTrigger(
                        id=str(uuid.uuid4()),
                        alert_id=config.id,
                        alert_type=config.alert_type,
                        symbol=symbol,
                        message=config.message or f"Signal {action} for {symbol}",
                        triggered_value=0.0,
                    )
                    self._history.append(trigger)
                    triggered.append(self._trigger_to_dict(trigger))
                    config.is_active = False
        return triggered

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._data_lock:
            return [self._trigger_to_dict(t) for t in reversed(self._history)][:limit]

    @staticmethod
    def _config_to_dict(c: AlertConfig) -> dict[str, Any]:
        return {
            "id": c.id,
            "alert_type": c.alert_type,
            "symbol": c.symbol,
            "value": c.value,
            "message": c.message,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat(),
        }

    @staticmethod
    def _trigger_to_dict(t: AlertTrigger) -> dict[str, Any]:
        return {
            "id": t.id,
            "alert_id": t.alert_id,
            "alert_type": t.alert_type,
            "symbol": t.symbol,
            "message": t.message,
            "triggered_value": t.triggered_value,
            "triggered_at": t.triggered_at.isoformat(),
        }
