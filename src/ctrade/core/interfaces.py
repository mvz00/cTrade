"""Protocol definitions for all pluggable components.

These protocols define the contracts that exchange adapters, feeds, strategies,
and other components must implement. Using Protocols (structural subtyping)
rather than ABCs allows duck-typing and easier testing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from ctrade.core.enums import OrderSide, OrderType, Timeframe
from ctrade.core.models import (
    Candle,
    MarketState,
    Order,
    Signal,
    Ticker,
)


@runtime_checkable
class ExchangeAdapter(Protocol):
    """Protocol for exchange connectivity (both paper and live)."""

    @property
    def name(self) -> str:
        """Exchange identifier (e.g., 'binance')."""
        ...

    async def fetch_ticker(self, symbol: str) -> Ticker:
        """Fetch current ticker for a symbol."""
        ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 100,
    ) -> list[Candle]:
        """Fetch OHLCV candle data."""
        ...

    async def fetch_balance(self) -> dict[str, Decimal]:
        """Fetch account balances. Returns {currency: available_amount}."""
        ...

    async def create_order(
        self,
        symbol: str,
        order_type: OrderType,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> Order:
        """Place an order on the exchange."""
        ...

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an existing order. Returns True if successfully cancelled."""
        ...

    async def fetch_order(self, order_id: str, symbol: str) -> Order:
        """Fetch the current state of an order."""
        ...

    async def close(self) -> None:
        """Close exchange connection and clean up resources."""
        ...


@runtime_checkable
class BaseFeed(Protocol):
    """Protocol for data feed sources."""

    @property
    def name(self) -> str:
        """Feed identifier."""
        ...

    async def start(self) -> None:
        """Start the feed (begin fetching data)."""
        ...

    async def stop(self) -> None:
        """Stop the feed gracefully."""
        ...

    async def healthcheck(self) -> bool:
        """Check if the feed is operating normally."""
        ...


@runtime_checkable
class BaseStrategy(Protocol):
    """Protocol for trading strategies."""

    @property
    def name(self) -> str:
        """Strategy identifier."""
        ...

    async def evaluate(self, market_state: MarketState) -> list[Signal]:
        """Evaluate market state and generate trading signals."""
        ...


@runtime_checkable
class RiskChecker(Protocol):
    """Protocol for risk management checks."""

    async def validate_order(
        self,
        order: Order,
        portfolio_value: Decimal,
        open_positions: int,
    ) -> tuple[bool, str]:
        """Validate an order against risk rules.

        Returns:
            Tuple of (is_valid, rejection_reason).
            If is_valid is True, rejection_reason is empty.
        """
        ...


@runtime_checkable
class PositionSizer(Protocol):
    """Protocol for position sizing calculation."""

    def calculate_size(
        self,
        portfolio_value: Decimal,
        current_price: Decimal,
        risk_per_trade: float,
        stop_loss_pct: float,
    ) -> Decimal:
        """Calculate the position size (quantity) for a trade."""
        ...


@runtime_checkable
class IndicatorCalculator(Protocol):
    """Protocol for technical indicator computation."""

    def compute(self, df: pd.DataFrame, **params: Any) -> pd.Series:  # type: ignore[type-arg]
        """Compute a technical indicator on OHLCV DataFrame.

        Args:
            df: DataFrame with columns [open, high, low, close, volume].
            **params: Indicator-specific parameters.

        Returns:
            Series with the computed indicator values.
        """
        ...


@runtime_checkable
class NotificationChannel(Protocol):
    """Protocol for notification delivery channels."""

    @property
    def name(self) -> str:
        """Channel identifier."""
        ...

    async def send(self, message: str, severity: str, metadata: dict[str, Any]) -> bool:
        """Send a notification. Returns True if delivered successfully."""
        ...
