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

_MAX_ACTIVITY_LOG = 100


def _build_justification(
    pair: str,
    side: str,
    signal: Signal,
    composite: float,
    agreement: str,
) -> str:
    """Build a human-readable justification for a trade from signal data.

    Returns a short summary (max ~500 chars) explaining which intelligence
    sources contributed and their key findings.
    """
    factors = signal.contributing_factors
    fusion = factors.get("fusion", {})
    scores = fusion.get("scores", {})
    _ALL_FEED_KEYS = ("technical", "sentiment", "onchain", "derivatives", "market_sentiment", "cvd", "social_velocity")
    total_configured = len(_ALL_FEED_KEYS)
    active_sources = len(scores)

    # Count directional agreement
    if side == "BUY":
        aligned = sum(1 for s in scores.values() if s > 0.52)
    else:
        aligned = sum(1 for s in scores.values() if s < 0.48)

    parts: list[str] = [f"{side} {pair}:"]

    # Consensus
    if agreement in ("bullish", "bearish"):
        parts.append(f"{agreement.capitalize()} consensus ({aligned}/{active_sources} active, {active_sources}/{total_configured} feeds).")
    else:
        parts.append(f"Mixed signals ({aligned}/{active_sources} active, {active_sources}/{total_configured} feeds).")

    # Technical highlights
    tech_score = scores.get("technical")
    if tech_score is not None:
        tech_details: list[str] = []
        for ind_name in ("rsi", "macd", "bb", "ema_cross"):
            ind = factors.get(ind_name) or {}
            sig = ind.get("signal")
            if sig and sig != "neutral":
                label = ind_name.upper().replace("_", " ")
                tech_details.append(f"{label} {sig}")
        detail_str = f" ({', '.join(tech_details)})" if tech_details else ""
        parts.append(f"Technical {tech_score:.2f}{detail_str}.")

    # Sentiment
    sent_score = scores.get("sentiment")
    if sent_score is not None:
        sent_info = factors.get("sentiment", {})
        sent_signal = sent_info.get("signal", "")
        parts.append(f"Sentiment {sent_score:.2f}{f' ({sent_signal})' if sent_signal else ''}.")

    # Derivatives
    deriv_score = scores.get("derivatives")
    if deriv_score is not None:
        deriv_info = factors.get("derivatives", {})
        deriv_signal = deriv_info.get("signal", "")
        parts.append(f"Derivatives {deriv_score:.2f}{f' ({deriv_signal})' if deriv_signal else ''}.")

    # On-chain
    onchain_score = scores.get("onchain")
    if onchain_score is not None:
        parts.append(f"On-chain {onchain_score:.2f}.")

    # Market sentiment
    mkt_score = scores.get("market_sentiment")
    if mkt_score is not None:
        mkt_info = factors.get("market_sentiment", {})
        fg = mkt_info.get("fear_greed", {})
        mkt_signal = fg.get("signal", "")
        parts.append(f"Mkt sentiment {mkt_score:.2f}{f' ({mkt_signal})' if mkt_signal else ''}.")

    # CVD
    cvd_score = scores.get("cvd")
    if cvd_score is not None:
        cvd_info = factors.get("cvd", {})
        cvd_signal = cvd_info.get("signal", "")
        parts.append(f"CVD {cvd_score:.2f}{f' ({cvd_signal})' if cvd_signal else ''}.")

    # Social velocity
    social_score = scores.get("social_velocity")
    if social_score is not None:
        sv_info = factors.get("social_velocity", {})
        velocity = sv_info.get("velocity_ratio")
        if velocity and velocity > 1.5:
            parts.append(f"Social spike {velocity:.1f}x.")
        else:
            parts.append(f"Social {social_score:.2f}.")

    # Confidence
    confidence_pct = round(signal.confidence * 100)
    parts.append(f"Confidence: {confidence_pct}%.")

    result = " ".join(parts)
    return result[:500] if len(result) > 500 else result


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
        self._sl_history: dict[str, datetime] = {}  # pair → last SL timestamp

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

    def clear_activity_log(self) -> int:
        """Clear all activity log entries. Returns the count cleared."""
        count = len(self._activity_log)
        self._activity_log.clear()
        return count

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
            self._log_activity(
                "info", "ALL",
                "No watched pairs — add pairs on the Trading page to start analysis",
            )
            return

        # Refresh real exchange prices for live-mode PnL display
        from ctrade.exchange.live_engine import LiveEngine

        if isinstance(engine, LiveEngine):
            try:
                await engine.refresh_live_prices()
            except Exception:
                logger.debug("Could not refresh live prices")

        store = None
        try:
            store = RuntimeConfigStore.get()
            strategy = store.get_strategy()
            trading = store.get_trading()
            exchanges = store.list_exchanges()
            # Global risk fallback (used when no per-pair exchange match)
            default_exchange_id = exchanges[0]["id"] if exchanges else None
            risk = store.get_effective_risk(default_exchange_id)
        except RuntimeError:
            strategy = {}
            risk = {}
            trading = {}
            exchanges = []
            default_exchange_id = None

        # ---- Risk appetite → dynamic thresholds + amplification ----
        risk_appetite = strategy.get("risk_appetite", 5)
        half_zone = 0.10 - (risk_appetite - 1) * 0.01  # 0.10 → 0.01
        entry_threshold = 0.50 + half_zone              # 0.60 → 0.51
        exit_threshold = 0.50 - half_zone               # 0.40 → 0.49
        amplification = 1.0 + (risk_appetite - 1) * 0.167  # 1.0 → 2.5

        max_open = trading.get("max_open_positions", 5)
        max_order_usdt = trading.get("max_order_usdt", 100.0)

        # Diagnostic: log effective config so we can verify in the UI
        logger.info("Trading tick config: max_order_usdt=%.2f, max_open=%d", max_order_usdt, max_open)

        # ---- Rank pairs by volatility (biggest movers first) ----
        ranked_pairs = self._rank_pairs_by_momentum(pairs)

        strategy_mode = strategy.get("strategy_mode", "long_only")
        quicktrade_min_1h_change_pct = strategy.get("quicktrade_min_1h_change_pct", 2.0)
        min_hold_minutes = strategy.get("min_hold_minutes", 15)

        processed = 0
        errors = 0
        for pair in ranked_pairs:
            # Route pair to its exchange based on quote currency
            pair_ex = store.find_exchange_for_pair(pair) if store else None
            self._active_exchange_id = (
                pair_ex.id if pair_ex
                else default_exchange_id
            )
            pair_risk = store.get_effective_risk(self._active_exchange_id) if store else risk

            # Per-pair risk values (may differ if exchange has risk overrides)
            p_max_pos = pair_risk.get("max_position_pct", 0.10)
            p_sl = pair_risk.get("default_stop_loss_pct", 0.03)
            p_tp = pair_risk.get("default_take_profit_pct", 0.06)
            p_sl_rebuy = pair_risk.get("sl_rebuy_delay_hours", 1.0)

            try:
                await self._process_pair(
                    pair, engine, market, signal_mgr,
                    entry_threshold, exit_threshold,
                    p_max_pos, max_open,
                    max_order_usdt,
                    p_sl, p_tp,
                    strategy,
                    strategy_mode, quicktrade_min_1h_change_pct,
                    amplification=amplification,
                    min_hold_minutes=min_hold_minutes,
                    sl_rebuy_delay_hours=p_sl_rebuy,
                )
                processed += 1
            except Exception:
                errors += 1
                logger.exception("Error processing pair %s", pair)

        # Log tick summary (replaces the previous summary if one exists
        # to avoid flooding the activity log with meta entries).
        mode_label = "live" if isinstance(engine, LiveEngine) else "paper"
        summary = f"Tick #{self._tick_count + 1} complete — {processed}/{len(ranked_pairs)} pairs analyzed ({mode_label})"
        if errors:
            summary += f", {errors} errors"
        self._log_activity("info", "ALL", summary)

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
        quicktrade_min_1h_change_pct: float = 2.0,
        amplification: float = 1.0,
        min_hold_minutes: int = 15,
        sl_rebuy_delay_hours: float = 1.0,
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

        # 1. Technical score (always available — pure TA indicators)
        tech_score = signal.technical_score or 0.5

        # 2. Screener / momentum score (CoinMarketCap top movers)
        cmc_feed = CoinMarketCapFeed.get_instance()
        momentum_score = cmc_feed.get_momentum_score(pair)

        # 3. Sentiment score (may be None if feed not ready)
        sentiment_feed = SentimentFeed.get_instance()
        sentiment_score = sentiment_feed.get_sentiment_score(pair)

        # 4. On-chain score (may be None if feed not ready)
        onchain_feed = OnChainFeed.get_instance()
        onchain_score = onchain_feed.get_onchain_score(pair)

        # 5. Derivatives score (may be None if feed not ready or exchange unavailable)
        derivatives_feed = DerivativesFeed.get_instance()
        derivatives_score = derivatives_feed.get_derivatives_score(pair)

        # 6. Market sentiment score (F&G index, L/S ratio, liquidation data)
        mkt_sentiment_feed = MarketSentimentFeed.get_instance()
        market_sentiment_score = mkt_sentiment_feed.get_market_sentiment_score(pair)

        # 7. CVD score (cumulative volume delta divergence)
        cvd_feed = CVDFeed.get_instance()
        cvd_score = cvd_feed.get_cvd_score(pair)

        # 8. Social velocity score (mention spike detection)
        social_velocity_feed = SocialVelocityFeed.get_instance()
        social_velocity_score = social_velocity_feed.get_social_velocity_score(pair)

        # ---- Weighted fusion with proportional redistribution ----

        raw_weights = {
            "technical": strategy.get("technical_weight", 0.30),
            "screener": strategy.get("screener_weight", 0.0),
            "sentiment": strategy.get("sentiment_weight", 0.10),
            "onchain": strategy.get("onchain_weight", 0.08),
            "derivatives": strategy.get("derivatives_weight", 0.17),
            "market_sentiment": strategy.get("market_sentiment_weight", 0.17),
            "cvd": strategy.get("cvd_weight", 0.10),
            "social_velocity": strategy.get("social_velocity_weight", 0.08),
        }

        scores: dict[str, float] = {"technical": tech_score}
        if momentum_score is not None:
            scores["screener"] = momentum_score
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

        raw_composite = sum(scores[k] * weights[k] for k in scores)
        # Amplify signal strength based on risk appetite (stretch away from 0.5)
        composite = 0.5 + (raw_composite - 0.5) * amplification
        composite = round(max(0.0, min(1.0, composite)), 4)

        # ---- Multi-timeframe outlook scores ----
        # 1h outlook = composite (already based on 1h candle analysis + 7 sources)
        outlook_1h = composite

        # 24h/7d outlooks blend composite with CMC price change data
        base_symbol = pair.split("/")[0]
        cmc_listing = cmc_feed._listings_by_symbol.get(base_symbol)
        if cmc_listing is not None:
            pct_24h_score = CoinMarketCapFeed._pct_to_score(cmc_listing.pct_change_24h, scale=10.0)
            pct_7d_score = CoinMarketCapFeed._pct_to_score(cmc_listing.pct_change_7d, scale=20.0)
            outlook_24h = round(0.50 * composite + 0.50 * pct_24h_score, 4)
            outlook_7d = round(0.60 * pct_7d_score + 0.40 * composite, 4)
        else:
            outlook_24h = composite
            outlook_7d = composite

        outlook = {"outlook_1h": outlook_1h, "outlook_24h": outlook_24h, "outlook_7d": outlook_7d}

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
            "raw_composite": round(raw_composite, 4),
            "amplification": round(amplification, 3),
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
            confidence=round(composite, 4),
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
                 "composite": composite, "agreement": agreement,
                 **outlook},
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
                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                outlook=outlook, min_hold_minutes=min_hold_minutes,
                sl_rebuy_delay_hours=sl_rebuy_delay_hours,
            )
        elif strategy_mode == "quicktrade":
            await self._execute_quicktrade(
                signal, pair, engine, market, signal_mgr,
                portfolio, open_positions, max_open, max_order_usdt,
                max_position_pct, composite, agreement,
                quicktrade_min_1h_change_pct,
                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                outlook=outlook, min_hold_minutes=min_hold_minutes,
                sl_rebuy_delay_hours=sl_rebuy_delay_hours,
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
        stop_loss_pct: float = 0.03,
        take_profit_pct: float = 0.06,
        outlook: dict[str, float] | None = None,
    ) -> None:
        """Open a new position (long or short) with standard position sizing."""
        total_value = portfolio["total_value_usd"]

        # Apply per-exchange max portfolio allocation cap
        active_ex_id = getattr(self, "_active_exchange_id", None)
        if active_ex_id:
            try:
                entry = RuntimeConfigStore.get().get_exchange_entry(active_ex_id)
                if entry and entry.max_portfolio_pct < 1.0:
                    total_value = total_value * entry.max_portfolio_pct
            except RuntimeError:
                pass

        # total_value is in USD but max_order_usdt and price are in the
        # pair's quote currency (e.g. AUD for BTC/AUD).  Convert portfolio
        # value to quote currency so both sides of the min() are comparable.
        quote = pair.split("/")[-1] if "/" in pair else "USDT"
        if quote not in ("USD", "USDT"):
            from ctrade.exchange.market_data import _FIAT_TO_USD
            usd_rate = _FIAT_TO_USD.get(quote, 1.0)
            if usd_rate > 0:
                total_value = total_value / usd_rate  # USD → quote currency

        # max_order_usdt is the user's explicit per-trade budget (e.g. $10).
        # Honour it directly — it already acts as the hard cap.
        # Only fall back to the portfolio-% limit when no explicit amount is set
        # (i.e. when using the large default of 100).
        position_budget = max_order_usdt

        # Get REAL exchange price — not simulated.
        # get_ticker() falls back to fake simulated prices when ccxt fails
        # (which it always does for CoinSpot AUD pairs), so we must use
        # the CoinSpot native API directly for AUD pairs.
        ticker = None
        if pair.endswith("/AUD"):
            ticker = await MarketDataProvider._fetch_coinspot_price_native(pair)
        if ticker is None:
            ticker = await market.get_ticker(pair)
        price = float(ticker.last_price)
        if price <= 0:
            return

        quantity = position_budget / price
        logger.info(
            "Position sizing %s: budget=%.2f, price=%.4f, qty=%.6f (investment=%.2f)",
            pair, position_budget, price, quantity, quantity * price,
        )

        # Compute absolute SL/TP price levels
        if side == "buy":
            sl_price = price * (1 - stop_loss_pct)
            tp_price = price * (1 + take_profit_pct)
        else:  # short
            sl_price = price * (1 + stop_loss_pct)
            tp_price = price * (1 - take_profit_pct)

        strategy_label = signal.strategy_name or "technical"
        momentum_tag = ""
        if cmc_info:
            pct_1h = cmc_info.get("pct_change_1h", 0)
            momentum_tag = f" [1h: {pct_1h:+.1f}%]"

        side_label = "BUY" if side == "buy" else "SHORT"
        log_type = "buy" if side == "buy" else "sell"

        # Resolve exchange name for position tracking
        exchange_name = "paper"
        active_ex_id = getattr(self, "_active_exchange_id", None)
        if active_ex_id:
            try:
                ex_entry = RuntimeConfigStore.get().get_exchange_entry(active_ex_id)
                if ex_entry:
                    exchange_name = ex_entry.name
            except RuntimeError:
                pass

        if quantity > 0:
            justification = _build_justification(
                pair=pair, side=side_label, signal=signal,
                composite=composite, agreement=agreement,
            )
            order = await engine.place_order(
                symbol=pair,
                side=side,
                order_type="market",
                quantity=quantity,
                price=price,
                signal_id=str(signal.id),
                strategy_name=strategy_label,
                justification=justification,
                stop_loss=sl_price,
                take_profit=tp_price,
                exchange_name=exchange_name,
                exchange_id=active_ex_id,
                outlook=outlook,
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
                    f"AUTO {side_label} {pair} {quantity:.6f} @ ${price:,.2f} (budget=${position_budget:.2f}){momentum_tag} → {order_status}",
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

    def _is_within_cooldown(
        self, positions: list[dict], pair: str, side: str, min_hold_minutes: int,
    ) -> bool:
        """Return True if any open position for pair+side is younger than min_hold_minutes."""
        if min_hold_minutes <= 0:
            return False
        now = datetime.now(timezone.utc)
        for pos in positions:
            if pos["pair_symbol"] == pair and pos["side"] == side:
                opened_str = pos.get("opened_at")
                if opened_str:
                    opened_at = datetime.fromisoformat(opened_str)
                    if (now - opened_at).total_seconds() / 60 < min_hold_minutes:
                        return True
        return False

    def _is_sl_rebuy_blocked(self, pair: str, sl_rebuy_delay_hours: float) -> bool:
        """True if pair was recently stopped-out and still within rebuy delay."""
        if sl_rebuy_delay_hours <= 0:
            return False
        last_sl = self._sl_history.get(pair)
        if last_sl is None:
            return False
        elapsed = (datetime.now(timezone.utc) - last_sl).total_seconds() / 3600
        return elapsed < sl_rebuy_delay_hours

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
        stop_loss_pct: float = 0.03, take_profit_pct: float = 0.06,
        outlook: dict[str, float] | None = None,
        min_hold_minutes: int = 15,
        sl_rebuy_delay_hours: float = 1.0,
    ) -> None:
        """Long-only mode: BUY opens long, SELL closes long."""
        cmc_info = CoinMarketCapFeed.get_instance().get_volatility_info(pair)

        if signal.action == SignalAction.BUY:
            if open_positions >= max_open:
                return
            existing = engine.get_positions(status="open")
            if any(p["pair_symbol"] == pair and p["side"] == "long" for p in existing):
                return
            if self._is_sl_rebuy_blocked(pair, sl_rebuy_delay_hours):
                self._log_activity("signal", pair,
                    f"BUY BLOCKED {pair}: re-buy delay active ({sl_rebuy_delay_hours}h after SL)",
                    {"action": "REBUY_BLOCKED", "composite": composite})
                return
            await self._open_position(
                pair, "buy", engine, market, signal, portfolio,
                max_order_usdt, max_position_pct, composite, agreement, cmc_info,
                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                outlook=outlook,
            )

        elif signal.action == SignalAction.SELL:
            positions = engine.get_positions(status="open")
            if self._is_within_cooldown(positions, pair, "long", min_hold_minutes):
                logger.info("HOLD (cooldown) %s: SELL suppressed — position < %d min old", pair, min_hold_minutes)
                self._log_activity(
                    "signal", pair,
                    f"HOLD (cooldown) {pair}: SELL suppressed — position < {min_hold_minutes}min old",
                    {"action": "SELL_SUPPRESSED", "composite": composite,
                     "agreement": agreement, "min_hold_minutes": min_hold_minutes},
                )
                return
            await self._close_positions(pair, "long", engine, composite, agreement)

    async def _execute_quicktrade(
        self, signal: Signal, pair: str, engine: Any, market: MarketDataProvider,
        signal_mgr: SignalManager, portfolio: dict, open_positions: int,
        max_open: int, max_order_usdt: float, max_position_pct: float,
        composite: float, agreement: str, quicktrade_min_1h_change_pct: float,
        stop_loss_pct: float = 0.03, take_profit_pct: float = 0.06,
        outlook: dict[str, float] | None = None,
        min_hold_minutes: int = 15,
        sl_rebuy_delay_hours: float = 1.0,
    ) -> None:
        """Quicktrade mode: BUY opens long only when momentum is high, SELL closes long.

        Like long_only but with an additional momentum filter on entry: the
        pair's 1-hour price change must exceed the quicktrade threshold before
        a BUY is executed.  Targets currencies expected to make big gains in a
        short time window.

        When CMC data is unavailable the momentum filter is bypassed and the
        pair is treated like a normal long_only buy so trading is not blocked.
        """
        cmc_info = CoinMarketCapFeed.get_instance().get_volatility_info(pair)

        if signal.action == SignalAction.BUY:
            # Momentum filter: only buy high-momentum pairs (skip if CMC data
            # is available but momentum is below threshold).  When CMC data is
            # unavailable (cmc_info is None) we fall through to allow the buy.
            if cmc_info is not None and abs(cmc_info.get("pct_change_1h", 0)) < quicktrade_min_1h_change_pct:
                pct = cmc_info["pct_change_1h"]
                self._log_activity(
                    "signal", pair,
                    f"QUICKTRADE skip {pair}: 1h change {pct}% < {quicktrade_min_1h_change_pct}% threshold",
                    {"pair": pair, "pct_change_1h": pct, "threshold": quicktrade_min_1h_change_pct,
                     **(outlook or {})},
                )
                return

            if open_positions >= max_open:
                return
            existing = engine.get_positions(status="open")
            if any(p["pair_symbol"] == pair and p["side"] == "long" for p in existing):
                return
            if self._is_sl_rebuy_blocked(pair, sl_rebuy_delay_hours):
                self._log_activity("signal", pair,
                    f"BUY BLOCKED {pair}: re-buy delay active ({sl_rebuy_delay_hours}h after SL)",
                    {"action": "REBUY_BLOCKED", "composite": composite})
                return
            await self._open_position(
                pair, "buy", engine, market, signal, portfolio,
                max_order_usdt, max_position_pct, composite, agreement, cmc_info,
                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
                outlook=outlook,
            )

        elif signal.action == SignalAction.SELL:
            positions = engine.get_positions(status="open")
            if self._is_within_cooldown(positions, pair, "long", min_hold_minutes):
                logger.info("HOLD (cooldown) %s: SELL suppressed — position < %d min old", pair, min_hold_minutes)
                self._log_activity(
                    "signal", pair,
                    f"HOLD (cooldown) {pair}: SELL suppressed — position < {min_hold_minutes}min old",
                    {"action": "SELL_SUPPRESSED", "composite": composite,
                     "agreement": agreement, "min_hold_minutes": min_hold_minutes},
                )
                return
            await self._close_positions(pair, "long", engine, composite, agreement)

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
                        self._sl_history[pair] = datetime.now(timezone.utc)
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
                        self._sl_history[pair] = datetime.now(timezone.utc)

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
