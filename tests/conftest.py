"""Shared test fixtures for cTrade tests."""

from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from ctrade.api.app import create_app
from ctrade.core.config_store import RuntimeConfigStore
from ctrade.core.enums import (
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    PositionStatus,
    SignalAction,
    Timeframe,
    TradingMode,
)
from ctrade.core.events import EventBus
from ctrade.core.models import Candle, Order, Position, Signal
from ctrade.settings import AppSettings


@pytest.fixture
def app_settings() -> AppSettings:
    """Provide test application settings."""
    return AppSettings(
        debug=True,
        log_level="DEBUG",
        trading={"mode": "paper"},  # type: ignore[arg-type]
    )


@pytest.fixture
def event_bus() -> EventBus:
    """Provide a fresh event bus for testing."""
    return EventBus()


@pytest.fixture(autouse=True)
def _init_config_store(app_settings):
    """Initialize the runtime config store for every test."""
    RuntimeConfigStore.initialize(app_settings)
    yield
    RuntimeConfigStore.reset()


@pytest.fixture
def app():
    """Provide a FastAPI test application."""
    return create_app()


@pytest.fixture
async def client(app):
    """Provide an async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_candle() -> Candle:
    """Provide a sample candle for testing."""
    return Candle(
        time=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        pair_symbol="BTC/USDT",
        timeframe=Timeframe.H1,
        open=Decimal("67000.00"),
        high=Decimal("67500.00"),
        low=Decimal("66800.00"),
        close=Decimal("67200.00"),
        volume=Decimal("1234.56"),
    )


@pytest.fixture
def sample_signal() -> Signal:
    """Provide a sample trading signal for testing."""
    return Signal(
        id=uuid4(),
        pair_symbol="BTC/USDT",
        action=SignalAction.BUY,
        confidence=0.82,
        technical_score=0.85,
        sentiment_score=0.75,
        onchain_score=0.80,
        contributing_factors={
            "rsi": {"value": 28.5, "signal": "oversold"},
            "macd": {"signal": "bullish_crossover"},
        },
        strategy_name="combined",
    )


@pytest.fixture
def sample_order() -> Order:
    """Provide a sample order for testing."""
    return Order(
        id=uuid4(),
        pair_symbol="BTC/USDT",
        exchange_name="binance",
        trading_mode=TradingMode.PAPER,
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        quantity=Decimal("0.01"),
        status=OrderStatus.PENDING,
    )


@pytest.fixture
def sample_position() -> Position:
    """Provide a sample position for testing."""
    return Position(
        id=uuid4(),
        pair_symbol="BTC/USDT",
        exchange_name="binance",
        trading_mode=TradingMode.PAPER,
        side=PositionSide.LONG,
        status=PositionStatus.OPEN,
        entry_price=Decimal("67200.00"),
        quantity=Decimal("0.01"),
        stop_loss=Decimal("65184.00"),
        take_profit=Decimal("71232.00"),
        strategy_name="combined",
    )
