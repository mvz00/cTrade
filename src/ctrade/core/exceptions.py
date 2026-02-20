"""Custom exception hierarchy for cTrade."""


class CTradeError(Exception):
    """Base exception for all cTrade errors."""


# Exchange errors
class ExchangeError(CTradeError):
    """Base exception for exchange-related errors."""


class ExchangeConnectionError(ExchangeError):
    """Failed to connect to exchange."""


class ExchangeRateLimitError(ExchangeError):
    """Exchange rate limit exceeded."""


class InsufficientBalanceError(ExchangeError):
    """Insufficient balance to execute order."""


class OrderNotFoundError(ExchangeError):
    """Order not found on exchange."""


# Risk errors
class RiskError(CTradeError):
    """Base exception for risk management errors."""


class RiskLimitExceededError(RiskError):
    """Trade rejected by risk management."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Risk limit exceeded: {reason}")


class CircuitBreakerTriggeredError(RiskError):
    """Trading halted by circuit breaker."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Circuit breaker triggered: {reason}")


# Feed errors
class FeedError(CTradeError):
    """Base exception for data feed errors."""


class FeedConnectionError(FeedError):
    """Failed to connect to data feed."""


class FeedParseError(FeedError):
    """Failed to parse feed data."""


# Strategy errors
class StrategyError(CTradeError):
    """Base exception for strategy errors."""


class StrategyNotFoundError(StrategyError):
    """Requested strategy not found in registry."""


# Configuration errors
class ConfigurationError(CTradeError):
    """Invalid configuration."""


# Database errors
class DatabaseError(CTradeError):
    """Database operation error."""


# Security errors
class SecurityError(CTradeError):
    """Security-related error."""


class EncryptionError(SecurityError):
    """Encryption/decryption failure."""


class AuthenticationError(SecurityError):
    """Authentication failure."""
