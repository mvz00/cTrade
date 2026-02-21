"""Trading orchestrator — background loop that drives the trading engine.

Periodically fetches candles for watched pairs, runs technical analysis,
generates signals, and executes trades through the paper engine.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

from uuid import uuid4

from ctrade.analysis.technical.engine import TechnicalAnalysisEngine
from ctrade.core.config_store import RuntimeConfigStore
from ctrade.core.enums import PositionStatus, SignalAction
from ctrade.core.models import Signal
from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
from ctrade.feeds.onchain import OnChainFeed
from ctrade.feeds.sentiment import SentimentFeed
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
        # Write-through to audit log
        fire_and_forget(self._persist_activity(entry))

    # ---- Database persistence ----

    async def hydrate_from_db(self) -> None:
        """Load recent activity from the audit_log table."""
        if not is_db_ready():
            logger.info("DB not available — TradingOrchestrator starting with empty activity log")
            return

        async def _load(session, _resolver):
            from sqlalchemy import select
            from ctrade.db.models import AuditLogModel

            stmt = (
                select(AuditLogModel)
                .where(AuditLogModel.event_type == "activity")
                .order_by(AuditLogModel.created_at.desc())
                .limit(_MAX_ACTIVITY_LOG)
            )
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "time": r.created_at.isoformat(),
                    "type": r.details.get("type", "info"),
                    "pair": r.details.get("pair", ""),
                    "message": r.details.get("message", ""),
                    "details": r.details.get("details", {}),
                }
                for r in reversed(rows)
            ]

        loaded = await run_db_operation(_load, description="hydrate TradingOrchestrator")
        if loaded:
            self._activity_log = loaded
            logger.info("Hydrated orchestrator activity log: %d entries", len(loaded))

    async def _persist_activity(self, entry: dict[str, Any]) -> None:
        """Write-through: persist an activity entry to the audit_log table."""
        async def _do(session, _resolver):
            from ctrade.db.models import AuditLogModel
            audit = AuditLogModel(
                event_type="activity",
                entity_type="orchestrator",
                details=entry,
            )
            session.add(audit)
        await run_db_operation(_do, description="persist activity log")

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
        """Analyze a single pair using 3-way signal fusion and potentially trade.

        Blends up to three intelligence sources with configurable weights:
        * Technical analysis (indicators + CMC momentum) — default 0.50
        * Sentiment (FinBERT-classified news/social)   — default 0.30
        * On-chain metrics (hash rate, volume, etc.)    — default 0.20

        If a source is unavailable (returns None), its weight is redistributed
        proportionally to the available sources.
        """
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

        # ---- Gather all intelligence sources ----

        # 1. Technical score (always available) + momentum blend
        cmc_feed = CoinMarketCapFeed.get_instance()
        momentum_score = cmc_feed.get_momentum_score(pair)
        raw_tech_score = signal.technical_score or 0.5

        # Blend momentum into technical: 60% TA + 40% momentum (when available)
        if momentum_score is not None:
            tech_score = 0.60 * raw_tech_score + 0.40 * momentum_score
        else:
            tech_score = raw_tech_score

        # 2. Sentiment score (may be None if feed not ready)
        sentiment_feed = SentimentFeed.get_instance()
        sentiment_score = sentiment_feed.get_sentiment_score(pair)

        # 3. On-chain score (may be None if feed not ready)
        onchain_feed = OnChainFeed.get_instance()
        onchain_score = onchain_feed.get_onchain_score(pair)

        # ---- Weighted fusion with proportional redistribution ----

        raw_weights = {
            "technical": strategy.get("technical_weight", 0.50),
            "sentiment": strategy.get("sentiment_weight", 0.30),
            "onchain": strategy.get("onchain_weight", 0.20),
        }

        scores: dict[str, float] = {"technical": tech_score}
        if sentiment_score is not None:
            scores["sentiment"] = sentiment_score
        if onchain_score is not None:
            scores["onchain"] = onchain_score

        # Redistribute unavailable weights proportionally
        available_weight = sum(raw_weights[k] for k in scores)
        if available_weight > 0:
            weights = {k: raw_weights[k] / available_weight for k in scores}
        else:
            weights = {"technical": 1.0}

        composite = sum(scores[k] * weights[k] for k in scores)
        composite = round(max(0.0, min(1.0, composite)), 4)

        # ---- Multi-source agreement bonus ----
        # If all available sources agree (all >0.55 or all <0.45),
        # adjust thresholds to make it easier to trigger trades
        threshold_adjust = 0.0
        agreement = "mixed"

        if len(scores) >= 2:
            all_bullish = all(s > 0.55 for s in scores.values())
            all_bearish = all(s < 0.45 for s in scores.values())

            if all_bullish:
                agreement = "bullish"
                # Lower entry threshold, proportional to source count
                threshold_adjust = -min(0.15, 0.05 * len(scores))
            elif all_bearish:
                agreement = "bearish"
                threshold_adjust = -min(0.15, 0.05 * len(scores))

        adj_entry = entry_threshold + threshold_adjust
        adj_exit = exit_threshold - threshold_adjust

        # ---- Determine action ----
        if composite >= adj_entry:
            action = SignalAction.BUY
        elif composite <= adj_exit:
            action = SignalAction.SELL
        else:
            action = SignalAction.HOLD

        # ---- Build contributing factors ----
        contributing_factors = {**signal.contributing_factors}

        if momentum_score is not None:
            contributing_factors["momentum"] = {
                "score": momentum_score,
                "signal": (
                    "bullish" if momentum_score > 0.6
                    else "bearish" if momentum_score < 0.4
                    else "neutral"
                ),
            }

        if sentiment_score is not None:
            contributing_factors["sentiment"] = sentiment_feed.get_contributing_factors(pair)

        if onchain_score is not None:
            contributing_factors["onchain"] = onchain_feed.get_contributing_factors(pair)

        contributing_factors["fusion"] = {
            "composite": composite,
            "weights": {k: round(v, 4) for k, v in weights.items()},
            "scores": {k: round(v, 4) for k, v in scores.items()},
            "agreement": agreement,
            "threshold_adjust": round(threshold_adjust, 4),
            "adj_entry": round(adj_entry, 4),
            "adj_exit": round(adj_exit, 4),
            "sources_available": len(scores),
        }

        # Determine strategy name based on available sources
        source_names = list(scores.keys())
        strategy_name = "+".join(source_names)

        # Build enriched signal
        signal = Signal(
            id=uuid4(),
            pair_symbol=signal.pair_symbol,
            action=action,
            confidence=round(abs(composite - 0.5) * 2, 4),
            technical_score=tech_score,
            sentiment_score=sentiment_score,
            onchain_score=onchain_score,
            strategy_name=strategy_name,
            contributing_factors=contributing_factors,
        )

        # Store signal
        signal_mgr.add_signal(signal, indicators)

        # Check stop-loss / take-profit for open positions
        await self._check_sl_tp(pair, engine, market, stop_loss_pct, take_profit_pct)

        if signal.action == SignalAction.HOLD:
            extras = []
            if sentiment_score is not None:
                extras.append(f"sentiment: {sentiment_score:.2f}")
            if onchain_score is not None:
                extras.append(f"onchain: {onchain_score:.2f}")
            extra_str = f" ({', '.join(extras)})" if extras else ""
            self._log_activity(
                "signal", pair,
                f"HOLD {pair} (confidence: {signal.confidence:.2f}{extra_str})",
                {"confidence": signal.confidence, "action": "HOLD",
                 "composite": composite, "agreement": agreement},
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

            strategy_label = signal.strategy_name or "technical"

            if quantity > 0:
                order = engine.place_order(
                    symbol=pair,
                    side="buy",
                    order_type="market",
                    quantity=quantity,
                    signal_id=str(signal.id),
                    strategy_name=strategy_label,
                )
                logger.info(
                    "AUTO BUY %s: qty=%.6f @ %.2f (confidence=%.2f, budget=$%.2f, strategy=%s) → %s",
                    pair, quantity, price, signal.confidence, position_budget,
                    strategy_label, order.status,
                )
                self._log_activity(
                    "buy", pair,
                    f"AUTO BUY {pair} {quantity:.6f} @ ${price:,.2f} (${position_budget:.2f})",
                    {
                        "quantity": quantity, "price": price,
                        "budget": position_budget, "confidence": signal.confidence,
                        "composite": composite, "agreement": agreement,
                        "strategy": strategy_label,
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
                        {"position_id": pos["id"], "pnl": pnl,
                         "composite": composite, "agreement": agreement},
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
