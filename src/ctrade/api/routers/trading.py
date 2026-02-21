"""Trading API endpoints — pairs, orders, positions, portfolio, engine control."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ctrade.api.schemas.trading import (
    ActivityEntry,
    AddPairRequest,
    AddPairsBatchRequest,
    EngineStartRequest,
    EngineStatusResponse,
    OrderResponse,
    PairResponse,
    PlaceOrderRequest,
    PortfolioResponse,
    PositionResponse,
    TickerResponse,
)
from ctrade.core.config_store import RuntimeConfigStore
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.strategy.orchestrator import TradingOrchestrator

router = APIRouter(prefix="/trading", tags=["trading"])


# ---- Watched Pairs ----

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
    return PairResponse(symbol=body.symbol)


@router.post("/pairs/batch", response_model=list[PairResponse], status_code=201)
async def add_pairs_batch(body: AddPairsBatchRequest) -> list[PairResponse]:
    """Add multiple trading pairs at once."""
    engine = PaperEngine.get_instance()
    added = []
    for symbol in body.symbols:
        if engine.add_watched_pair(symbol):
            added.append(PairResponse(symbol=symbol))
    return added


@router.delete("/pairs/{symbol:path}", status_code=204)
async def remove_pair(symbol: str) -> None:
    """Remove a trading pair from watch list."""
    engine = PaperEngine.get_instance()
    if not engine.remove_watched_pair(symbol):
        raise HTTPException(status_code=404, detail=f"Pair {symbol} not found")


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
    engine = PaperEngine.get_instance()
    orders = engine.get_orders(status=status)
    return [OrderResponse(**o) for o in orders]


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def place_order(body: PlaceOrderRequest) -> OrderResponse:
    """Place a manual order."""
    engine = PaperEngine.get_instance()
    order = engine.place_order(
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        quantity=body.quantity,
        price=body.price,
    )
    return OrderResponse(**PaperEngine._order_to_dict(order))


# ---- Positions ----

@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    status: str | None = Query(None, description="Filter: open, closed"),
) -> list[PositionResponse]:
    """List positions."""
    engine = PaperEngine.get_instance()
    positions = engine.get_positions(status=status)
    return [PositionResponse(**p) for p in positions]


@router.post("/positions/{position_id}/close", response_model=OrderResponse)
async def close_position(position_id: str) -> OrderResponse:
    """Close an open position at market price."""
    engine = PaperEngine.get_instance()
    order = engine.close_position(position_id)
    if not order:
        raise HTTPException(status_code=404, detail="Position not found or already closed")
    return OrderResponse(**PaperEngine._order_to_dict(order))


# ---- Portfolio ----

@router.get("/portfolio", response_model=PortfolioResponse)
async def get_portfolio() -> PortfolioResponse:
    """Get portfolio summary.  In live mode, fetches real exchange balances."""
    store = RuntimeConfigStore.get()
    mode = store.get_trading()["mode"]

    if mode == "live":
        market = MarketDataProvider.get_instance()
        live_portfolio = await market.fetch_exchange_portfolio()
        if live_portfolio:
            return PortfolioResponse(**live_portfolio)
        # Fall through to paper if live fetch fails (no exchange configured)

    engine = PaperEngine.get_instance()
    return PortfolioResponse(**engine.get_portfolio())


# ---- Trade History CSV Export ----

@router.get("/history/export")
async def export_trade_history() -> StreamingResponse:
    """Export closed positions as a CSV file."""
    engine = PaperEngine.get_instance()
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


# ---- Activity Log ----

@router.get("/activity", response_model=list[ActivityEntry])
async def activity_log() -> list[ActivityEntry]:
    """Get recent activity log from the trading engine."""
    orch = TradingOrchestrator.get_instance()
    return [ActivityEntry(**e) for e in orch.get_activity_log()]


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
    return EngineStatusResponse(**orch.get_status())


@router.post("/engine/stop", response_model=EngineStatusResponse)
async def stop_engine() -> EngineStatusResponse:
    """Stop the trading engine."""
    orch = TradingOrchestrator.get_instance()
    stopped = await orch.stop()
    if not stopped:
        raise HTTPException(status_code=409, detail="Engine not running")
    return EngineStatusResponse(**orch.get_status())
