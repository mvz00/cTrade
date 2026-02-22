"""Trading orchestrator — background loop that drives the trading engine.

Periodically fetches candles for watched pairs, runs technical analysis,
generates signals, and executes trades through the active engine (paper or live).
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
from ctrade.core.events import Event, EventBus, EventTypes
from ctrade.core.models import Signal
from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation
from ctrade.exchange.engine_resolver import get_engine
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine
from ctrade.feeds.coinmarketcap import CoinMarketCapFeed
from ctrade.feeds.cvd import CVDFeed
from ctrade.feeds.derivatives import DerivativesFeed
from ctrade.feeds.market_sentiment import MarketSentimentFeed
from ctrade.feeds.onchain import OnChainFeed
from ctrade.feeds.sentiment import SentimentFeed
from ctrade.feeds.social_velocity import SocialVelocityFeed
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

    # ---- Event publishing helpers ----

    @staticmethod
    def _publish(event_type: str, data: dict[str, Any]) -> None:
        """Publish an event to the global EventBus (sync-safe via publish_nowait)."""
        try:
            bus = EventBus.get_instance()
            bus.publish_nowait(Event(event_type=event_type, data=data))
        except Exception:
            logger.debug("EventBus unavailable — skipping publish for %s", event_type)

    @staticmethod
    def _check_alerts(pair: str, *, price: float | None = None, action: str | None = None) -> None:
        """Fire AlertManager checks and publish ALERT_TRIGGERED for any results."""
        try:
            from ctrade.notifications.alert_manager import AlertManager
            am = AlertManager.get_instance()
            triggered: list[dict[str, Any]] = []

            if price is not None:
                triggered.extend(am.check_price(pair, price))
            if action is not None:
                triggered.extend(am.check_signal(pair, action))

            for alert in triggered:
                TradingOrchestrator._publish(EventTypes.ALERT_TRIGGERED, {
                    "alert": alert,
                    "pair": pair,
                })
        except Exception:
            logger.debug("Alert check skipped for %s", pair, exc_info=True)

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
        """Single trading tick: analyze all watched pairs.

        Pairs are ranked by volatility/momentum so the biggest movers are
        evaluated (and traded) first, maximising short-trade profit potential.
        """
        engine = get_engine()
        market = MarketDataProvider.get_instance()
        signal_mgr = SignalManager.get_instance()

        pairs = engine.get_watched_pairs()
        if not pairs:
            return

        # Refresh real exchange prices for live-mode PnL display
        from ctrade.exchange.live_engine import LiveEngine

        if isinstance(engine, LiveEngine):
            try:
                await engine.refresh_live_prices()
            except Exception:
                logger.debug("Could not refresh live prices")

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

        # ---- Rank pairs by volatility (biggest movers first) ----
        ranked_pairs = self._rank_pairs_by_momentum(pairs)

        strategy_mode = strategy.get("strategy_mode", "long_only")
        short_min_1h_change_pct = strategy.get("short_min_1h_change_pct", 2.0)

        for pair in ranked_pairs:
            try:
                await self._process_pair(
                    pair, engine, market, signal_mgr,
                    entry_threshold, exit_threshold,
                    max_position_pct, max_open,
                    max_order_usdt,
                    stop_loss_pct, take_profit_pct,
                    strategy,
                    strategy_mode, short_min_1h_change_pct,
                )
            except Exception:
                logger.exception("Error processing pair %s", pair)

    def _rank_pairs_by_momentum(self, pairs: list[str]) -> list[str]:
        """Rank trading pairs by absolute momentum — biggest movers first.

        Uses CoinMarketCap data to compute a volatility score based on:
        - Absolute 1h change (weight 0.40)  — captures intraday spikes
        - Absolute 24h change (weight 0.30) — medium-term momentum
        - Volume surge (weight 0.30)        — confirms real movement

        Pairs without CMC data keep their original order (appended at end).
        """
        cmc = CoinMarketCapFeed.get_instance()
        if not cmc.is_enabled or not cmc._listings:
            return pairs

        scored: list[tuple[float, str]] = []
        unscored: list[str] = []

        for pair in pairs:
            base_symbol = pair.split("/")[0]
            listing = cmc._listings_by_symbol.get(base_symbol)
            if listing is None:
                unscored.append(pair)
                continue

            # Absolute change = bigger moves score higher (buy OR sell opportunity)
            abs_1h = abs(listing.pct_change_1h)
            abs_24h = abs(listing.pct_change_24h)

            # Volume surge relative to median
            vol_score = cmc._volume_score(listing)
            # Convert volume score (0-1, centered at 0.5) to absolute deviation
            vol_deviation = abs(vol_score - 0.5) * 2  # 0 = median, 1 = extreme

            # Weighted volatility score — higher = more volatile / bigger mover
            volatility = (
                0.40 * abs_1h
                + 0.30 * abs_24h
                + 0.30 * (vol_deviation * 20)  # Scale vol to comparable range
            )
            scored.append((volatility, pair))

        # Sort by volatility descending (biggest movers first)
        scored.sort(reverse=True, key=lambda x: x[0])
        return [pair for _, pair in scored] + unscored

    async def _process_pair(
        self,
        pair: str,
        engine: Any,
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
        strategy_mode: str = "long_only",
        short_min_1h_change_pct: float = 2.0,
    ) -> None:
        """Analyze a single pair using 7-way signal fusion and potentially trade.

        Blends up to seven intelligence sources with configurable weights:
        * Technical analysis (indicators + CMC momentum) — default 0.30
        * Sentiment (FinBERT-classified news/social)     — default 0.10
        * On-chain metrics (hash rate, volume, etc.)     — default 0.08
        * Derivatives (funding rate, OI, order book)     — default 0.17
        * Market sentiment (F&G, L/S ratio, liq data)    — default 0.17
        * CVD (cumulative volume delta divergence)       — default 0.10
        * Social velocity (mention spike detection)      — default 0.08

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

        # 4. Derivatives score (may be None if feed not ready or exchange unavailable)
        derivatives_feed = DerivativesFeed.get_instance()
        derivatives_score = derivatives_feed.get_derivatives_score(pair)

        # 5. Market sentiment score (F&G index, L/S ratio, liquidation data)
        mkt_sentiment_feed = MarketSentimentFeed.get_instance()
        market_sentiment_score = mkt_sentiment_feed.get_market_sentiment_score(pair)

        # 6. CVD score (cumulative volume delta divergence)
        cvd_feed = CVDFeed.get_instance()
        cvd_score = cvd_feed.get_cvd_score(pair)

        # 7. Social velocity score (mention spike detection)
        social_velocity_feed = SocialVelocityFeed.get_instance()
        social_velocity_score = social_velocity_feed.get_social_velocity_score(pair)

        # ---- Weighted fusion with proportional redistribution ----

        raw_weights = {
            "technical": strategy.get("technical_weight", 0.30),
            "sentiment": strategy.get("sentiment_weight", 0.10),
            "onchain": strategy.get("onchain_weight", 0.08),
            "derivatives": strategy.get("derivatives_weight", 0.17),
            "market_sentiment": strategy.get("market_sentiment_weight", 0.17),
            "cvd": strategy.get("cvd_weight", 0.10),
            "social_velocity": strategy.get("social_velocity_weight", 0.08),
        }

        scores: dict[str, float] = {"technical": tech_score}
        if sentiment_score is not None:
            scores["sentiment"] = sentiment_score
        if onchain_score is not None:
            scores["onchain"] = onchain_score
        if derivatives_score is not None:
            scores["derivatives"] = derivatives_score
        if market_sentiment_score is not None:
            scores["market_sentiment"] = market_sentiment_score
        if cvd_score is not None:
            scores["cvd"] = cvd_score
        if social_velocity_score is not None:
            scores["social_velocity"] = social_velocity_score

        # Redistribute unavailable weights proportionally
        available_weight = sum(raw_weights[k] for k in scores)
        if available_weight > 0:
            weights = {k: raw_weights[k] / available_weight for k in scores}
        else:
            weights = {"technical": 1.0}

        composite = sum(scores[k] * weights[k] for k in scores)
        composite = round(max(0.0, min(1.0, composite)), 4)

        # ---- Multi-source agreement bonus ----
        # If sources agree, adjust thresholds to make it easier to trigger trades.
        # Even a single source with a clear directional bias gets a small bonus.
        threshold_adjust = 0.0
        agreement = "mixed"

        if len(scores) >= 2:
            all_bullish = all(s > 0.52 for s in scores.values())
            all_bearish = all(s < 0.48 for s in scores.values())

            if all_bullish:
                agreement = "bullish"
                # Larger bonus: up to 0.10 per source, max 0.20
                threshold_adjust = -min(0.20, 0.10 * len(scores))
            elif all_bearish:
                agreement = "bearish"
                threshold_adjust = -min(0.20, 0.10 * len(scores))
        elif len(scores) == 1:
            # Single source with clear direction gets a small bonus
            val = list(scores.values())[0]
            if val > 0.55:
                agreement = "bullish"
                threshold_adjust = -0.05
            elif val < 0.45:
                agreement = "bearish"
                threshold_adjust = -0.05

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

        if derivatives_score is not None:
            contributing_factors["derivatives"] = derivatives_feed.get_contributing_factors(pair)

        if market_sentiment_score is not None:
            contributing_factors["market_sentiment"] = mkt_sentiment_feed.get_contributing_factors(pair)

        if cvd_score is not None:
            contributing_factors["cvd"] = cvd_feed.get_contributing_factors(pair)

        if social_velocity_score is not None:
            contributing_factors["social_velocity"] = social_velocity_feed.get_contributing_factors(pair)

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
            derivatives_score=derivatives_score,
            market_sentiment_score=market_sentiment_score,
            cvd_score=cvd_score,
            social_velocity_score=social_velocity_score,
            strategy_name=strategy_name,
            contributing_factors=contributing_factors,
        )

        # Store signal
        signal_mgr.add_signal(signal, indicators)

        # Publish signal event
        self._publish(EventTypes.SIGNAL_GENERATED, {
            "pair": pair,
            "action": signal.action.value if hasattr(signal.action, "value") else str(signal.action),
            "confidence": signal.confidence,
            "composite": composite,
            "agreement": agreement,
            "strategy": signal.strategy_name,
        })

        # Check alerts against current candle close price
        close_price = float(candles[-1].close) if candles else None
        self._check_alerts(
            pair,
            price=close_price,
            action=signal.action.value if hasattr(signal.action, "value") else str(signal.action),
        )

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
        portfolio = await engine.get_portfolio()
        open_positions = portfolio["open_positions"]

        # ---- Execute based on strategy mode ----
        if strategy_mode == "long_only":
            await self._execute_long_only(
                signal, pair, engine, market, signal_mgr,
                portfolio, open_positions, max_open, max_order_usdt,
                max_position_pct, composite, agreement,
            )
        elif strategy_mode == "short_only":
            await self._execute_short_only(
                signal, pair, engine, market, signal_mgr,
                portfolio, open_positions, max_open, max_order_usdt,
                max_position_pct, composite, agreement,
                short_min_1h_change_pct,
            )
        elif strategy_mode == "both":
            await self._execute_both(
                signal, pair, engine, market, signal_mgr,
                portfolio, open_positions, max_open, max_order_usdt,
                max_position_pct, composite, agreement,
                short_min_1h_change_pct,
            )

    # ------------------------------------------------------------------
    # Strategy mode execution helpers
    # ------------------------------------------------------------------

    async def _open_position(
        self,
        pair: str,
        side: str,
        engine: Any,
        market: MarketDataProvider,
        signal: Signal,
        portfolio: dict,
        max_order_usdt: float,
        max_position_pct: float,
        composite: float,
        agreement: str,
        cmc_info: dict | None = None,
    ) -> None:
        """Open a new position (long or short) with standard position sizing."""
        total_value = portfolio["total_value_usd"]
        position_budget = min(max_order_usdt, total_value * max_position_pct)
        ticker = await market.get_ticker(pair)
        price = float(ticker.last_price)
        if price <= 0:
            return
        quantity = position_budget / price

        strategy_label = signal.strategy_name or "technical"
        momentum_tag = ""
        if cmc_info:
            pct_1h = cmc_info.get("pct_change_1h", 0)
            momentum_tag = f" [1h: {pct_1h:+.1f}%]"

        side_label = "BUY" if side == "buy" else "SHORT"
        log_type = "buy" if side == "buy" else "sell"

        if quantity > 0:
            order = await engine.place_order(
                symbol=pair,
                side=side,
                order_type="market",
                quantity=quantity,
                signal_id=str(signal.id),
                strategy_name=strategy_label,
            )
            order_status = order.status.value if hasattr(order.status, "value") else str(order.status)
            logger.info(
                "AUTO %s %s: qty=%.6f @ %.2f (confidence=%.2f, budget=$%.2f, strategy=%s) → %s",
                side_label, pair, quantity, price, signal.confidence, position_budget,
                strategy_label, order_status,
            )

            if order_status == "rejected":
                self._log_activity(
                    "error", pair,
                    f"{side_label} REJECTED {pair}: {order.error_message or 'unknown error'}",
                    {
                        "quantity": quantity, "price": price,
                        "budget": position_budget, "confidence": signal.confidence,
                        "composite": composite, "agreement": agreement,
                        "strategy": strategy_label,
                        "status": order_status,
                        "error": order.error_message,
                    },
                )
            else:
                self._log_activity(
                    log_type, pair,
                    f"AUTO {side_label} {pair} {quantity:.6f} @ ${price:,.2f}{momentum_tag} → {order_status}",
                    {
                        "quantity": quantity, "price": price,
                        "budget": position_budget, "confidence": signal.confidence,
                        "composite": composite, "agreement": agreement,
                        "strategy": strategy_label,
                        "status": order_status,
                        "momentum": cmc_info,
                    },
                )
            self._publish(EventTypes.ORDER_CREATED, {
                "pair": pair, "side": side, "quantity": quantity,
                "price": price, "status": order_status,
            })

    async def _close_positions(
        self,
        pair: str,
        target_side: str,
        engine: Any,
        composite: float,
        agreement: str,
    ) -> None:
        """Close all open positions for a pair on a given side."""
        positions = engine.get_positions(status="open")
        for pos in positions:
            if pos["pair_symbol"] == pair and pos["side"] == target_side:
                close_order = await engine.close_position(pos["id"])
                pnl = pos.get("unrealized_pnl", 0)

                if close_order and hasattr(close_order, "status"):
                    close_status = close_order.status.value if hasattr(close_order.status, "value") else str(close_order.status)
                else:
                    close_status = "unknown"

                side_label = "SELL" if target_side == "long" else "CLOSE SHORT"
                log_type = "sell" if target_side == "long" else "buy"

                if close_status == "rejected":
                    logger.warning("AUTO %s %s: REJECTED — %s", side_label, pair, close_order.error_message)
                    self._log_activity(
                        "error", pair,
                        f"{side_label} REJECTED {pair}: {close_order.error_message or 'unknown error'}",
                        {"position_id": pos["id"], "pnl": pnl,
                         "composite": composite, "agreement": agreement,
                         "error": close_order.error_message},
                    )
                else:
                    logger.info("AUTO %s %s: closed position %s → %s", side_label, pair, pos["id"], close_status)
                    self._log_activity(
                        log_type, pair,
                        f"AUTO {side_label} {pair} — closed position (P&L: ${pnl:+.2f}) → {close_status}",
                        {"position_id": pos["id"], "pnl": pnl,
                         "composite": composite, "agreement": agreement},
                    )
                    self._publish(EventTypes.POSITION_CLOSED, {
                        "pair": pair, "position_id": pos["id"],
                        "pnl": pnl, "reason": "signal",
                    })

    async def _execute_long_only(
        self, signal: Signal, pair: str, engine: Any, market: MarketDataProvider,
        signal_mgr: SignalManager, portfolio: dict, open_positions: int,
        max_open: int, max_order_usdt: float, max_position_pct: float,
        composite: float, agreement: str,
    ) -> None:
        """Long-only mode: BUY opens long, SELL closes long."""
        cmc_info = CoinMarketCapFeed.get_instance().get_volatility_info(pair)

        if signal.action == SignalAction.BUY:
            if open_positions >= max_open:
                return
            existing = engine.get_positions(status="open")
            if any(p["pair_symbol"] == pair and p["side"] == "long" for p in existing):
                return
            await self._open_position(
                pair, "buy", engine, market, signal, portfolio,
                max_order_usdt, max_position_pct, composite, agreement, cmc_info,
            )

        elif signal.action == SignalAction.SELL:
            await self._close_positions(pair, "long", engine, composite, agreement)

    async def _execute_short_only(
        self, signal: Signal, pair: str, engine: Any, market: MarketDataProvider,
        signal_mgr: SignalManager, portfolio: dict, open_positions: int,
        max_open: int, max_order_usdt: float, max_position_pct: float,
        composite: float, agreement: str, short_min_1h_change_pct: float,
    ) -> None:
        """Short-only mode: SELL opens short (momentum filter), BUY closes short."""
        cmc_info = CoinMarketCapFeed.get_instance().get_volatility_info(pair)

        if signal.action == SignalAction.SELL:
            # Momentum filter: only short high-volatility pairs
            if cmc_info is None or abs(cmc_info.get("pct_change_1h", 0)) < short_min_1h_change_pct:
                pct = cmc_info["pct_change_1h"] if cmc_info else "N/A"
                self._log_activity(
                    "signal", pair,
                    f"SHORT_ONLY skip {pair}: 1h change {pct}% < {short_min_1h_change_pct}% threshold",
                    {"pair": pair, "pct_change_1h": pct, "threshold": short_min_1h_change_pct},
                )
                return

            if open_positions >= max_open:
                return
            existing = engine.get_positions(status="open")
            if any(p["pair_symbol"] == pair and p["side"] == "short" for p in existing):
                return
            await self._open_position(
                pair, "sell", engine, market, signal, portfolio,
                max_order_usdt, max_position_pct, composite, agreement, cmc_info,
            )

        elif signal.action == SignalAction.BUY:
            await self._close_positions(pair, "short", engine, composite, agreement)

    async def _execute_both(
        self, signal: Signal, pair: str, engine: Any, market: MarketDataProvider,
        signal_mgr: SignalManager, portfolio: dict, open_positions: int,
        max_open: int, max_order_usdt: float, max_position_pct: float,
        composite: float, agreement: str, short_min_1h_change_pct: float,
    ) -> None:
        """Both mode: BUY closes short + opens long, SELL closes long + opens short."""
        cmc_info = CoinMarketCapFeed.get_instance().get_volatility_info(pair)

        if signal.action == SignalAction.BUY:
            # Close any short first
            await self._close_positions(pair, "short", engine, composite, agreement)

            # Re-check open count after closing
            portfolio = await engine.get_portfolio()
            open_positions = portfolio["open_positions"]

            if open_positions >= max_open:
                return
            existing = engine.get_positions(status="open")
            if any(p["pair_symbol"] == pair and p["side"] == "long" for p in existing):
                return
            await self._open_position(
                pair, "buy", engine, market, signal, portfolio,
                max_order_usdt, max_position_pct, composite, agreement, cmc_info,
            )

        elif signal.action == SignalAction.SELL:
            # Close any long first
            await self._close_positions(pair, "long", engine, composite, agreement)

            # Momentum filter for short entry
            if cmc_info is None or abs(cmc_info.get("pct_change_1h", 0)) < short_min_1h_change_pct:
                return

            # Re-check open count after closing
            portfolio = await engine.get_portfolio()
            open_positions = portfolio["open_positions"]

            if open_positions >= max_open:
                return
            existing = engine.get_positions(status="open")
            if any(p["pair_symbol"] == pair and p["side"] == "short" for p in existing):
                return
            await self._open_position(
                pair, "sell", engine, market, signal, portfolio,
                max_order_usdt, max_position_pct, composite, agreement, cmc_info,
            )

    async def _check_sl_tp(
        self,
        pair: str,
        engine: Any,
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
                    sl_order = await engine.close_position(pos["id"])
                    sl_status = (sl_order.status.value if sl_order and hasattr(sl_order.status, "value") else "unknown") if sl_order else "failed"
                    if sl_status == "rejected":
                        logger.warning("STOP LOSS close REJECTED for %s: %s", pair, sl_order.error_message)
                        self._log_activity(
                            "error", pair,
                            f"STOP LOSS close REJECTED {pair}: {sl_order.error_message or 'unknown'}",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd, "error": sl_order.error_message},
                        )
                    else:
                        logger.info("STOP LOSS triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                        self._log_activity(
                            "sl", pair,
                            f"STOP LOSS {pair} {pnl_pct * 100:+.1f}% (${pnl_usd:+.2f})",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd},
                        )
                        self._publish(EventTypes.STOP_LOSS_HIT, {
                            "pair": pair, "position_id": pos["id"],
                            "pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd,
                        })
                elif pnl_pct >= take_profit_pct:
                    tp_order = await engine.close_position(pos["id"])
                    tp_status = (tp_order.status.value if tp_order and hasattr(tp_order.status, "value") else "unknown") if tp_order else "failed"
                    if tp_status == "rejected":
                        logger.warning("TAKE PROFIT close REJECTED for %s: %s", pair, tp_order.error_message)
                        self._log_activity(
                            "error", pair,
                            f"TAKE PROFIT close REJECTED {pair}: {tp_order.error_message or 'unknown'}",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd, "error": tp_order.error_message},
                        )
                    else:
                        logger.info("TAKE PROFIT triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                        self._log_activity(
                            "tp", pair,
                            f"TAKE PROFIT {pair} {pnl_pct * 100:+.1f}% (${pnl_usd:+.2f})",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd},
                        )
                        self._publish(EventTypes.TAKE_PROFIT_HIT, {
                            "pair": pair, "position_id": pos["id"],
                            "pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd,
                        })

            elif pos["side"] == "short":
                # For shorts: price UP = loss, price DOWN = profit
                pnl_pct = (entry_price - current_price) / entry_price
                pnl_usd = (entry_price - current_price) * pos["quantity"]

                if pnl_pct <= -stop_loss_pct:
                    sl_order = await engine.close_position(pos["id"])
                    sl_status = (sl_order.status.value if sl_order and hasattr(sl_order.status, "value") else "unknown") if sl_order else "failed"
                    if sl_status == "rejected":
                        logger.warning("SHORT STOP LOSS close REJECTED for %s: %s", pair, sl_order.error_message)
                        self._log_activity(
                            "error", pair,
                            f"SHORT STOP LOSS close REJECTED {pair}: {sl_order.error_message or 'unknown'}",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd, "error": sl_order.error_message},
                        )
                    else:
                        logger.info("SHORT STOP LOSS triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                        self._log_activity(
                            "sl", pair,
                            f"SHORT STOP LOSS {pair} {pnl_pct * 100:+.1f}% (${pnl_usd:+.2f})",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd},
                        )
                        self._publish(EventTypes.STOP_LOSS_HIT, {
                            "pair": pair, "position_id": pos["id"],
                            "pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd,
                        })

                elif pnl_pct >= take_profit_pct:
                    tp_order = await engine.close_position(pos["id"])
                    tp_status = (tp_order.status.value if tp_order and hasattr(tp_order.status, "value") else "unknown") if tp_order else "failed"
                    if tp_status == "rejected":
                        logger.warning("SHORT TAKE PROFIT close REJECTED for %s: %s", pair, tp_order.error_message)
                        self._log_activity(
                            "error", pair,
                            f"SHORT TAKE PROFIT close REJECTED {pair}: {tp_order.error_message or 'unknown'}",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd, "error": tp_order.error_message},
                        )
                    else:
                        logger.info("SHORT TAKE PROFIT triggered for %s (PnL: %.2f%%)", pair, pnl_pct * 100)
                        self._log_activity(
                            "tp", pair,
                            f"SHORT TAKE PROFIT {pair} {pnl_pct * 100:+.1f}% (${pnl_usd:+.2f})",
                            {"pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd},
                        )
                        self._publish(EventTypes.TAKE_PROFIT_HIT, {
                            "pair": pair, "position_id": pos["id"],
                            "pnl_pct": pnl_pct * 100, "pnl_usd": pnl_usd,
                        })
