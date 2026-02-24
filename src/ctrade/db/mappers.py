"""Bidirectional mappers between domain dataclasses and ORM models.

Domain models (core/models.py) use string identifiers (pair_symbol, exchange_name).
ORM models (db/models.py) use UUID foreign keys (pair_id, exchange_id).
The PairResolver bridges this gap with a cached lookup + auto-vivify.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ctrade.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    PositionStatus,
    SignalAction,
    TradingMode,
)
from ctrade.core.models import Order, Position, Signal
from ctrade.db.models import (
    AlertConfigModel,
    AlertHistoryModel,
    AuditLogModel,
    ExchangeModel,
    OrderModel,
    PositionModel,
    PortfolioSnapshotModel,
    SignalModel,
    TradingPairModel,
)

# NOTE: AlertConfig and AlertTrigger are imported lazily inside the functions
# that use them, to avoid a circular import:
#   alert_manager -> db.persistence -> db.mappers -> alert_manager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(val: Decimal | float | None) -> float | None:
    """Convert Decimal to float for ORM storage.  None stays None."""
    if val is None:
        return None
    return float(val)


def _to_decimal(val: float | None) -> Decimal | None:
    """Convert ORM float to Decimal for domain model.  None stays None."""
    if val is None:
        return None
    return Decimal(str(val))


def _to_decimal_zero(val: float | None) -> Decimal:
    """Convert ORM float to Decimal, defaulting to 0."""
    if val is None:
        return Decimal("0")
    return Decimal(str(val))


# ---------------------------------------------------------------------------
# PairResolver  — maps  symbol <-> pair_id  and  name <-> exchange_id
# ---------------------------------------------------------------------------

class PairResolver:
    """Resolves pair_symbol <-> pair_id with an in-memory cache.

    Lazily creates TradingPairModel and ExchangeModel rows as needed so that
    domain models using string identifiers can be persisted to the UUID-keyed
    ORM tables.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._pair_cache: dict[str, uuid.UUID] = {}       # symbol -> pair_id
        self._pair_reverse: dict[uuid.UUID, str] = {}      # pair_id -> symbol
        self._exchange_cache: dict[str, uuid.UUID] = {}    # name   -> exchange_id
        self._exchange_reverse: dict[uuid.UUID, str] = {}  # exchange_id -> name

    # -- bulk load on startup --------------------------------------------------

    async def load_cache(self) -> None:
        """Pre-load all existing pairs and exchanges into the lookup caches."""
        pairs = (await self._session.execute(select(TradingPairModel))).scalars().all()
        for p in pairs:
            self._pair_cache[p.symbol] = p.id
            self._pair_reverse[p.id] = p.symbol

        exchanges = (await self._session.execute(select(ExchangeModel))).scalars().all()
        for e in exchanges:
            self._exchange_cache[e.name] = e.id
            self._exchange_reverse[e.id] = e.name

    # -- pair resolution -------------------------------------------------------

    async def get_pair_id(self, symbol: str) -> uuid.UUID:
        """Get or create a pair_id for *symbol*."""
        if symbol in self._pair_cache:
            return self._pair_cache[symbol]

        exchange_id = await self.get_exchange_id("paper")
        parts = symbol.split("/")
        base = parts[0] if len(parts) >= 2 else symbol
        quote = parts[1] if len(parts) >= 2 else "USDT"

        pair = TradingPairModel(
            exchange_id=exchange_id,
            symbol=symbol,
            base_currency=base,
            quote_currency=quote,
        )
        self._session.add(pair)
        try:
            await self._session.flush()
        except IntegrityError:
            # Race condition — another task already created this pair.
            await self._session.rollback()
            stmt = select(TradingPairModel).where(TradingPairModel.symbol == symbol)
            pair = (await self._session.execute(stmt)).scalar_one()

        self._pair_cache[symbol] = pair.id
        self._pair_reverse[pair.id] = symbol
        return pair.id

    def symbol_for_pair_id(self, pair_id: uuid.UUID) -> str:
        """Reverse-lookup: pair_id -> symbol."""
        return self._pair_reverse.get(pair_id, "UNKNOWN")

    # -- exchange resolution ---------------------------------------------------

    async def get_exchange_id(self, name: str) -> uuid.UUID:
        """Get or create an exchange_id for *name*."""
        if name in self._exchange_cache:
            return self._exchange_cache[name]

        exchange = ExchangeModel(name=name, exchange_type=name)
        self._session.add(exchange)
        try:
            await self._session.flush()
        except IntegrityError:
            await self._session.rollback()
            stmt = select(ExchangeModel).where(ExchangeModel.name == name)
            exchange = (await self._session.execute(stmt)).scalar_one()

        self._exchange_cache[name] = exchange.id
        self._exchange_reverse[exchange.id] = name
        return exchange.id

    def name_for_exchange_id(self, exchange_id: uuid.UUID) -> str:
        """Reverse-lookup: exchange_id -> name."""
        return self._exchange_reverse.get(exchange_id, "unknown")


# ---------------------------------------------------------------------------
# Order mappers
# ---------------------------------------------------------------------------

async def order_to_orm(order: Order, resolver: PairResolver) -> OrderModel:
    """Convert a domain Order to an ORM OrderModel."""
    pair_id = await resolver.get_pair_id(order.pair_symbol)
    exchange_name = order.exchange_name or "paper"
    exchange_id = await resolver.get_exchange_id(exchange_name)

    return OrderModel(
        id=order.id,
        signal_id=order.signal_id,
        pair_id=pair_id,
        exchange_id=exchange_id,
        trading_mode=str(order.trading_mode),
        order_type=str(order.order_type),
        side=str(order.side),
        quantity=_to_float(order.quantity) or 0.0,
        price=_to_float(order.price),
        stop_price=_to_float(order.stop_price),
        status=str(order.status),
        filled_quantity=_to_float(order.filled_quantity) or 0.0,
        avg_fill_price=_to_float(order.avg_fill_price),
        fee=_to_float(order.fee) or 0.0,
        fee_currency=order.fee_currency or None,
        exchange_order_id=order.exchange_order_id,
        error_message=order.error_message,
        created_at=order.created_at,
        updated_at=order.updated_at,
        filled_at=order.filled_at,
    )


def orm_to_order(orm: OrderModel, resolver: PairResolver) -> Order:
    """Convert an ORM OrderModel to a domain Order."""
    return Order(
        id=orm.id,
        signal_id=orm.signal_id,
        pair_symbol=resolver.symbol_for_pair_id(orm.pair_id),
        exchange_name=resolver.name_for_exchange_id(orm.exchange_id),
        trading_mode=TradingMode(orm.trading_mode),
        order_type=OrderType(orm.order_type),
        side=OrderSide(orm.side),
        quantity=_to_decimal_zero(orm.quantity),
        price=_to_decimal(orm.price),
        stop_price=_to_decimal(orm.stop_price),
        status=OrderStatus(orm.status),
        filled_quantity=_to_decimal_zero(orm.filled_quantity),
        avg_fill_price=_to_decimal(orm.avg_fill_price),
        fee=_to_decimal_zero(orm.fee),
        fee_currency=orm.fee_currency or "",
        exchange_order_id=orm.exchange_order_id,
        error_message=orm.error_message,
        created_at=orm.created_at,
        updated_at=orm.updated_at,
        filled_at=orm.filled_at,
    )


# ---------------------------------------------------------------------------
# Position mappers
# ---------------------------------------------------------------------------

async def position_to_orm(position: Position, resolver: PairResolver) -> PositionModel:
    """Convert a domain Position to an ORM PositionModel."""
    pair_id = await resolver.get_pair_id(position.pair_symbol)
    exchange_name = position.exchange_name or "paper"
    exchange_id = await resolver.get_exchange_id(exchange_name)

    return PositionModel(
        id=position.id,
        pair_id=pair_id,
        exchange_id=exchange_id,
        trading_mode=str(position.trading_mode),
        side=str(position.side),
        status=str(position.status),
        entry_price=_to_float(position.entry_price) or 0.0,
        exit_price=_to_float(position.exit_price),
        quantity=_to_float(position.quantity) or 0.0,
        stop_loss=_to_float(position.stop_loss),
        take_profit=_to_float(position.take_profit),
        realized_pnl=_to_float(position.realized_pnl),
        realized_pnl_pct=_to_float(position.realized_pnl_pct),
        fees_total=_to_float(position.fees_total) or 0.0,
        strategy_name=position.strategy_name or None,
        entry_signal_id=position.entry_signal_id,
        exit_signal_id=position.exit_signal_id,
        opened_at=position.opened_at,
        closed_at=position.closed_at,
        metadata_json={"justification": position.justification} if position.justification else None,
    )


def orm_to_position(orm: PositionModel, resolver: PairResolver) -> Position:
    """Convert an ORM PositionModel to a domain Position."""
    return Position(
        id=orm.id,
        pair_symbol=resolver.symbol_for_pair_id(orm.pair_id),
        exchange_name=resolver.name_for_exchange_id(orm.exchange_id),
        trading_mode=TradingMode(orm.trading_mode),
        side=PositionSide(orm.side),
        status=PositionStatus(orm.status),
        entry_price=_to_decimal_zero(orm.entry_price),
        exit_price=_to_decimal(orm.exit_price),
        quantity=_to_decimal_zero(orm.quantity),
        stop_loss=_to_decimal(orm.stop_loss),
        take_profit=_to_decimal(orm.take_profit),
        realized_pnl=_to_decimal(orm.realized_pnl),
        realized_pnl_pct=_to_decimal(orm.realized_pnl_pct),
        fees_total=_to_decimal_zero(orm.fees_total),
        strategy_name=orm.strategy_name or "",
        entry_signal_id=orm.entry_signal_id,
        exit_signal_id=orm.exit_signal_id,
        opened_at=orm.opened_at,
        closed_at=orm.closed_at,
        justification=(orm.metadata_json or {}).get("justification", ""),
    )


# ---------------------------------------------------------------------------
# Signal mappers
# ---------------------------------------------------------------------------

async def signal_to_orm(signal: Signal, resolver: PairResolver) -> SignalModel:
    """Convert a domain Signal to an ORM SignalModel."""
    pair_id = await resolver.get_pair_id(signal.pair_symbol)

    return SignalModel(
        id=signal.id,
        pair_id=pair_id,
        strategy_name=signal.strategy_name or "unknown",
        action=str(signal.action),
        confidence=signal.confidence,
        technical_score=signal.technical_score,
        sentiment_score=signal.sentiment_score,
        onchain_score=signal.onchain_score,
        derivatives_score=signal.derivatives_score,
        market_sentiment_score=signal.market_sentiment_score,
        cvd_score=signal.cvd_score,
        social_velocity_score=signal.social_velocity_score,
        contributing_factors=signal.contributing_factors or {},
        created_at=signal.created_at,
    )


def orm_to_signal(orm: SignalModel, resolver: PairResolver) -> Signal:
    """Convert an ORM SignalModel to a domain Signal."""
    return Signal(
        id=orm.id,
        pair_symbol=resolver.symbol_for_pair_id(orm.pair_id),
        action=SignalAction(orm.action),
        confidence=float(orm.confidence) if orm.confidence is not None else 0.0,
        technical_score=float(orm.technical_score) if orm.technical_score is not None else None,
        sentiment_score=float(orm.sentiment_score) if orm.sentiment_score is not None else None,
        onchain_score=float(orm.onchain_score) if orm.onchain_score is not None else None,
        derivatives_score=float(orm.derivatives_score) if hasattr(orm, "derivatives_score") and orm.derivatives_score is not None else None,
        market_sentiment_score=float(orm.market_sentiment_score) if hasattr(orm, "market_sentiment_score") and orm.market_sentiment_score is not None else None,
        cvd_score=float(orm.cvd_score) if hasattr(orm, "cvd_score") and orm.cvd_score is not None else None,
        social_velocity_score=float(orm.social_velocity_score) if hasattr(orm, "social_velocity_score") and orm.social_velocity_score is not None else None,
        contributing_factors=orm.contributing_factors or {},
        strategy_name=orm.strategy_name or "",
        created_at=orm.created_at,
    )


# ---------------------------------------------------------------------------
# Alert mappers
# ---------------------------------------------------------------------------

def alert_config_to_orm(config: Any) -> AlertConfigModel:
    """Convert an AlertConfig to an ORM AlertConfigModel.

    The domain model stores symbol/value/message as separate fields;
    the ORM packs them into JSONB ``conditions``.

    ``config`` is typed as ``Any`` to avoid a circular import at the
    module level.  At runtime it is an ``AlertConfig`` instance.
    """
    return AlertConfigModel(
        id=uuid.UUID(config.id),
        alert_type=config.alert_type,
        conditions={
            "symbol": config.symbol,
            "value": config.value,
            "message": config.message,
        },
        channels={},  # No channels implemented yet
        is_active=config.is_active,
        created_at=config.created_at,
    )


def orm_to_alert_config(orm: AlertConfigModel) -> Any:
    """Convert an ORM AlertConfigModel to an AlertConfig.

    Returns an ``AlertConfig`` instance (lazy import to break cycle).
    """
    from ctrade.notifications.alert_manager import AlertConfig

    conditions = orm.conditions or {}
    return AlertConfig(
        id=str(orm.id),
        alert_type=orm.alert_type,
        symbol=conditions.get("symbol", ""),
        value=conditions.get("value", 0.0),
        message=conditions.get("message"),
        is_active=orm.is_active,
        created_at=orm.created_at,
    )


def alert_trigger_to_orm(trigger: Any) -> AlertHistoryModel:
    """Convert an AlertTrigger to an ORM AlertHistoryModel.

    ``trigger`` is typed as ``Any`` to avoid a circular import.
    """
    try:
        config_id = uuid.UUID(trigger.alert_id)
    except (ValueError, AttributeError):
        config_id = None

    return AlertHistoryModel(
        alert_config_id=config_id,
        message=trigger.message,
        severity="info",
        delivered_to={
            "alert_type": trigger.alert_type,
            "symbol": trigger.symbol,
            "triggered_value": trigger.triggered_value,
        },
        created_at=trigger.triggered_at,
    )


def orm_to_alert_trigger(orm: AlertHistoryModel) -> Any:
    """Convert an ORM AlertHistoryModel to an AlertTrigger.

    Returns an ``AlertTrigger`` instance (lazy import to break cycle).
    """
    from ctrade.notifications.alert_manager import AlertTrigger

    delivered = orm.delivered_to or {}
    return AlertTrigger(
        id=str(orm.id),
        alert_id=str(orm.alert_config_id) if orm.alert_config_id else "",
        alert_type=delivered.get("alert_type", ""),
        symbol=delivered.get("symbol", ""),
        message=orm.message,
        triggered_value=delivered.get("triggered_value", 0.0),
        triggered_at=orm.created_at,
    )
