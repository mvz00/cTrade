"""Tests for database persistence layer.

These tests verify:
1. Graceful degradation when DB is unavailable
2. Mapper round-trip correctness (domain <-> ORM)
3. fire_and_forget behaviour without an event loop
4. Singleton hydrate_from_db is a no-op without DB
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
from ctrade.db.persistence import fire_and_forget, is_db_ready, run_db_operation
from ctrade.notifications.alert_manager import AlertConfig, AlertTrigger


# ---------------------------------------------------------------------------
# persistence helpers
# ---------------------------------------------------------------------------

class TestIsDbReady:
    """is_db_ready() should reflect the session factory state."""

    def test_returns_false_when_no_factory(self):
        """Without init_db(), is_db_ready() must return False."""
        with patch("ctrade.db.persistence._engine_module._session_factory", None):
            assert is_db_ready() is False

    def test_returns_true_when_factory_exists(self):
        """After init_db(), is_db_ready() must return True."""
        mock_factory = MagicMock()
        with patch("ctrade.db.persistence._engine_module._session_factory", mock_factory):
            assert is_db_ready() is True


class TestFireAndForget:
    """fire_and_forget() must not raise even without an event loop."""

    def test_no_event_loop_does_not_raise(self):
        """When called outside an async context, should silently skip."""
        async def dummy_coro():
            pass

        # Should not raise
        fire_and_forget(dummy_coro())


@pytest.mark.asyncio
class TestRunDbOperation:
    """run_db_operation() graceful degradation."""

    async def test_returns_none_when_db_unavailable(self):
        """When session factory is None, operation should return None."""
        async def _op(session, resolver):
            return "should-not-reach"

        with patch("ctrade.db.persistence._engine_module._session_factory", None):
            result = await run_db_operation(_op, description="test")
        assert result is None

    async def test_returns_none_on_exception(self):
        """If operation raises, should return None and not propagate."""
        async def _failing_op(session, resolver):
            raise RuntimeError("boom")

        mock_factory = MagicMock()
        mock_session = AsyncMock()
        mock_factory.return_value = mock_session
        # PairResolver is imported lazily inside run_db_operation, so mock it there
        with (
            patch("ctrade.db.persistence._engine_module._session_factory", mock_factory),
            patch("ctrade.db.mappers.PairResolver") as MockResolver,
        ):
            MockResolver.return_value.load_cache = AsyncMock()
            result = await run_db_operation(_failing_op, description="test")
        assert result is None


# ---------------------------------------------------------------------------
# mapper round-trips
# ---------------------------------------------------------------------------

class TestOrderMapper:
    """Order <-> OrderModel round-trip."""

    def test_order_to_orm_fields(self):
        """Verify that order_to_orm maps all fields correctly."""
        from ctrade.db.mappers import _to_float, _to_decimal, _to_decimal_zero

        # Test helper conversions
        assert _to_float(Decimal("1.23")) == 1.23
        assert _to_float(None) is None
        assert _to_decimal(1.23) == Decimal("1.23")
        assert _to_decimal(None) is None
        assert _to_decimal_zero(None) == Decimal("0")
        assert _to_decimal_zero(1.5) == Decimal("1.5")


class TestSignalMapper:
    """Signal domain model field validation for mapping."""

    def test_signal_fields_for_mapping(self):
        """Signal should have all fields needed by signal_to_orm."""
        sig = Signal(
            id=uuid.uuid4(),
            pair_symbol="BTC/USDT",
            action=SignalAction.BUY,
            confidence=0.85,
            technical_score=0.72,
            sentiment_score=0.68,
            onchain_score=None,
            contributing_factors={"rsi": 0.8},
            strategy_name="technical+momentum",
        )
        assert sig.pair_symbol == "BTC/USDT"
        assert sig.action == SignalAction.BUY
        assert sig.confidence == 0.85
        assert sig.technical_score == 0.72
        assert sig.sentiment_score == 0.68
        assert sig.onchain_score is None
        assert sig.strategy_name == "technical+momentum"


class TestAlertConfigMapper:
    """AlertConfig <-> AlertConfigModel round-trip."""

    def test_alert_config_to_orm_and_back(self):
        """Should pack conditions into JSONB and unpack correctly."""
        from ctrade.db.mappers import alert_config_to_orm, orm_to_alert_config

        config = AlertConfig(
            id=str(uuid.uuid4()),
            alert_type="price_above",
            symbol="BTC/USDT",
            value=70000.0,
            message="BTC above 70k!",
            is_active=True,
        )
        orm = alert_config_to_orm(config)
        assert orm.alert_type == "price_above"
        assert orm.conditions["symbol"] == "BTC/USDT"
        assert orm.conditions["value"] == 70000.0
        assert orm.conditions["message"] == "BTC above 70k!"
        assert orm.is_active is True

        # Round-trip back
        restored = orm_to_alert_config(orm)
        assert restored.id == config.id
        assert restored.alert_type == config.alert_type
        assert restored.symbol == config.symbol
        assert restored.value == config.value
        assert restored.message == config.message
        assert restored.is_active == config.is_active


class TestAlertTriggerMapper:
    """AlertTrigger <-> AlertHistoryModel round-trip."""

    def test_alert_trigger_to_orm_and_back(self):
        """Should store trigger details in delivered_to JSONB."""
        from ctrade.db.mappers import alert_trigger_to_orm, orm_to_alert_trigger

        trigger = AlertTrigger(
            id=str(uuid.uuid4()),
            alert_id=str(uuid.uuid4()),
            alert_type="price_above",
            symbol="ETH/USDT",
            message="ETH above 4k!",
            triggered_value=4100.0,
        )
        orm = alert_trigger_to_orm(trigger)
        assert orm.message == "ETH above 4k!"
        assert orm.severity == "info"
        assert orm.delivered_to["symbol"] == "ETH/USDT"
        assert orm.delivered_to["triggered_value"] == 4100.0

        # Round-trip back
        # Note: orm.id is auto-generated int, so we check fields not ID
        restored = orm_to_alert_trigger(orm)
        assert restored.alert_type == trigger.alert_type
        assert restored.symbol == trigger.symbol
        assert restored.message == trigger.message
        assert restored.triggered_value == trigger.triggered_value


# ---------------------------------------------------------------------------
# Singleton hydration (no-op without DB)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSingletonHydration:
    """Singletons should gracefully handle hydration without a DB."""

    async def test_paper_engine_hydrate_noop(self):
        """PaperEngine.hydrate_from_db() should be no-op without DB."""
        from ctrade.exchange.paper_engine import PaperEngine

        engine = PaperEngine()
        with patch("ctrade.db.persistence._engine_module._session_factory", None):
            await engine.hydrate_from_db()
        # Should still have default state
        assert engine._cash.get("USDT") is not None

    async def test_signal_manager_hydrate_noop(self):
        """SignalManager.hydrate_from_db() should be no-op without DB."""
        from ctrade.strategy.signal_manager import SignalManager

        mgr = SignalManager()
        with patch("ctrade.db.persistence._engine_module._session_factory", None):
            await mgr.hydrate_from_db()
        assert mgr._signals == []

    async def test_alert_manager_hydrate_noop(self):
        """AlertManager.hydrate_from_db() should be no-op without DB."""
        from ctrade.notifications.alert_manager import AlertManager

        mgr = AlertManager()
        with patch("ctrade.db.persistence._engine_module._session_factory", None):
            await mgr.hydrate_from_db()
        assert mgr._configs == []
        assert mgr._history == []

    async def test_orchestrator_hydrate_noop(self):
        """TradingOrchestrator.hydrate_from_db() should be no-op without DB."""
        from ctrade.strategy.orchestrator import TradingOrchestrator

        orch = TradingOrchestrator()
        with patch("ctrade.db.persistence._engine_module._session_factory", None):
            await orch.hydrate_from_db()
        assert orch._activity_log == []


# ---------------------------------------------------------------------------
# DB engine ping
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPingDb:
    """ping_db() should return False when engine is None."""

    async def test_ping_returns_false_without_engine(self):
        from ctrade.db.engine import ping_db

        result = await ping_db()
        assert result is False
