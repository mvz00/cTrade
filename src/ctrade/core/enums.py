"""Core enumerations used throughout the cTrade application."""

from enum import StrEnum


class TradingMode(StrEnum):
    """Trading execution mode."""

    PAPER = "paper"
    LIVE = "live"


class OrderSide(StrEnum):
    """Order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Order execution type."""

    MARKET = "market"
    LIMIT = "limit"
    STOP_LIMIT = "stop_limit"


class OrderStatus(StrEnum):
    """Order lifecycle status."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class PositionSide(StrEnum):
    """Position direction."""

    LONG = "long"
    SHORT = "short"


class PositionStatus(StrEnum):
    """Position lifecycle status."""

    OPEN = "open"
    CLOSED = "closed"


class SignalAction(StrEnum):
    """Trading signal action recommendation."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class StrategyMode(StrEnum):
    """Strategy position mode — controls which sides the orchestrator trades."""

    LONG_ONLY = "long_only"
    SHORT_ONLY = "short_only"
    BOTH = "both"


class Timeframe(StrEnum):
    """Candlestick timeframe intervals."""

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class FeedStatus(StrEnum):
    """Data feed health status."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    DOWN = "down"
    STOPPED = "stopped"


class AlertSeverity(StrEnum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SentimentLabel(StrEnum):
    """Sentiment classification labels."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
