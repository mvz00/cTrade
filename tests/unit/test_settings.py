"""Tests for application settings."""

from ctrade.settings import AppSettings


def test_default_settings():
    """Default settings should load without errors."""
    settings = AppSettings()
    assert settings.app_name == "cTrade"
    assert settings.trading.mode == "paper"
    assert settings.risk.max_position_pct == 0.10
    assert settings.strategy.technical_weight == 0.35
    assert settings.strategy.derivatives_weight == 0.20
    assert settings.strategy.market_sentiment_weight == 0.20
    assert settings.api_port == 8000


def test_strategy_weights_sum():
    """Strategy weights should sum to approximately 1.0."""
    settings = AppSettings()
    total = (
        settings.strategy.technical_weight
        + settings.strategy.sentiment_weight
        + settings.strategy.onchain_weight
        + settings.strategy.derivatives_weight
        + settings.strategy.market_sentiment_weight
    )
    assert abs(total - 1.0) < 0.01


def test_risk_settings_ranges():
    """Risk settings should be within valid ranges."""
    settings = AppSettings()
    assert 0 < settings.risk.max_position_pct <= 1.0
    assert 0 < settings.risk.max_daily_loss_pct <= 1.0
    assert 0 < settings.risk.default_stop_loss_pct <= 1.0
    assert 0 < settings.risk.default_take_profit_pct <= 1.0
