"""Application settings loaded from environment variables, .env file, and TOML config.

Priority (highest to lowest):
1. Environment variables (CTRADE_ prefix)
2. .env file
3. Hardcoded defaults in Pydantic models
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_DB__")

    url: str = "postgresql+asyncpg://ctrade:ctrade@localhost:5432/ctrade"
    pool_size: int = 10
    echo_sql: bool = False


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_REDIS__")

    url: str = "redis://localhost:6379/0"


class TradingSettings(BaseSettings):
    """Trading execution settings."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_TRADING__")

    mode: Literal["paper", "live"] = "paper"
    default_quote_currency: str = "USDT"
    max_open_positions: int = 5
    max_order_usdt: float = 100.0
    order_timeout_seconds: int = 60


class RiskSettings(BaseSettings):
    """Risk management settings."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_RISK__")

    max_position_pct: float = 0.10
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.15
    default_stop_loss_pct: float = 0.03
    default_take_profit_pct: float = 0.06


class StrategySettings(BaseSettings):
    """Strategy parameter settings."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_STRATEGY__")

    active_strategy: str = "combined"
    technical_weight: float = 0.50
    sentiment_weight: float = 0.30
    onchain_weight: float = 0.20
    entry_confidence_threshold: float = 0.70
    exit_confidence_threshold: float = 0.30
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0


class FeedSettings(BaseSettings):
    """Data feed API keys and polling intervals."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_FEEDS__")

    coinmarketcap_api_key: SecretStr = SecretStr("")
    twitter_bearer_token: SecretStr = SecretStr("")
    reddit_client_id: SecretStr = SecretStr("")
    reddit_client_secret: SecretStr = SecretStr("")
    glassnode_api_key: SecretStr = SecretStr("")
    news_poll_interval_seconds: int = 300
    social_poll_interval_seconds: int = 300
    onchain_poll_interval_seconds: int = 900
    candle_poll_interval_seconds: int = 60


class AuthSettings(BaseSettings):
    """Dashboard authentication settings."""

    model_config = SettingsConfigDict(env_prefix="CTRADE_AUTH__")

    secret_key: SecretStr = SecretStr("change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours
    username: str = "admin"
    password_hash: str = ""


class AppSettings(BaseSettings):
    """Root application settings, composes all sub-settings."""

    model_config = SettingsConfigDict(
        env_prefix="CTRADE_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # App-level
    app_name: str = "cTrade"
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Encryption key for API credential storage
    encryption_key: SecretStr = Field(default=SecretStr(""))

    # Sub-settings
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    feeds: FeedSettings = Field(default_factory=FeedSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get cached application settings singleton."""
    return AppSettings()
