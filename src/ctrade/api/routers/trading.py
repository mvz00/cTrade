"""Trading API endpoints — pairs, orders, positions, portfolio, engine control."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ctrade.api.schemas.trading import (
    ActivityEntry,
    AddPairRequest,
    AddPairsBatchRequest,
    CandlePoint,
    EngineStartRequest,
    EngineStatusResponse,
    OrderResponse,
    PairResponse,
    PlaceOrderRequest,
    PortfolioResponse,
    PositionResponse,
    QuickBuyRequest,
    QuickBuyResponse,
    SymbolCandleSeries,
    TickerResponse,
)
from ctrade.exchange.engine_resolver import get_engine
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.strategy.orchestrator import TradingOrchestrator

router = APIRouter(prefix="/trading", tags=["trading"])
logger = logging.getLogger(__name__)


# ---- Watched Pairs (shared — always use PaperEngine) ----

@router.get("/pairs", response_model=list[PairResponse])
async def list_pairs() -> list[PairResponse]:
    """List watched trading pairs."""
    engine = PaperEngine.get_instance()
    return [PairResponse(symbol=s) for s in engine.get_watched_pairs()]


@router.post("/pairs", response_model=PairResponse, status_code=201)
async def add_pair(body: AddPairRequest) -> PairResponse:
    """Add a trading pair to watch."""
    engine = PaperEngine.get_instance()
    if not engine.add_watched_pair(body.symbol):
        raise HTTPException(status_code=409, detail=f"Pair {body.symbol} already watched")
    logger.info("Pair added: %s", body.symbol)
    return PairResponse(symbol=body.symbol)


@router.post("/pairs/batch", response_model=list[PairResponse], status_code=201)
async def add_pairs_batch(body: AddPairsBatchRequest) -> list[PairResponse]:
    """Add multiple trading pairs at once."""
    engine = PaperEngine.get_instance()
    added = []
    for symbol in body.symbols:
        if engine.add_watched_pair(symbol):
            added.append(PairResponse(symbol=symbol))
    if added:
        logger.info("Pairs added: %s", [p.symbol for p in added])
    return added


@router.delete("/pairs/{symbol:path}", status_code=204)
async def remove_pair(symbol: str) -> None:
    """Remove a trading pair from watch list."""
    engine = PaperEngine.get_instance()
    if not engine.remove_watched_pair(symbol):
        raise HTTPException(status_code=404, detail=f"Pair {symbol} not found")
    logger.info("Pair removed: %s", symbol)


@router.delete("/pairs", status_code=200)
async def remove_all_pairs() -> dict[str, int]:
    """Remove all watched pairs."""
    engine = PaperEngine.get_instance()
    count = engine.clear_all_watched_pairs()
    logger.info("All pairs removed (%d)", count)
    return {"removed": count}


# ---- Available Pairs ----

@router.get("/available-pairs", response_model=list[str])
async def available_pairs() -> list[str]:
    """List available trading pairs (from exchange or simulated fallback)."""
    market = MarketDataProvider.get_instance()
    return await market.get_available_pairs()


# ---- Orders ----

@router.get("/orders", response_model=list[OrderResponse])
async def list_orders(
    status: str | None = Query(None, description="Filter by status"),
) -> list[OrderResponse]:
    """List all orders."""
    engine = get_engine()
    orders = engine.get_orders(status=status)
    return [OrderResponse(**o) for o in orders]


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def place_order(body: PlaceOrderRequest) -> OrderResponse:
    """Place a manual order.

    Routes to the correct exchange based on the pair's quote currency,
    mirroring the same logic used by quick-buy.
    """
    from ctrade.core.config_store import RuntimeConfigStore

    engine = get_engine()

    # Route to correct exchange based on pair's quote currency
    exchange_name = ""
    exchange_id: str | None = None
    try:
        store = RuntimeConfigStore.get()
        pair_entry = store.find_exchange_for_pair(body.symbol)
        if pair_entry:
            exchange_name = pair_entry.name
            exchange_id = pair_entry.id
        else:
            exchanges = store.list_exchanges()
            if exchanges:
                ex_entry = store.get_exchange_entry(exchanges[0]["id"])
                if ex_entry:
                    exchange_name = ex_entry.name
                    exchange_id = exchanges[0]["id"]
    except RuntimeError:
        pass  # config store not initialised — engine will use defaults

    order = await engine.place_order(
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
        exchange_name=exchange_name,
        exchange_id=exchange_id,
    )
    logger.info("Order placed: %s %s %s qty=%.6f", body.side, body.order_type, body.symbol, body.quantity)
    return OrderResponse(**engine._order_to_dict(order))


@router.post("/quick-buy", response_model=QuickBuyResponse)
async def quick_buy(body: QuickBuyRequest) -> QuickBuyResponse:
    """Quick-buy: one-click market buy with auto-calculated quantity and SL/TP."""
    from ctrade.core.config_store import RuntimeConfigStore

    engine = get_engine()
    market = MarketDataProvider.get_instance()
    orch = TradingOrchestrator.get_instance()

    # Prevent duplicate positions on the same pair
    existing = engine.get_positions(status="open")
    if any(p["pair_symbol"] == body.symbol and p["side"] == "long" for p in existing):
        raise HTTPException(status_code=409, detail=f"Position already open for {body.symbol}")

    # Route to correct exchange based on pair's quote currency
    exchange_name = "paper"
    exchange_id: str | None = None
    try:
        store = RuntimeConfigStore.get()
        trading = store.get_trading()
        pair_entry = store.find_exchange_for_pair(body.symbol)
        if pair_entry:
            exchange_name = pair_entry.name
            exchange_id = pair_entry.id
        else:
            exchanges = store.list_exchanges()
            if exchanges:
                ex_entry = store.get_exchange_entry(exchanges[0]["id"])
                if ex_entry:
                    exchange_name = ex_entry.name
                    exchange_id = exchanges[0]["id"]
        risk = store.get_effective_risk(exchange_id)
    except RuntimeError:
        trading = {}
        risk = {}

    # Prevent rebuy during SL delay
    sl_rebuy_delay_hours = risk.get("sl_rebuy_delay_hours", 1.0)
    if orch._is_sl_rebuy_blocked(body.symbol, sl_rebuy_delay_hours):
        raise HTTPException(status_code=409, detail=f"Re-buy blocked: {body.symbol} hit stop-loss recently")

    max_order_usdt = trading.get("max_order_usdt", 100.0)
    stop_loss_pct = risk.get("default_stop_loss_pct", 0.03)
    take_profit_pct = risk.get("default_take_profit_pct", 0.06)

    amount_usdt = body.amount_usdt or max_order_usdt

    # Get current price — use ask for buys so limit orders fill immediately
    ticker = await market.get_ticker(body.symbol)
    price = float(ticker.ask) if float(ticker.ask) > 0 else float(ticker.last_price)
    if price <= 0:
        raise HTTPException(status_code=422, detail=f"Invalid price for {body.symbol}")

    quantity = amount_usdt / price
    sl_price = round(price * (1 - stop_loss_pct), 8)
    tp_price = round(price * (1 + take_profit_pct), 8)

    order = await engine.place_order(
        symbol=body.symbol,
        side="buy",
        order_type="market",
        quantity=quantity,
        price=price,
        strategy_name="manual_quick_buy",
        justification=f"Manual quick-buy from activity feed (${amount_usdt:.2f} USDT)",
        stop_loss=sl_price,
        take_profit=tp_price,
        exchange_name=exchange_name,
        exchange_id=exchange_id,
    )

    order_status = order.status.value if hasattr(order.status, "value") else str(order.status)

    # Log activity
    orch._log_activity(
        "buy", body.symbol,
        f"MANUAL BUY {body.symbol} {quantity:.6f} @ ${price:,.2f} → {order_status}",
        {"quantity": quantity, "price": price, "amount_usdt": amount_usdt,
         "stop_loss": sl_price, "take_profit": tp_price,
         "strategy": "manual_quick_buy", "status": order_status},
    )

    logger.info("Quick buy: %s $%.2f @ $%.4f → %s", body.symbol, amount_usdt, price, order_status)

    if order_status == "rejected":
        return QuickBuyResponse(
            success=False, symbol=body.symbol, quantity=quantity,
            price=price, amount_usdt=amount_usdt,
            stop_loss=sl_price, take_profit=tp_price,
            status=order_status, error=order.error_message,
        )

    return QuickBuyResponse(
        success=True, order_id=str(order.id), symbol=body.symbol,
        quantity=quantity, price=price, amount_usdt=amount_usdt,
        stop_loss=sl_price, take_profit=tp_price, status=order_status,
    )


# ---- Positions ----

@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    status: str | None = Query(None, description="Filter: open, closed"),
) -> list[PositionResponse]:
    """List positions."""
    engine = get_engine()

    # Refresh live prices before returning positions so P&L is up-to-date
    from ctrade.exchange.live_engine import LiveEngine
    if isinstance(engine, LiveEngine):
        try:
            await engine.refresh_live_prices()
        except Exception as exc:
            logger.warning("refresh_live_prices failed: %s", exc)

    positions = engine.get_positions(status=status)
    return [PositionResponse(**p) for p in positions]


@router.post("/positions/close-all")
async def close_all_positions() -> dict[str, Any]:
    """Close all open positions at market price."""
    engine = get_engine()
    open_positions = engine.get_positions(status="open")
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for pos in open_positions:
        try:
            order = await engine.close_position(pos["id"])
            if order and order.status == "filled":
                results.append({
                    "position_id": pos["id"],
                    "pair": pos["pair_symbol"],
                    "status": "closed",
                })
            elif order and order.status == "rejected":
                errors.append(f"{pos['pair_symbol']}: {order.error_message}")
            else:
                errors.append(f"{pos['pair_symbol']}: position not found")
        except Exception as e:
            errors.append(f"{pos['pair_symbol']}: {e}")

    logger.info("Close all positions: %d closed, %d failed", len(results), len(errors))
    return {
        "closed": len(results),
        "failed": len(errors),
        "errors": errors,
        "results": results,
    }


@router.post("/positions/{position_id}/close", response_model=OrderResponse)
async def close_position(position_id: str) -> OrderResponse:
    """Close an open position at market price."""
    engine = get_engine()
    order = await engine.close_position(position_id)
    if not order:
        raise HTTPException(status_code=404, detail="Position not found or already closed")
    logger.info("Position closed: %s", position_id)
    order_dict = engine._order_to_dict(order)
    if order.status == "rejected":
        raise HTTPException(
            status_code=422,
            detail=f"Close order rejected: {order.error_message or 'unknown error'}",
        )
    return OrderResponse(**order_dict)


# ---- Portfolio ----

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio() -> PortfolioResponse:
    """Get portfolio summary. Engine resolver handles paper vs live routing."""
    engine = get_engine()
    portfolio = await engine.get_portfolio()
    return PortfolioResponse(**portfolio)


# ---- Trade History CSV Export ----

@router.get("/history/export")
async def export_trade_history() -> StreamingResponse:
    """Export closed positions as a CSV file."""
    engine = get_engine()
    positions = engine.get_positions(status="closed")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "pair", "side", "entry_price", "exit_price",
        "quantity", "realized_pnl", "realized_pnl_pct",
        "fees", "strategy", "opened_at", "closed_at",
    ])
    for p in positions:
        writer.writerow([
            p.get("id", ""),
            p.get("pair_symbol", ""),
            p.get("side", ""),
            p.get("entry_price", ""),
            p.get("exit_price", ""),
            p.get("quantity", ""),
            p.get("realized_pnl", ""),
            p.get("realized_pnl_pct", ""),
            p.get("fees_total", ""),
            p.get("strategy_name", ""),
            p.get("opened_at", ""),
            p.get("closed_at", ""),
        ])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trade_history.csv"},
    )


# ---- Ticker ----

@router.get("/ticker/{symbol:path}", response_model=TickerResponse)
async def get_ticker(symbol: str) -> TickerResponse:
    """Get current ticker (price) for a symbol."""
    market = MarketDataProvider.get_instance()
    ticker = await market.get_ticker(symbol)
    return TickerResponse(
        symbol=ticker.pair_symbol,
        last_price=float(ticker.last_price),
        bid=float(ticker.bid),
        ask=float(ticker.ask),
        high_24h=float(ticker.high_24h),
        low_24h=float(ticker.low_24h),
        volume_24h=float(ticker.volume_24h),
        change_pct_24h=ticker.change_pct_24h,
    )



# ---- Candles (batch) ----

@router.get("/candles", response_model=list[SymbolCandleSeries])
async def get_candles_batch(
    symbols: str = Query(..., description="Comma-separated symbols, e.g. BTC/AUD,ETH/AUD"),
    timeframe: str = Query("1h", description="Candle timeframe: 1m, 5m, 15m, 1h"),
    limit: int = Query(100, ge=1, le=500, description="Number of candles per symbol"),
) -> list[SymbolCandleSeries]:
    """Fetch OHLCV candle close prices for multiple symbols concurrently."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return []
    if len(symbol_list) > 20:
        raise HTTPException(status_code=400, detail="Maximum 20 symbols per request")

    market = MarketDataProvider.get_instance()

    async def _fetch(sym: str) -> SymbolCandleSeries | None:
        try:
            candles = await market.get_candles(sym, timeframe, limit)
            return SymbolCandleSeries(
                symbol=sym,
                candles=[
                    CandlePoint(time=c.time.isoformat(), close=float(c.close))
                    for c in candles
                ],
            )
        except Exception:
            logger.warning("Failed to fetch candles for %s", sym, exc_info=True)
            return None

    results = await asyncio.gather(*[_fetch(sym) for sym in symbol_list])
    return [r for r in results if r is not None]


# ---- Activity Log ----

@router.get("/activity", response_model=list[ActivityEntry])
async def activity_log() -> list[ActivityEntry]:
    """Get recent activity log from the trading engine."""
    orch = TradingOrchestrator.get_instance()
    return [ActivityEntry(**e) for e in orch.get_activity_log()]


@router.post("/activity/clear")
async def clear_activity() -> dict[str, int]:
    """Clear the activity log."""
    orch = TradingOrchestrator.get_instance()
    count = orch.clear_activity_log()
    logger.info("Activity log cleared (%d entries)", count)
    return {"cleared": count}


# ---- Engine Control ----

@router.get("/engine/status", response_model=EngineStatusResponse)
async def engine_status() -> EngineStatusResponse:
    """Get trading engine status."""
    orch = TradingOrchestrator.get_instance()
    return EngineStatusResponse(**orch.get_status())


@router.post("/engine/start", response_model=EngineStatusResponse)
async def start_engine(body: EngineStartRequest | None = None) -> EngineStatusResponse:
    """Start the trading engine."""
    orch = TradingOrchestrator.get_instance()
    interval = body.interval if body else None
    started = await orch.start(interval=interval)
    if not started:
        raise HTTPException(status_code=409, detail="Engine already running")
    logger.info("Trading engine started")
    return EngineStatusResponse(**orch.get_status())


@router.post("/engine/stop", response_model=EngineStatusResponse)
async def stop_engine() -> EngineStatusResponse:
    """Stop the trading engine."""
    orch = TradingOrchestrator.get_instance()
    stopped = await orch.stop()
    if not stopped:
        raise HTTPException(status_code=409, detail="Engine not running")
    logger.info("Trading engine stopped")
    return EngineStatusResponse(**orch.get_status())


@router.post("/engine/reset")
async def reset_paper_engine() -> dict[str, Any]:
    """Reset paper trading to initial $10K balance.

    Stops the engine if running, clears all orders/positions/history,
    and restores the starting balance.  Cannot be undone.
    """
    # Stop engine first if running
    orch = TradingOrchestrator.get_instance()
    try:
        await orch.stop()
    except Exception:
        pass  # Already stopped — that's fine

    engine = PaperEngine.get_instance()
    await engine.reset_to_defaults()
    logger.info("Paper engine reset")

    return {"success": True, "balance": 10_000.0, "message": "Paper trading reset to $10,000"}
