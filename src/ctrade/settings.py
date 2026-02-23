"""Application settings loaded from environment variables, .env file, and TOML config.

Priority (highest to lowest):
1. Environment variables (CTRADE_ prefix)
2. .env file
3. Hardcoded defaults in Pydantic models

Env var naming: CTRADE_{section}__{field}
  e.g. CTRADE_FEEDS__COINMARKETCAP_API_KEY  →  settings.feeds.coinmarketcap_api_key
       CTRADE_DB__URL                        →  settings.db.url
       CTRADE_AUTH__ENABLED                  →  settings.auth.enabled

Sub-models are plain BaseModel (not BaseSettings) so that only the root
AppSettings reads from the environment via env_nested_delimiter="__".
This avoids conflicts between the parent's nested-delimiter resolution
and each sub-model's independent env loading.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseModel):
    """Database connection settings."""

    url: str = "postgresql+asyncpg://ctrade:ctrade@localhost:5432/ctrade"
    pool_size: int = 10
    echo_sql: bool = False


class RedisSettings(BaseModel):
    """Redis connection settings."""

    url: str = "redis://localhost:6379/0"


class TradingSettings(BaseModel):
    """Trading execution settings."""

    mode: Literal["paper", "live"] = "paper"
    default_quote_currency: str = "USDT"
    max_open_positions: int = 5
    max_order_usdt: float = 100.0
    order_timeout_seconds: int = 60


class RiskSettings(BaseModel):
    """Risk management settings."""

    max_position_pct: float = 0.10
    max_daily_loss_pct: float = 0.05
    max_drawdown_pct: float = 0.15
    default_stop_loss_pct: float = 0.03
    default_take_profit_pct: float = 0.06


class StrategySettings(BaseModel):
    """Strategy parameter settings."""

    active_strategy: str = "combined"
    technical_weight: float = 0.30
    sentiment_weight: float = 0.10
    onchain_weight: float = 0.08
    derivatives_weight: float = 0.17
    market_sentiment_weight: float = 0.17
    cvd_weight: float = 0.10
    social_velocity_weight: float = 0.08
    strategy_mode: str = "long_only"
    short_min_1h_change_pct: float = 2.0
    entry_confidence_threshold: float = 0.55
    exit_confidence_threshold: float = 0.45
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0


class FeedSettings(BaseModel):
    """Data feed API keys and polling intervals."""

    coinmarketcap_api_key: SecretStr = SecretStr("")
    twitter_bearer_token: SecretStr = SecretStr("")
    reddit_client_id: SecretStr = SecretStr("")
    reddit_client_secret: SecretStr = SecretStr("")
    glassnode_api_key: SecretStr = SecretStr("")
    news_poll_interval_seconds: int = 300
    social_poll_interval_seconds: int = 300
    onchain_poll_interval_seconds: int = 900
    candle_poll_interval_seconds: int = 60


class AuthSettings(BaseModel):
    """Dashboard authentication settings."""

    enabled: bool = False  # Set to True in production (CTRADE_AUTH__ENABLED=true)
    secret_key: SecretStr = SecretStr("change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours
    username: str = "admin"
    password_hash: str = ""


class DiscordSettings(BaseModel):
    """Discord webhook notification settings."""

    enabled: bool = False
    webhook_url: SecretStr = SecretStr("")


class TelegramSettings(BaseModel):
    """Telegram bot notification settings."""

    enabled: bool = False
    bot_token: SecretStr = SecretStr("")
    chat_id: str = ""


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

    # Sub-settings (resolved via env_nested_delimiter, e.g. CTRADE_DB__URL)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    trading: TradingSettings = Field(default_factory=TradingSettings)
    risk: RiskSettings = Field(default_factory=RiskSettings)
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    feeds: FeedSettings = Field(default_factory=FeedSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    discord: DiscordSettings = Field(default_factory=DiscordSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Get cached application settings singleton."""
    return AppSettings()
