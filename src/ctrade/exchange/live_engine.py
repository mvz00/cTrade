"""Live trading engine — executes real orders on exchanges via ccxt.

Mirrors the PaperEngine API but routes order placement and position
management through ccxt to a real exchange.  In-memory state is maintained
for fast reads (orders, positions, equity curve) with async write-through
to the database.
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


@dataclass
class EquityPoint:
    """A single point on the equity curve."""

    timestamp: datetime
    total_value: float
    cash: float
    positions_value: float


class LiveEngine:
    """Live trading engine singleton — executes real orders via ccxt."""

    _instance: ClassVar[LiveEngine | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._orders: list[Order] = []
        self._positions: list[Position] = []
        self._equity_curve: list[EquityPoint] = []
        self._data_lock = threading.Lock()
        # Cached real exchange prices for open positions (updated async)
        self._live_prices: dict[str, float] = {}
        # Pairs that the exchange cannot trade (learned at runtime).
        # Prevents repeated API calls for coins that return errors like
        # "Market trades for this coin are unavailable at present".
        self._untradeable_pairs: set[str] = set()

    @classmethod
    def get_instance(cls) -> LiveEngine:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    # ---- Event publishing ----

    @staticmethod
    def _publish(event_type: str, data: dict[str, Any]) -> None:
        """Publish an event via EventBus singleton (sync-safe)."""
        try:
            EventBus.get_instance().publish_nowait(Event(event_type=event_type, data=data))
        except Exception:
            pass  # EventBus not running yet — swallow silently

    @staticmethod
    async def _notify_order_fill(order: Any, mode: str = "live") -> None:
        """Send order-fill notification to all registered channels."""
        try:
            from ctrade.notifications.channels.router import NotificationRouter
            router = NotificationRouter.get_instance()
            if not router.list_channels():
                return
            side = order.side.value if hasattr(order.side, "value") else str(order.side)
            qty = float(order.filled_quantity) if order.filled_quantity else 0
            price = float(order.avg_fill_price) if order.avg_fill_price else 0
            fee = float(order.fee) if order.fee else 0
            symbol = order.pair_symbol
            message = f"{side.upper()} {qty:.6g} {symbol} filled @ {price:.8g} ({mode} mode)"
            await router.dispatch(
                message=message,
                severity="success",
                metadata={
                    "title": f"Order Filled: {side.upper()} {symbol}",
                    "pair": symbol,
                    "side": side.upper(),
                    "quantity": qty,
                    "price": price,
                    "fee": fee,
                    "mode": mode,
                },
            )
        except Exception:
            pass  # Non-fatal — don't break order flow

    # ---- Watched pairs (delegated to PaperEngine — shared state) ----

    def get_watched_pairs(self) -> list[str]:
        from ctrade.exchange.paper_engine import PaperEngine

        return PaperEngine.get_instance().get_watched_pairs()

    def add_watched_pair(self, symbol: str) -> bool:
        from ctrade.exchange.paper_engine import PaperEngine

        return PaperEngine.get_instance().add_watched_pair(symbol)

    def remove_watched_pair(self, symbol: str) -> bool:
        from ctrade.exchange.paper_engine import PaperEngine

        return PaperEngine.get_instance().remove_watched_pair(symbol)

    # ---- Helper: get exchange config ----

    def _get_exchange_name(self, exchange_id: str | None = None) -> str:
        """Get the name of a specific exchange, or fall back to the first configured."""
        try:
            from ctrade.core.config_store import RuntimeConfigStore

            store = RuntimeConfigStore.get()
            if exchange_id:
                entry = store.get_exchange_entry(exchange_id)
                if entry:
                    return entry.name
            exchanges = store.list_exchanges()
            if exchanges:
                return exchanges[0]["name"]
        except Exception:
            pass
        return "unknown"

    def _resolve_exchange_id(self, exchange_name: str) -> str | None:
        """Look up an exchange_id from the exchange name."""
        try:
            from ctrade.core.config_store import RuntimeConfigStore

            store = RuntimeConfigStore.get()
            for ex_dict in store.list_exchanges():
                if ex_dict["name"].lower() == exchange_name.lower():
                    return ex_dict["id"]
        except Exception:
            pass
        return None

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
        exchange_name: str = "",
        exchange_id: str | None = None,
    ) -> Order:
        """Place a real order on the exchange via ccxt."""
        from ctrade.core.config_store import RuntimeConfigStore
        from ctrade.exchange.market_data import MarketDataProvider

        if not exchange_name:
            exchange_name = self._get_exchange_name(exchange_id)

        order = Order(
            id=uuid.uuid4(),
            signal_id=uuid.UUID(signal_id) if signal_id else None,
            pair_symbol=symbol,
            exchange_name=exchange_name,
            trading_mode=TradingMode.LIVE,
            order_type=OrderType(order_type),
            side=OrderSide(side),
            quantity=Decimal(str(quantity)),
            price=Decimal(str(price)) if price else None,
            status=OrderStatus.PENDING,
        )

        # Fast-reject pairs known to be untradeable on this exchange
        if symbol in self._untradeable_pairs:
            order.status = OrderStatus.REJECTED
            order.error_message = (
                f"{symbol} is not available for trading on {exchange_name} "
                f"(previously rejected by exchange)"
            )
            with self._data_lock:
                self._orders.append(order)
            logger.info("Skipped untradeable pair %s on %s", symbol, exchange_name)
            fire_and_forget(self._persist_order_async(order))
            return order

        # Safety: enforce max order size using REAL exchange price
        try:
            store = RuntimeConfigStore.get()
            trading_cfg = store.get_trading()
            max_order_usdt = trading_cfg.get("max_order_usdt", 100.0)

            market = MarketDataProvider.get_instance()
            # Use real exchange ticker for live mode price validation
            ticker = await market._try_ccxt_ticker(symbol)
            if ticker is None:
                # Try /USD pair (common on Kraken)
                ticker = await market._try_ccxt_ticker(symbol.replace("/USDT", "/USD"))
            current_price = float(ticker.last_price) if ticker else 0.0

            if current_price > 0:
                order_value_usdt = float(quantity) * current_price

                if order_value_usdt > max_order_usdt * 1.1:  # 10% tolerance for price movement
                    order.status = OrderStatus.REJECTED
                    order.error_message = (
                        f"Order value ${order_value_usdt:.2f} exceeds max "
                        f"${max_order_usdt:.2f}"
                    )
                    with self._data_lock:
                        self._orders.append(order)
                    logger.warning("LIVE order rejected: %s", order.error_message)
                    return order
            else:
                logger.warning("Could not get real price for %s — skipping size check", symbol)
        except Exception as e:
            logger.warning("Could not validate order size: %s", e)

        # Execute via ccxt
        ccxt_exchange = None
        try:
            market = MarketDataProvider.get_instance()
            ccxt_exchange = await market._create_ccxt_exchange(exchange_id)

            if ccxt_exchange is None:
                order.status = OrderStatus.REJECTED
                order.error_message = "No exchange configured or connection failed"
                with self._data_lock:
                    self._orders.append(order)
                return order

            if ccxt_exchange.id == 'coinspot':
                # ---- CoinSpot native V2 API path ----
                # Bypass ccxt for order placement — ccxt's CoinSpot V1
                # sign() method produces "failed signature" 401 errors.
                # The native V2 API uses the same proven HMAC-SHA512
                # signing as our working balance fetcher.
                api_key, api_secret = await MarketDataProvider._get_coinspot_credentials(exchange_id)

                # CoinSpot V2 always needs a price (buy/sell requires
                # rate, swap requires amount calculation).
                # Use bid price for sells and ask price for buys so
                # limit orders fill immediately.  CoinSpot's spread is
                # typically >1%, so using last_price with small slippage
                # often leaves sell orders unfilled above the bid.
                effective_price = price
                if effective_price is None:
                    base_price = 0.0
                    if side == "sell" and ticker and float(ticker.bid) > 0:
                        base_price = float(ticker.bid)
                    elif side == "buy" and ticker and float(ticker.ask) > 0:
                        base_price = float(ticker.ask)
                    elif current_price > 0:
                        base_price = current_price

                    if base_price > 0:
                        slippage = 1.005 if side == "buy" else 0.995
                        effective_price = round(base_price * slippage, 8)
                    else:
                        _fb_ticker = await market._try_ccxt_ticker(symbol)
                        if _fb_ticker:
                            if side == "sell" and float(_fb_ticker.bid) > 0:
                                _cp = float(_fb_ticker.bid)
                            elif side == "buy" and float(_fb_ticker.ask) > 0:
                                _cp = float(_fb_ticker.ask)
                            else:
                                _cp = float(_fb_ticker.last_price)
                            slippage = 1.005 if side == "buy" else 0.995
                            effective_price = round(_cp * slippage, 8)

                if effective_price is None:
                    order.status = OrderStatus.REJECTED
                    order.error_message = (
                        f"Could not determine price for CoinSpot order on {symbol}"
                    )
                    with self._data_lock:
                        self._orders.append(order)
                    await ccxt_exchange.close()
                    ccxt_exchange = None
                    return order

                order.order_type = OrderType.LIMIT
                order.price = Decimal(str(effective_price))

                logger.info(
                    "CoinSpot native V2: %s %s qty=%.6f @ %.8f",
                    side.upper(), symbol, quantity, effective_price,
                )

                result = await MarketDataProvider._coinspot_place_order_native(
                    api_key, api_secret, symbol, side, quantity, effective_price,
                )

                # Close ccxt instance — only needed for exchange detection
                await ccxt_exchange.close()
                ccxt_exchange = None

            else:
                # ---- Standard ccxt path (non-CoinSpot exchanges) ----

                # Reject orders for synthetic (injected) markets — these
                # pairs only work in paper trading mode.
                synthetic = getattr(ccxt_exchange, '_ctrade_synthetic_symbols', set())
                if symbol in synthetic:
                    order.status = OrderStatus.REJECTED
                    order.error_message = (
                        f"{symbol} is not available for live trading on {exchange_name}. "
                        f"This pair only works in paper trading mode."
                    )
                    with self._data_lock:
                        self._orders.append(order)
                    logger.warning(
                        "Symbol %s is synthetic on %s — order rejected",
                        symbol, exchange_name,
                    )
                    await ccxt_exchange.close()
                    return order

                # Auto-convert market → limit for exchanges that don't support market orders
                if order_type == "market":
                    supports_market = ccxt_exchange.has.get("createMarketOrder", True)
                    if not supports_market:
                        order_type = "limit"
                        order.order_type = OrderType.LIMIT
                        # current_price was already fetched above for size validation
                        if price is None and current_price > 0:
                            slippage = 1.005 if side == "buy" else 0.995
                            price = round(current_price * slippage, 8)
                            order.price = Decimal(str(price))
                        elif price is None:
                            # Fallback: re-fetch ticker
                            _fb_ticker = await market._try_ccxt_ticker(symbol)
                            if _fb_ticker:
                                _cp = float(_fb_ticker.last_price)
                                slippage = 1.005 if side == "buy" else 0.995
                                price = round(_cp * slippage, 8)
                                order.price = Decimal(str(price))
                        logger.info(
                            "Exchange does not support market orders — converted to limit @ %.8f for %s",
                            price or 0,
                            symbol,
                        )

                if order_type == "market":
                    if side == "buy":
                        result = await ccxt_exchange.create_market_buy_order(symbol, quantity)
                    else:
                        result = await ccxt_exchange.create_market_sell_order(symbol, quantity)
                else:
                    # Limit order
                    if price is None:
                        order.status = OrderStatus.REJECTED
                        order.error_message = "Limit orders require a price"
                        with self._data_lock:
                            self._orders.append(order)
                        return order
                    result = await ccxt_exchange.create_limit_order(
                        symbol, side, quantity, price
                    )

            # Parse ccxt response
            exchange_order_id = result.get("id")
            fill_price = result.get("average") or result.get("price") or 0
            filled_qty = result.get("filled") or quantity
            fee_info = result.get("fee") or {}
            fee_cost = fee_info.get("cost") or 0
            fee_currency = fee_info.get("currency") or "USDT"

            # Kraken (and some exchanges) return average=None for market
            # orders — the fill details arrive asynchronously.  Poll
            # fetch_order once to get the actual fill price.
            # Skip for CoinSpot native path (ccxt_exchange already closed).
            if not fill_price and exchange_order_id and ccxt_exchange is not None:
                try:
                    import asyncio as _aio
                    await _aio.sleep(0.5)  # brief pause for exchange to settle
                    fetched = await ccxt_exchange.fetch_order(exchange_order_id, symbol)
                    fill_price = fetched.get("average") or fetched.get("price") or 0
                    filled_qty = fetched.get("filled") or filled_qty
                    fee_info = fetched.get("fee") or fee_info
                    fee_cost = fee_info.get("cost") or fee_cost
                    fee_currency = fee_info.get("currency") or fee_currency
                except Exception as fetch_err:
                    logger.warning("Could not fetch order details for %s: %s", exchange_order_id, fetch_err)

            # Last resort: use the ticker price we already fetched for validation
            if not fill_price:
                try:
                    mdp = MarketDataProvider.get_instance()
                    _ticker = await mdp._try_ccxt_ticker(symbol)
                    if _ticker:
                        fill_price = float(_ticker.last_price)
                except Exception:
                    pass

            order.status = OrderStatus.FILLED
            order.filled_quantity = Decimal(str(filled_qty))
            order.avg_fill_price = Decimal(str(fill_price)) if fill_price else Decimal("0")
            order.fee = Decimal(str(fee_cost))
            order.fee_currency = fee_currency
            order.filled_at = datetime.now(timezone.utc)
            order.updated_at = datetime.now(timezone.utc)

            # Cache the fill price for live PnL calculations
            if fill_price:
                self._live_prices[symbol] = float(fill_price)

            with self._data_lock:
                self._orders.append(order)
                self._update_positions(order, strategy_name, justification, stop_loss, take_profit)
                self._record_equity_snapshot()

            # Publish event
            self._publish(EventTypes.ORDER_FILLED, {
                "order_id": str(order.id),
                "exchange_order_id": exchange_order_id,
                "pair": symbol,
                "side": side,
                "quantity": float(order.filled_quantity),
                "price": float(order.avg_fill_price or 0),
                "fee": float(order.fee),
                "mode": "live",
            })

            # Notify all channels (email, Discord, Telegram)
            fire_and_forget(self._notify_order_fill(order, mode="live"))

            logger.info(
                "LIVE %s %s: qty=%.6f @ %.4f (fee=%.4f %s) exchange_id=%s",
                side.upper(),
                symbol,
                float(order.filled_quantity),
                float(order.avg_fill_price or 0),
                float(order.fee),
                fee_currency,
                exchange_order_id,
            )

        except Exception as e:
            order.status = OrderStatus.REJECTED
            order.error_message = f"Exchange error: {e}"
            with self._data_lock:
                self._orders.append(order)

            # Learn: if the exchange says this coin can't be traded, add it
            # to the blocklist so we don't waste API calls on future ticks.
            err_lower = str(e).lower()
            if "unavailable" in err_lower or "not supported" in err_lower:
                self._untradeable_pairs.add(symbol)
                logger.warning(
                    "Added %s to untradeable pairs list — exchange: %s",
                    symbol, e,
                )
            else:
                logger.error("LIVE order failed for %s: %s", symbol, e)
        finally:
            if ccxt_exchange:
                try:
                    await ccxt_exchange.close()
                except Exception:
                    pass

        # Persist to DB
        fire_and_forget(self._persist_order_async(order))
        return order

    def _update_positions(self, order: Order, strategy_name: str = "", justification: str = "", stop_loss: float | None = None, take_profit: float | None = None) -> None:
        """Update positions after a filled order (must hold _data_lock)."""
        if order.side == OrderSide.BUY:
            existing = self._find_open_position(order.pair_symbol, PositionSide.SHORT)
            if existing:
                self._close_position_internal(existing, order)
            else:
                pos = Position(
                    id=uuid.uuid4(),
                    pair_symbol=order.pair_symbol,
                    exchange_name=order.exchange_name,
                    trading_mode=TradingMode.LIVE,
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
                    "mode": "live",
                })

        elif order.side == OrderSide.SELL:
            existing = self._find_open_position(order.pair_symbol, PositionSide.LONG)
            if existing:
                self._close_position_internal(existing, order)
            else:
                pos = Position(
                    id=uuid.uuid4(),
                    pair_symbol=order.pair_symbol,
                    exchange_name=order.exchange_name,
                    trading_mode=TradingMode.LIVE,
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
                    "mode": "live",
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

        fire_and_forget(self._persist_position_async(pos))

        self._publish(EventTypes.POSITION_CLOSED, {
            "position_id": str(pos.id),
            "pair": pos.pair_symbol,
            "pnl": float(pos.realized_pnl or 0),
            "pnl_pct": float(pos.realized_pnl_pct or 0),
            "mode": "live",
        })

    async def close_position(self, position_id: str) -> Order | None:
        """Close a position at market price via real exchange order."""
        with self._data_lock:
            pos = None
            for p in self._positions:
                if str(p.id) == position_id and p.status == PositionStatus.OPEN:
                    pos = p
                    break
            if not pos:
                return None

        side = "sell" if pos.side == PositionSide.LONG else "buy"
        # Route close order to the same exchange that opened the position
        close_exchange_id = self._resolve_exchange_id(pos.exchange_name)
        order = await self.place_order(
            symbol=pos.pair_symbol,
            side=side,
            order_type="market",
            quantity=float(pos.quantity),
            exchange_name=pos.exchange_name,
            exchange_id=close_exchange_id,
        )

        # If place_order didn't close the position via _update_positions
        # (can happen if _find_open_position fails to match), force-close it
        if order.status == OrderStatus.FILLED and pos.status == PositionStatus.OPEN:
            with self._data_lock:
                self._close_position_internal(pos, order)

        # Handle "Insufficient funds" — the coins don't exist on the
        # exchange (e.g. position opened in paper mode, or coins sold
        # externally).  Force-close the position in the database so it
        # doesn't block future close-all attempts.
        if (
            order.status == OrderStatus.REJECTED
            and pos.status == PositionStatus.OPEN
            and order.error_message
            and "insufficient funds" in order.error_message.lower()
        ):
            logger.warning(
                "Force-closing position %s (%s) — exchange reported insufficient funds",
                pos.id, pos.pair_symbol,
            )
            # Use last known price or entry price as exit price
            fallback_price = Decimal(str(
                self._live_prices.get(pos.pair_symbol, 0)
            )) or pos.entry_price
            order.avg_fill_price = fallback_price
            order.filled_quantity = pos.quantity
            order.status = OrderStatus.FILLED
            order.filled_at = datetime.now(timezone.utc)
            with self._data_lock:
                self._close_position_internal(pos, order)

        return order

    async def refresh_live_prices(self) -> None:
        """Refresh cached real exchange prices for all open position symbols."""
        from ctrade.exchange.market_data import MarketDataProvider

        market = MarketDataProvider.get_instance()

        with self._data_lock:
            symbols = list({
                p.pair_symbol for p in self._positions
                if p.status == PositionStatus.OPEN
            })

        for symbol in symbols:
            try:
                ticker = await market._try_ccxt_ticker(symbol)
                if ticker is None:
                    ticker = await market._try_ccxt_ticker(symbol.replace("/USDT", "/USD"))
                if ticker:
                    self._live_prices[symbol] = float(ticker.last_price)
            except Exception:
                logger.debug("Could not refresh price for %s", symbol)

    def _record_equity_snapshot(self) -> None:
        """Record a portfolio equity snapshot (call after order fills)."""
        positions_value = 0.0
        for pos in self._positions:
            if pos.status == PositionStatus.OPEN:
                price = self._live_prices.get(pos.pair_symbol, float(pos.entry_price))
                positions_value += float(pos.quantity) * price

        # We don't track cash for live — total comes from exchange
        total = positions_value  # approximate; full value fetched async
        self._equity_curve.append(EquityPoint(
            timestamp=datetime.now(timezone.utc),
            total_value=round(total, 2),
            cash=0.0,
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
                if p.status == PositionStatus.OPEN:
                    # Use cached real price for live positions (updated by _refresh_live_prices)
                    current = self._live_prices.get(p.pair_symbol)
                    if current is None:
                        # Fallback: use entry price (PnL = 0) rather than fake simulated price
                        current = p.entry_price
                    else:
                        current = Decimal(str(current))
                    if p.side == PositionSide.LONG:
                        unrealized = (current - p.entry_price) * p.quantity
                    else:
                        unrealized = (p.entry_price - current) * p.quantity
                    d["unrealized_pnl"] = float(unrealized)
                    d["unrealized_pnl_pct"] = (
                        float(unrealized / (p.entry_price * p.quantity) * 100)
                        if p.entry_price > 0
                        else 0.0
                    )
                    d["current_price"] = float(current)
                result.append(d)
            return result

    async def get_portfolio(self) -> dict[str, Any]:
        """Get portfolio from real exchange balances."""
        from ctrade.exchange.market_data import MarketDataProvider

        market = MarketDataProvider.get_instance()
        live_portfolio = await market.fetch_exchange_portfolio()

        if live_portfolio:
            # Augment with position data from our tracking
            with self._data_lock:
                open_count = sum(
                    1 for p in self._positions if p.status == PositionStatus.OPEN
                )
                closed_count = sum(
                    1 for p in self._positions if p.status == PositionStatus.CLOSED
                )
                total_realized = sum(
                    float(p.realized_pnl or 0)
                    for p in self._positions
                    if p.status == PositionStatus.CLOSED
                )
            live_portfolio["open_positions"] = open_count
            live_portfolio["closed_positions"] = closed_count
            live_portfolio["realized_pnl"] = round(total_realized, 2)
            live_portfolio["total_orders"] = len(self._orders)
            return live_portfolio

        # Fallback: build from in-memory state
        return {
            "cash_balance": {},
            "total_value_usd": 0.0,
            "positions_value": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "daily_pnl": 0.0,
            "open_positions": 0,
            "closed_positions": 0,
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
        """Load persisted live-mode state from database."""
        if not is_db_ready():
            logger.info("DB not available — LiveEngine starting with empty in-memory state")
            return

        async def _load(session, resolver):
            from sqlalchemy import select

            from ctrade.db.mappers import orm_to_order, orm_to_position
            from ctrade.db.models import OrderModel, PositionModel

            # Load live orders
            stmt = select(OrderModel).where(OrderModel.trading_mode == "live")
            orm_orders = (await session.execute(stmt)).scalars().all()
            orders = [orm_to_order(o, resolver) for o in orm_orders]

            # Load live positions
            stmt = select(PositionModel).where(PositionModel.trading_mode == "live")
            orm_positions = (await session.execute(stmt)).scalars().all()
            positions = [orm_to_position(p, resolver) for p in orm_positions]

            return orders, positions

        loaded = await run_db_operation(_load, description="hydrate LiveEngine")
        if loaded is None:
            return

        orders, positions = loaded
        with self._data_lock:
            if orders:
                self._orders = orders
            if positions:
                self._positions = positions

        logger.info(
            "Hydrated LiveEngine from DB: %d orders, %d positions",
            len(orders),
            len(positions),
        )

    async def _persist_order_async(self, order: Order) -> None:
        """Write-through: persist a single order to the database."""

        async def _do(session, resolver):
            from ctrade.db.mappers import order_to_orm

            orm_order = await order_to_orm(order, resolver)
            await session.merge(orm_order)

        await run_db_operation(_do, description="persist live order")

    async def _persist_position_async(self, position: Position) -> None:
        """Write-through: persist a single position to the database."""

        async def _do(session, resolver):
            from ctrade.db.mappers import position_to_orm

            orm_pos = await position_to_orm(position, resolver)
            await session.merge(orm_pos)

        await run_db_operation(_do, description="persist live position")

    # ---- Serialization (same as PaperEngine) ----

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
