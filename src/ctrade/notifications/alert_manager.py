"""Alert management system with optional database persistence.

In-memory alert configs and trigger history, with write-through to the
database when available.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar

from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation

logger = logging.getLogger(__name__)


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
    """Alert system singleton with DB write-through."""

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
        fire_and_forget(self._persist_alert_config(config))
        return self._config_to_dict(config)

    def list_alerts(self) -> list[dict[str, Any]]:
        with self._data_lock:
            return [self._config_to_dict(c) for c in self._configs]

    def delete_alert(self, alert_id: str) -> bool:
        with self._data_lock:
            before = len(self._configs)
            self._configs = [c for c in self._configs if c.id != alert_id]
            deleted = len(self._configs) < before
        if deleted:
            fire_and_forget(self._delete_alert_config_db(alert_id))
        return deleted

    def toggle_alert(self, alert_id: str) -> dict[str, Any] | None:
        with self._data_lock:
            for c in self._configs:
                if c.id == alert_id:
                    c.is_active = not c.is_active
                    result = self._config_to_dict(c)
                    fire_and_forget(self._update_alert_config_db(c))
                    return result
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
                    fire_and_forget(self._persist_trigger(trigger))
                    fire_and_forget(self._update_alert_config_db(config))
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
                    fire_and_forget(self._persist_trigger(trigger))
                    fire_and_forget(self._update_alert_config_db(config))
        return triggered

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._data_lock:
            return [self._trigger_to_dict(t) for t in reversed(self._history)][:limit]

    # ---- Database persistence ----

    async def hydrate_from_db(self) -> None:
        """Load alert configs and history from database."""
        if not is_db_ready():
            logger.info("DB not available — AlertManager starting with empty state")
            return

        async def _load(session, _resolver):
            from sqlalchemy import select
            from ctrade.db.mappers import orm_to_alert_config, orm_to_alert_trigger
            from ctrade.db.models import AlertConfigModel, AlertHistoryModel

            configs_result = await session.execute(select(AlertConfigModel))
            configs = [orm_to_alert_config(c) for c in configs_result.scalars().all()]

            history_stmt = (
                select(AlertHistoryModel)
                .order_by(AlertHistoryModel.created_at.desc())
                .limit(200)
            )
            history_result = await session.execute(history_stmt)
            history = [
                orm_to_alert_trigger(h)
                for h in reversed(history_result.scalars().all())
            ]

            return configs, history

        loaded = await run_db_operation(_load, description="hydrate AlertManager")
        if loaded:
            configs, history = loaded
            with self._data_lock:
                self._configs = configs
                self._history = history
            logger.info(
                "Hydrated AlertManager: %d configs, %d history entries",
                len(configs),
                len(history),
            )

    async def _persist_alert_config(self, config: AlertConfig) -> None:
        """Write-through: persist an alert config."""
        async def _do(session, _resolver):
            from ctrade.db.mappers import alert_config_to_orm
            orm = alert_config_to_orm(config)
            await session.merge(orm)
        await run_db_operation(_do, description="persist alert config")

    async def _update_alert_config_db(self, config: AlertConfig) -> None:
        """Write-through: update an existing alert config (e.g. toggle)."""
        await self._persist_alert_config(config)

    async def _delete_alert_config_db(self, alert_id: str) -> None:
        """Write-through: delete an alert config from the database."""
        async def _do(session, _resolver):
            from sqlalchemy import delete
            from ctrade.db.models import AlertConfigModel
            try:
                uid = uuid.UUID(alert_id)
            except ValueError:
                return
            await session.execute(
                delete(AlertConfigModel).where(AlertConfigModel.id == uid)
            )
        await run_db_operation(_do, description="delete alert config")

    async def _persist_trigger(self, trigger: AlertTrigger) -> None:
        """Write-through: persist a triggered alert to history."""
        async def _do(session, _resolver):
            from ctrade.db.mappers import alert_trigger_to_orm
            orm = alert_trigger_to_orm(trigger)
            session.add(orm)
        await run_db_operation(_do, description="persist alert trigger")

    # ---- Serialization ----

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
