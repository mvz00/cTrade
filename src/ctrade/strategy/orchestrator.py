"""Trading orchestrator — background loop that drives the trading engine.

Periodically fetches candles for watched pairs, runs technical analysis,
generates signals, and executes trades through the paper engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from ctrade.analysis.technical.engine import TechnicalAnalysisEngine
from ctrade.core.config_store import RuntimeConfigStore
from ctrade.core.enums import PositionStatus, SignalAction
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.strategy.signal_manager import SignalManager

logger = logging.getLogger(__name__)


class TradingOrchestrator:
    """Background trading loop singleton."""

    _instance: ClassVar[TradingOrchestrator | None] = None

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._tick_count = 0
        self._last_tick: datetime | None = None
        self._interval_seconds = 30
        self._ta_engine = TechnicalAnalysisEngine()

    @classmethod
    def get_instance(cls) -> TradingOrchestrator:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    @property
    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "tick_count": self._tick_count,
            "last_tick": self._last_tick.isoformat() if self._last_tick else None,
            "interval_seconds": self._interval_seconds,
        }

    async def start(self, interval: int | None = None) -> bool:
        """Start the trading loop."""
        if self._running:
            return False
        if interval:
            self._interval_seconds = interval
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Trading orchestrator started (interval=%ds)", self._interval_seconds)
        return True

    async def stop(self) -> bool:
        """Stop the trading loop."""
        if not self._running:
            return False
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Trading orchestrator stopped")
        return True

    async def _run_loop(self) -> None:
        """Main trading loop."""
        while self._running:
            try:
                await self._tick()
                self._tick_count += 1
                self._last_tick = datetime.now(timezone.utc)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in trading tick")

            try:
                await asyncio.sleep(self._interval_seconds)
            except asyncio.CancelledError:
                break

    async def _tick(self) -> None:
        """Single trading tick: analyze all watched pairs."""
        engine = PaperEngine.get_instance()
        market = MarketDataProvider.get_instance()
        signal_mgr = SignalManager.get_instance()

        pairs = engine.get_watched_pairs()
        if not pairs:
            return

        try:
            store = RuntimeConfigStore.get()
            strategy = store.get_strategy()
            risk = store.get_risk()
        except RuntimeError:
            strategy = {}
            risk = {}

        entry_threshold = strategy.get("entry_confidence_threshold", 0.70)
        exit_threshold = strategy.get("exit_confidence_threshold", 0.30)
        max_position_pct = risk.get("max_position_pct", 0.10)
        max_open = store.get_trading().get("max_open_positions", 5) if store else 5
        stop_loss_pct = risk.get("default_stop_loss_pct", 0.03)
        take_profit_pct = risk.get("default_take_profit_pct", 0.06)

        for pair in pairs:
            try:
                await self._process_pair(
                    pair, engine, market, signal_mgr,
                    entry_threshold, exit_threshold,
                    max_position_pct, max_open,
                    stop_loss_pct, take_profit_pct,
                    strategy,
                )
            except Exception:
                logger.exception("Error processing pair %s", pair)

    async def _process_pair(
        self,
        pair: str,
        engine: PaperEngine,
        market: MarketDataProvider,
        signal_mgr: SignalManager,
        entry_threshold: float,
        exit_threshold: float,
        max_position_pct: float,
        max_open: int,
        stop_loss_pct: float,
        take_profit_pct: float,
        strategy: dict[str, Any],
    ) -> None:
        """Analyze a single pair and potentially trade."""
        # Fetch candles
        candles = await market.get_candles(pair, "1h", 100)
        if len(candles) < 30:
            return

        # Run technical analysis
        signal, indicators = self._ta_engine.analyze(
            candles,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            rsi_period=strategy.get("rsi_period", 14),
            macd_fast=strategy.get("macd_fast", 12),
            macd_slow=strategy.get("macd_slow", 26),
            macd_signal=strategy.get("macd_signal", 9),
        )

        # Store signal
        signal_mgr.add_signal(signal, indicators)

        # Check stop-loss / take-profit for open positions
        await self._check_sl_tp(pair, engine, market, stop_loss_pct, take_profit_pct)

        if signal.action == SignalAction.HOLD:
            return

        # Risk checks
        portfolio = engine.get_portfolio()
        open_positions = portfolio["open_positions"]

        if signal.action == SignalAction.BUY:
            if open_positions >= max_open:
                logger.debug("Max open positions reached (%d), skipping BUY for %s", max_open, pair)
                return

            # Calculate position size
            total_value = portfolio["total_value_usd"]
            position_budget = total_value * max_position_pct
            ticker = await market.get_ticker(pair)
            price = float(ticker.last_price)
            if price <= 0:
                return
            quantity = position_budget / price

            if quantity > 0:
                order = engine.place_order(
                    symbol=pair,
                    side="buy",
                    order_type="market",
                    quantity=quantity,
                    signal_id=str(signal.id),
                    strategy_name="technical",
                )
                logger.info(
                    "AUTO BUY %s: qty=%.6f @ %.2f (confidence=%.2f) → %s",
                    pair, quantity, price, signal.confidence, order.status,
                )

        elif signal.action == SignalAction.SELL:
            # Close any open long position
            positions = engine.get_positions(status="open")
            for pos in positions:
                if pos["pair_symbol"] == pair and pos["side"] == "long":
                    engine.close_position(pos["id"])
                    logger.info("AUTO SELL %s: closed position %s", pair, pos["id"])

    async def _check_sl_tp(
        self,
        pair: str,
        engine: PaperEngine,
        market: MarketDataProvider,
        stop_loss_pct: float,
        take_profit_pct: float,
    ) -> None:
        """Check stop-loss and take-profit for open positions."""
        positions = engine.get_positions(status="open")
        for pos in positions:
            if pos["pair_symbol"] != pair:
                continue

            current_price = pos.get("current_price")
            if not current_price:
                ticker = await market.get_ticker(pair)
                current_price = float(ticker.last_price)

            entry_price = pos["entry_price"]
            if entry_price <= 0:
                continue

            if pos["side"] == "long":
                pnl_pct = (current_price - entry_price) / entry_price
                if pnl_pct <= -stop_loss_pct:
                    engine.close_position(pos["id"])
                    logger.info("STOP LOSS triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                elif pnl_pct >= take_profit_pct:
                    engine.close_position(pos["id"])
                    logger.info("TAKE PROFIT triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
