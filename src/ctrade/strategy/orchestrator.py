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

_DEFAULT_PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]
_MAX_ACTIVITY_LOG = 100


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
        self._activity_log: list[dict[str, Any]] = []

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

    def get_activity_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return recent activity log entries (newest first)."""
        return list(reversed(self._activity_log[-limit:]))

    def _log_activity(
        self,
        activity_type: str,
        pair: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Add an entry to the activity log."""
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "type": activity_type,
            "pair": pair,
            "message": message,
            "details": details or {},
        }
        self._activity_log.append(entry)
        # Cap the log size
        if len(self._activity_log) > _MAX_ACTIVITY_LOG:
            self._activity_log = self._activity_log[-_MAX_ACTIVITY_LOG:]

    async def start(self, interval: int | None = None) -> bool:
        """Start the trading loop."""
        if self._running:
            return False
        if interval:
            self._interval_seconds = interval
        self._running = True

        # Auto-add default pairs if none are watched
        engine = PaperEngine.get_instance()
        if not engine.get_watched_pairs():
            for pair in _DEFAULT_PAIRS:
                engine.add_watched_pair(pair)
            logger.info("Auto-added %d default trading pairs", len(_DEFAULT_PAIRS))
            self._log_activity(
                "info", "ALL",
                f"Auto-added {len(_DEFAULT_PAIRS)} default pairs: {', '.join(_DEFAULT_PAIRS)}",
            )

        self._task = asyncio.create_task(self._run_loop())
        logger.info("Trading orchestrator started (interval=%ds)", self._interval_seconds)
        self._log_activity("info", "ALL", "Auto-trading engine started")
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
        self._log_activity("info", "ALL", "Auto-trading engine stopped")
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
            trading = store.get_trading()
        except RuntimeError:
            strategy = {}
            risk = {}
            trading = {}

        entry_threshold = strategy.get("entry_confidence_threshold", 0.70)
        exit_threshold = strategy.get("exit_confidence_threshold", 0.30)
        max_position_pct = risk.get("max_position_pct", 0.10)
        max_open = trading.get("max_open_positions", 5)
        max_order_usdt = trading.get("max_order_usdt", 100.0)
        stop_loss_pct = risk.get("default_stop_loss_pct", 0.03)
        take_profit_pct = risk.get("default_take_profit_pct", 0.06)

        for pair in pairs:
            try:
                await self._process_pair(
                    pair, engine, market, signal_mgr,
                    entry_threshold, exit_threshold,
                    max_position_pct, max_open,
                    max_order_usdt,
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
        max_order_usdt: float,
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
            self._log_activity(
                "signal", pair,
                f"HOLD {pair} (confidence: {signal.confidence:.2f})",
                {"confidence": signal.confidence, "action": "HOLD"},
            )
            return

        # Risk checks
        portfolio = engine.get_portfolio()
        open_positions = portfolio["open_positions"]

        if signal.action == SignalAction.BUY:
            if open_positions >= max_open:
                logger.debug("Max open positions reached (%d), skipping BUY for %s", max_open, pair)
                return

            # Calculate position size: min of USDT cap and portfolio % limit
            total_value = portfolio["total_value_usd"]
            position_budget = min(max_order_usdt, total_value * max_position_pct)
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
                    "AUTO BUY %s: qty=%.6f @ %.2f (confidence=%.2f, budget=$%.2f) → %s",
                    pair, quantity, price, signal.confidence, position_budget, order.status,
                )
                self._log_activity(
                    "buy", pair,
                    f"AUTO BUY {pair} {quantity:.6f} @ ${price:,.2f} (${position_budget:.2f})",
                    {
                        "quantity": quantity, "price": price,
                        "budget": position_budget, "confidence": signal.confidence,
                        "status": str(order.status),
                    },
                )

        elif signal.action == SignalAction.SELL:
            # Close any open long position
            positions = engine.get_positions(status="open")
            for pos in positions:
                if pos["pair_symbol"] == pair and pos["side"] == "long":
                    engine.close_position(pos["id"])
                    pnl = pos.get("unrealized_pnl", 0)
                    logger.info("AUTO SELL %s: closed position %s", pair, pos["id"])
                    self._log_activity(
                        "sell", pair,
                        f"AUTO SELL {pair} — closed position (P&L: ${pnl:+.2f})",
                        {"position_id": pos["id"], "pnl": pnl},
                    )

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
                pnl_usd = (current_price - entry_price) * pos["quantity"]
                if pnl_pct <= -stop_loss_pct:
                    engine.close_position(pos["id"])
                    logger.info("STOP LOSS triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                    self._log_activity(
                        "sl", pair,
                        f"STOP LOSS {pair} {pnl_pct * 100:+.1f}% (${pnl_usd:+.2f})",
                        {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd},
                    )
                elif pnl_pct >= take_profit_pct:
                    engine.close_position(pos["id"])
                    logger.info("TAKE PROFIT triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                    self._log_activity(
                        "tp", pair,
                        f"TAKE PROFIT {pair} {pnl_pct * 100:+.1f}% (${pnl_usd:+.2f})",
                        {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd},
                    )
