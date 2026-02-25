"""Paper trading engine with optional database persistence.

Simulates order execution, position management, and portfolio tracking
without connecting to a real exchange.  Primary state lives in memory for
fast reads; mutations are written through to the database asynchronously
when a DB connection is available (fire-and-forget).
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, ClassVar

from ctrade.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    PositionStatus,
    TradingMode,
)
from ctrade.core.events import Event, EventBus, EventTypes
from ctrade.core.models import Order, Position
from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation

logger = logging.getLogger(__name__)

INITIAL_BALANCE = Decimal("10000.00")


@dataclass
class EquityPoint:
    """A single point on the equity curve."""
    timestamp: datetime
    total_value: float
    cash: float
    positions_value: float


class PaperEngine:
    """In-memory paper trading engine singleton."""

    _instance: ClassVar[PaperEngine | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, initial_balance: Decimal = INITIAL_BALANCE) -> None:
        self._cash: dict[str, Decimal] = {"USDT": initial_balance}
        self._orders: list[Order] = []
        self._positions: list[Position] = []
        self._equity_curve: list[EquityPoint] = []
        self._watched_pairs: list[str] = []
        self._data_lock = threading.Lock()
        self._daily_pnl_start: float = float(initial_balance)

        # Record initial equity
        self._equity_curve.append(EquityPoint(
            timestamp=datetime.now(timezone.utc),
            total_value=float(initial_balance),
            cash=float(initial_balance),
            positions_value=0.0,
        ))

    @classmethod
    def get_instance(cls) -> PaperEngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    async def reset_to_defaults(self) -> None:
        """Wipe all paper-trading state and restore $10K balance.

        Clears in-memory orders, positions, equity curve, and cash.
        Deletes all paper-mode records from the database so the clean
        state persists across restarts.
        """
        with self._data_lock:
            self._cash = {"USDT": INITIAL_BALANCE}
            self._orders.clear()
            self._positions.clear()
            self._equity_curve.clear()
            self._daily_pnl_start = float(INITIAL_BALANCE)

            # Record fresh initial equity point
            self._equity_curve.append(EquityPoint(
                timestamp=datetime.now(timezone.utc),
                total_value=float(INITIAL_BALANCE),
                cash=float(INITIAL_BALANCE),
                positions_value=0.0,
            ))

        # Clear database records
        if is_db_ready():
            async def _clear_db(session, _resolver):
                from sqlalchemy import delete
                from ctrade.db.models import OrderModel, PositionModel, PortfolioSnapshotModel

                await session.execute(
                    delete(OrderModel).where(OrderModel.trading_mode == "paper")
                )
                await session.execute(
                    delete(PositionModel).where(PositionModel.trading_mode == "paper")
                )
                await session.execute(
                    delete(PortfolioSnapshotModel).where(
                        PortfolioSnapshotModel.trading_mode == "paper"
                    )
                )

            await run_db_operation(_clear_db, description="reset paper engine DB")

        logger.info("Paper engine reset to $%.2f", float(INITIAL_BALANCE))

    # ---- Event publishing ----

    @staticmethod
    def _publish(event_type: str, data: dict[str, Any]) -> None:
        """Publish an event via EventBus singleton (sync-safe)."""
        try:
            EventBus.get_instance().publish_nowait(Event(event_type=event_type, data=data))
        except Exception:
            pass  # EventBus not running yet — swallow silently

    # ---- Watched pairs ----

    def get_watched_pairs(self) -> list[str]:
        with self._data_lock:
            return list(self._watched_pairs)

    def add_watched_pair(self, symbol: str) -> bool:
        with self._data_lock:
            if symbol not in self._watched_pairs:
                self._watched_pairs.append(symbol)
                return True
            return False

    def remove_watched_pair(self, symbol: str) -> bool:
        with self._data_lock:
            if symbol in self._watched_pairs:
                self._watched_pairs.remove(symbol)
                return True
            return False

    def clear_all_watched_pairs(self) -> int:
        """Remove all watched pairs. Returns the count removed."""
        with self._data_lock:
            count = len(self._watched_pairs)
            self._watched_pairs.clear()
            return count

    # ---- Order management ----

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "market",
        quantity: float = 0.0,
        price: float | None = None,
        signal_id: str | None = None,
        strategy_name: str = "",
        justification: str = "",
        stop_loss: float | None = None,
        take_profit: float | None = None,
        exchange_name: str = "paper",
        exchange_id: str | None = None,
    ) -> Order:
        """Place an order. Market orders fill immediately."""
        from ctrade.exchange.market_data import MarketDataProvider

        market = MarketDataProvider.get_instance()
        # Use provided price (from orchestrator's real ticker) if available
        current_price = price if price is not None else market.get_current_price(symbol)

        order = Order(
            id=uuid.uuid4(),
            signal_id=uuid.UUID(signal_id) if signal_id else None,
            pair_symbol=symbol,
            exchange_name=exchange_name,
            trading_mode=TradingMode.PAPER,
            order_type=OrderType(order_type),
            side=OrderSide(side),
            quantity=Decimal(str(quantity)),
            price=Decimal(str(price)) if price else None,
            status=OrderStatus.PENDING,
        )

        with self._data_lock:
            if order_type == "market":
                fill_price = current_price
                cost = Decimal(str(fill_price)) * order.quantity
                fee = cost * Decimal("0.001")  # 0.1% fee

                # Check balance
                quote = symbol.split("/")[1] if "/" in symbol else "USDT"
                base = symbol.split("/")[0] if "/" in symbol else symbol

                if side == "buy":
                    available = self._cash.get(quote, Decimal("0"))
                    if available < cost + fee:
                        order.status = OrderStatus.REJECTED
                        order.error_message = f"Insufficient {quote}: need {cost + fee}, have {available}"
                        self._orders.append(order)
                        return order

                    self._cash[quote] = available - cost - fee
                    self._cash[base] = self._cash.get(base, Decimal("0")) + order.quantity
                else:  # sell
                    existing_long = self._find_open_position(symbol, PositionSide.LONG)
                    if existing_long:
                        # Closing a long position — need the base asset
                        available = self._cash.get(base, Decimal("0"))
                        if available < order.quantity:
                            order.status = OrderStatus.REJECTED
                            order.error_message = f"Insufficient {base}: need {order.quantity}, have {available}"
                            self._orders.append(order)
                            return order

                        self._cash[base] = available - order.quantity
                        self._cash[quote] = self._cash.get(quote, Decimal("0")) + cost - fee
                    else:
                        # Opening a short position — use quote currency as margin
                        available_quote = self._cash.get(quote, Decimal("0"))
                        if available_quote < cost + fee:
                            order.status = OrderStatus.REJECTED
                            order.error_message = f"Insufficient {quote} margin: need {cost + fee}, have {available_quote}"
                            self._orders.append(order)
                            return order

                        self._cash[quote] = available_quote - cost - fee

                order.status = OrderStatus.FILLED
                order.filled_quantity = order.quantity
                order.avg_fill_price = Decimal(str(fill_price))
                order.fee = fee
                order.fee_currency = quote
                order.filled_at = datetime.now(timezone.utc)
                order.updated_at = datetime.now(timezone.utc)

                self._orders.append(order)

                # Update positions
                self._update_positions(order, strategy_name, justification, stop_loss, take_profit, exchange_name)
                # Record equity
                self._record_equity()

                # Publish ORDER_FILLED event
                self._publish(EventTypes.ORDER_FILLED, {
                    "order_id": str(order.id),
                    "pair": symbol,
                    "side": side,
                    "quantity": float(order.filled_quantity),
                    "price": float(order.avg_fill_price or 0),
                    "fee": float(order.fee),
                })

            else:
                # Limit/stop orders stay pending
                self._orders.append(order)

        # Write-through to DB (async, non-blocking)
        fire_and_forget(self._persist_order_async(order))
        return order

    def _update_positions(self, order: Order, strategy_name: str = "", justification: str = "", stop_loss: float | None = None, take_profit: float | None = None, exchange_name: str = "paper") -> None:
        """Update positions after a filled order."""
        if order.side == OrderSide.BUY:
            # Check for existing short position to close
            existing = self._find_open_position(order.pair_symbol, PositionSide.SHORT)
            if existing:
                self._close_position_internal(existing, order)
            else:
                # Open new long position
                pos = Position(
                    id=uuid.uuid4(),
                    pair_symbol=order.pair_symbol,
                    exchange_name=exchange_name,
                    trading_mode=TradingMode.PAPER,
                    side=PositionSide.LONG,
                    status=PositionStatus.OPEN,
                    entry_price=order.avg_fill_price or Decimal("0"),
                    quantity=order.filled_quantity,
                    stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                    take_profit=Decimal(str(take_profit)) if take_profit else None,
                    fees_total=order.fee,
                    strategy_name=strategy_name,
                    entry_signal_id=order.signal_id,
                    justification=justification,
                )
                self._positions.append(pos)
                fire_and_forget(self._persist_position_async(pos))
                self._publish(EventTypes.POSITION_OPENED, {
                    "position_id": str(pos.id),
                    "pair": pos.pair_symbol,
                    "side": "long",
                    "entry_price": float(pos.entry_price),
                    "quantity": float(pos.quantity),
                })

        elif order.side == OrderSide.SELL:
            existing = self._find_open_position(order.pair_symbol, PositionSide.LONG)
            if existing:
                self._close_position_internal(existing, order)
            else:
                pos = Position(
                    id=uuid.uuid4(),
                    pair_symbol=order.pair_symbol,
                    exchange_name=exchange_name,
                    trading_mode=TradingMode.PAPER,
                    side=PositionSide.SHORT,
                    status=PositionStatus.OPEN,
                    entry_price=order.avg_fill_price or Decimal("0"),
                    quantity=order.filled_quantity,
                    stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                    take_profit=Decimal(str(take_profit)) if take_profit else None,
                    fees_total=order.fee,
                    strategy_name=strategy_name,
                    entry_signal_id=order.signal_id,
                    justification=justification,
                )
                self._positions.append(pos)
                fire_and_forget(self._persist_position_async(pos))
                self._publish(EventTypes.POSITION_OPENED, {
                    "position_id": str(pos.id),
                    "pair": pos.pair_symbol,
                    "side": "short",
                    "entry_price": float(pos.entry_price),
                    "quantity": float(pos.quantity),
                })

    def _find_open_position(self, symbol: str, side: PositionSide) -> Position | None:
        for pos in self._positions:
            if pos.pair_symbol == symbol and pos.side == side and pos.status == PositionStatus.OPEN:
                return pos
        return None

    def _close_position_internal(self, pos: Position, exit_order: Order) -> None:
        """Close a position with an exit order."""
        pos.status = PositionStatus.CLOSED
        pos.exit_price = exit_order.avg_fill_price
        pos.closed_at = datetime.now(timezone.utc)
        pos.exit_signal_id = exit_order.signal_id
        pos.fees_total += exit_order.fee

        if pos.entry_price and pos.exit_price:
            if pos.side == PositionSide.LONG:
                pnl = (pos.exit_price - pos.entry_price) * pos.quantity - pos.fees_total
            else:
                pnl = (pos.entry_price - pos.exit_price) * pos.quantity - pos.fees_total
            pos.realized_pnl = pnl
            if pos.entry_price > 0:
                pos.realized_pnl_pct = (pnl / (pos.entry_price * pos.quantity)) * 100

        # Persist closed position + cash snapshot
        fire_and_forget(self._persist_position_async(pos))
        fire_and_forget(self._persist_cash_snapshot_async())

    async def close_position(self, position_id: str) -> Order | None:
        """Close a position at market price."""
        with self._data_lock:
            pos = None
            for p in self._positions:
                if str(p.id) == position_id and p.status == PositionStatus.OPEN:
                    pos = p
                    break
            if not pos:
                return None

        # Place opposite order
        side = "sell" if pos.side == PositionSide.LONG else "buy"
        order = await self.place_order(
            symbol=pos.pair_symbol,
            side=side,
            order_type="market",
            quantity=float(pos.quantity),
        )

        # If place_order didn't close the position via _update_positions
        # (can happen if _find_open_position fails to match), force-close it
        if order.status == OrderStatus.FILLED and pos.status == PositionStatus.OPEN:
            with self._data_lock:
                self._close_position_internal(pos, order)

        return order

    def _record_equity(self) -> None:
        """Record current portfolio value to equity curve."""
        from ctrade.exchange.market_data import MarketDataProvider
        market = MarketDataProvider.get_instance()

        cash_total = sum(
            float(v) if k == "USDT" else float(v) * market.get_current_price(f"{k}/USDT")
            for k, v in self._cash.items()
            if float(v) > 0
        )
        positions_value = 0.0
        for pos in self._positions:
            if pos.status == PositionStatus.OPEN:
                price = market.get_current_price(pos.pair_symbol)
                positions_value += float(pos.quantity) * price

        total = cash_total + positions_value
        self._equity_curve.append(EquityPoint(
            timestamp=datetime.now(timezone.utc),
            total_value=round(total, 2),
            cash=round(cash_total, 2),
            positions_value=round(positions_value, 2),
        ))

    # ---- Query methods ----

    def get_orders(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._data_lock:
            orders = self._orders
            if status:
                orders = [o for o in orders if o.status == status]
            return [self._order_to_dict(o) for o in reversed(orders)]

    def get_positions(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._data_lock:
            positions = self._positions
            if status:
                positions = [p for p in positions if p.status == status]
            result = []
            for p in reversed(positions):
                d = self._position_to_dict(p)
                # Add unrealized P&L for open positions
                if p.status == PositionStatus.OPEN:
                    from ctrade.exchange.market_data import MarketDataProvider
                    market = MarketDataProvider.get_instance()
                    current = Decimal(str(market.get_current_price(p.pair_symbol)))
                    if p.side == PositionSide.LONG:
                        unrealized = (current - p.entry_price) * p.quantity
                    else:
                        unrealized = (p.entry_price - current) * p.quantity
                    d["unrealized_pnl"] = float(unrealized)
                    d["unrealized_pnl_pct"] = float(
                        unrealized / (p.entry_price * p.quantity) * 100
                    ) if p.entry_price > 0 else 0.0
                    d["current_price"] = float(current)
                result.append(d)
            return result

    async def get_portfolio(self) -> dict[str, Any]:
        with self._data_lock:
            from ctrade.exchange.market_data import MarketDataProvider
            market = MarketDataProvider.get_instance()

            cash_usd = float(self._cash.get("USDT", Decimal("0")))
            positions_value = 0.0
            unrealized_pnl = 0.0

            for pos in self._positions:
                if pos.status == PositionStatus.OPEN:
                    price = market.get_current_price(pos.pair_symbol)
                    val = float(pos.quantity) * price
                    positions_value += val
                    entry_val = float(pos.entry_price * pos.quantity)
                    if pos.side == PositionSide.LONG:
                        unrealized_pnl += val - entry_val
                    else:
                        unrealized_pnl += entry_val - val

            total = cash_usd + positions_value
            daily_pnl = total - self._daily_pnl_start

            open_count = sum(
                1 for p in self._positions if p.status == PositionStatus.OPEN
            )
            closed_count = sum(
                1 for p in self._positions if p.status == PositionStatus.CLOSED
            )
            total_realized = sum(
                float(p.realized_pnl or 0)
                for p in self._positions if p.status == PositionStatus.CLOSED
            )

            return {
                "cash_balance": {k: float(v) for k, v in self._cash.items()},
                "total_value_usd": round(total, 2),
                "positions_value": round(positions_value, 2),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "realized_pnl": round(total_realized, 2),
                "daily_pnl": round(daily_pnl, 2),
                "open_positions": open_count,
                "closed_positions": closed_count,
                "total_orders": len(self._orders),
            }

    def get_equity_curve(self) -> list[dict[str, Any]]:
        with self._data_lock:
            return [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "total_value": p.total_value,
                    "cash": p.cash,
                    "positions_value": p.positions_value,
                }
                for p in self._equity_curve
            ]

    def get_recent_trades(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get recent closed positions as trades."""
        with self._data_lock:
            closed = [
                p for p in self._positions if p.status == PositionStatus.CLOSED
            ]
            closed.sort(key=lambda p: p.closed_at or p.opened_at, reverse=True)
            return [self._position_to_dict(p) for p in closed[:limit]]

    # ---- Database persistence ----

    async def hydrate_from_db(self) -> None:
        """Load persisted state from database.  Called once at startup."""
        if not is_db_ready():
            logger.info("DB not available — PaperEngine starting with empty in-memory state")
            return

        async def _load(session, resolver):
            from sqlalchemy import select
            from ctrade.db.mappers import orm_to_order, orm_to_position
            from ctrade.db.models import OrderModel, PositionModel, PortfolioSnapshotModel

            # Load orders
            stmt = select(OrderModel).where(OrderModel.trading_mode == "paper")
            orm_orders = (await session.execute(stmt)).scalars().all()
            orders = [orm_to_order(o, resolver) for o in orm_orders]

            # Load positions
            stmt = select(PositionModel).where(PositionModel.trading_mode == "paper")
            orm_positions = (await session.execute(stmt)).scalars().all()
            positions = [orm_to_position(p, resolver) for p in orm_positions]

            # Load latest cash snapshot
            stmt = (
                select(PortfolioSnapshotModel)
                .where(PortfolioSnapshotModel.trading_mode == "paper")
                .order_by(PortfolioSnapshotModel.time.desc())
                .limit(1)
            )
            snapshot = (await session.execute(stmt)).scalar_one_or_none()

            return orders, positions, snapshot

        loaded = await run_db_operation(_load, description="hydrate PaperEngine")
        if loaded is None:
            return

        orders, positions, snapshot = loaded
        with self._data_lock:
            if orders:
                self._orders = orders
            if positions:
                self._positions = positions
            if snapshot and snapshot.cash_balance:
                self._cash = {
                    k: Decimal(str(v)) for k, v in snapshot.cash_balance.items()
                }
                self._daily_pnl_start = float(snapshot.total_value_usd or 0)

        logger.info(
            "Hydrated PaperEngine from DB: %d orders, %d positions",
            len(orders),
            len(positions),
        )

    async def _persist_order_async(self, order: Order) -> None:
        """Write-through: persist a single order to the database."""
        async def _do(session, resolver):
            from ctrade.db.mappers import order_to_orm
            orm_order = await order_to_orm(order, resolver)
            await session.merge(orm_order)
        await run_db_operation(_do, description="persist order")

    async def _persist_position_async(self, position: Position) -> None:
        """Write-through: persist a single position to the database."""
        async def _do(session, resolver):
            from ctrade.db.mappers import position_to_orm
            orm_pos = await position_to_orm(position, resolver)
            await session.merge(orm_pos)
        await run_db_operation(_do, description="persist position")

    async def _persist_cash_snapshot_async(self) -> None:
        """Write-through: persist current cash balances as a portfolio snapshot."""
        async def _do(session, resolver):
            from ctrade.db.models import PortfolioSnapshotModel
            exchange_id = await resolver.get_exchange_id("paper")
            open_count = sum(
                1 for p in self._positions if p.status == PositionStatus.OPEN
            )
            total_usd = sum(float(v) for v in self._cash.values())
            snapshot = PortfolioSnapshotModel(
                exchange_id=exchange_id,
                trading_mode="paper",
                total_value_usd=round(total_usd, 2),
                cash_balance={k: float(v) for k, v in self._cash.items()},
                open_positions=open_count,
            )
            session.add(snapshot)
        await run_db_operation(_do, description="persist cash snapshot")

    # ---- Serialization ----

    @staticmethod
    def _order_to_dict(o: Order) -> dict[str, Any]:
        return {
            "id": str(o.id),
            "signal_id": str(o.signal_id) if o.signal_id else None,
            "pair_symbol": o.pair_symbol,
            "trading_mode": o.trading_mode,
            "order_type": o.order_type,
            "side": o.side,
            "quantity": float(o.quantity),
            "price": float(o.price) if o.price else None,
            "status": o.status,
            "filled_quantity": float(o.filled_quantity),
            "avg_fill_price": float(o.avg_fill_price) if o.avg_fill_price else None,
            "fee": float(o.fee),
            "fee_currency": o.fee_currency,
            "error_message": o.error_message,
            "created_at": o.created_at.isoformat(),
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
        }

    @staticmethod
    def _position_to_dict(p: Position) -> dict[str, Any]:
        return {
            "id": str(p.id),
            "pair_symbol": p.pair_symbol,
            "exchange_name": p.exchange_name,
            "side": p.side,
            "status": p.status,
            "entry_price": float(p.entry_price),
            "exit_price": float(p.exit_price) if p.exit_price else None,
            "quantity": float(p.quantity),
            "stop_loss": float(p.stop_loss) if p.stop_loss else None,
            "take_profit": float(p.take_profit) if p.take_profit else None,
            "realized_pnl": float(p.realized_pnl) if p.realized_pnl else None,
            "realized_pnl_pct": float(p.realized_pnl_pct) if p.realized_pnl_pct else None,
            "fees_total": float(p.fees_total),
            "strategy_name": p.strategy_name,
            "opened_at": p.opened_at.isoformat(),
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "justification": p.justification,
        }
