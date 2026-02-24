"""Exchange management API endpoints."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ctrade.api.deps import get_app_settings
from ctrade.api.schemas.config import (
    AvailableExchangeResponse,
    ExchangeAddRequest,
    ExchangeResponse,
    ExchangeTestResponse,
    ExchangeUpdateRequest,
)
from ctrade.core.config_store import RuntimeConfigStore
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.security.vault import Vault
from ctrade.settings import AppSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exchanges", tags=["exchanges"])

# In Docker (non-editable install), __file__ is in site-packages so the
# parents[4] trick won't reach /app.  Use CTRADE_CONFIG_DIR when set
# (Dockerfile sets it to /app/config).
_config_env = os.environ.get("CTRADE_CONFIG_DIR")
_CONFIG_DIR = Path(_config_env) if _config_env else Path(__file__).resolve().parents[4] / "config"
_EXCHANGES_TOML = _CONFIG_DIR / "exchanges.toml"


def _load_available_exchanges() -> dict[str, dict]:
    """Load exchange templates from config/exchanges.toml."""
    import tomllib

    if not _EXCHANGES_TOML.exists():
        return {}
    with open(_EXCHANGES_TOML, "rb") as f:
        return tomllib.load(f)


def _get_vault(settings: AppSettings) -> Vault:
    """Create a Vault from the encryption key."""
    key = settings.encryption_key.get_secret_value()
    if not key:
        raise HTTPException(
            status_code=500,
            detail=(
                "No encryption key configured. "
                "Set CTRADE_ENCRYPTION_KEY env var. "
                "Generate one with: python -c "
                "\"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ),
        )
    return Vault(key)


@router.get("/available", response_model=list[AvailableExchangeResponse])
async def list_available_exchanges() -> list[AvailableExchangeResponse]:
    """List exchange templates from config/exchanges.toml."""
    exchanges = _load_available_exchanges()
    return [
        AvailableExchangeResponse(
            name=name,
            exchange_type=data.get("exchange_type", "spot"),
            default_fee_pct=data.get("default_fee_pct", 0.10),
            supports_websocket=data.get("supports_websocket", False),
        )
        for name, data in exchanges.items()
    ]


@router.get("/", response_model=list[ExchangeResponse])
async def list_exchanges() -> list[ExchangeResponse]:
    """List configured exchanges (credentials are never returned)."""
    store = RuntimeConfigStore.get()
    return [ExchangeResponse(**ex) for ex in store.list_exchanges()]


@router.post("/", response_model=ExchangeResponse, status_code=201)
async def add_exchange(
    body: ExchangeAddRequest,
    settings: AppSettings = Depends(get_app_settings),
) -> ExchangeResponse:
    """Add an exchange with encrypted API credentials."""
    vault = _get_vault(settings)

    available = _load_available_exchanges()
    if body.name.lower() not in available:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown exchange '{body.name}'. Available: {list(available.keys())}",
        )

    template = available[body.name.lower()]
    store = RuntimeConfigStore.get()
    result = store.add_exchange(
        name=body.name.lower(),
        exchange_type=template.get("exchange_type", "spot"),
        api_key=body.api_key,
        api_secret=body.api_secret,
        vault=vault,
        passphrase=body.passphrase,
        quote_currencies=body.quote_currencies,
        max_portfolio_pct=body.max_portfolio_pct or 1.0,
        risk_overrides=body.risk_overrides,
    )
    # New exchange → refresh available pairs from it
    MarketDataProvider.get_instance().clear_pairs_cache()
    return ExchangeResponse(**result)


@router.patch("/{exchange_id}/toggle", response_model=ExchangeResponse)
async def toggle_exchange(exchange_id: str) -> ExchangeResponse:
    """Toggle an exchange between active and inactive."""
    store = RuntimeConfigStore.get()
    result = store.toggle_exchange(exchange_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Exchange not found")
    # Active status change affects available pairs, prices, and portfolio
    market = MarketDataProvider.get_instance()
    market.clear_pairs_cache()
    market.clear_ticker_cache()
    return ExchangeResponse(**result)


@router.delete("/{exchange_id}", status_code=204)
async def delete_exchange(exchange_id: str) -> None:
    """Remove an exchange configuration."""
    store = RuntimeConfigStore.get()
    if not store.remove_exchange(exchange_id):
        raise HTTPException(status_code=404, detail="Exchange not found")
    # Exchange removed → refresh available pairs
    MarketDataProvider.get_instance().clear_pairs_cache()


@router.put("/{exchange_id}", response_model=ExchangeResponse)
async def update_exchange(
    exchange_id: str,
    body: ExchangeUpdateRequest,
    settings: AppSettings = Depends(get_app_settings),
) -> ExchangeResponse:
    """Update credentials and settings for an existing exchange.

    Only non-empty fields are re-encrypted/updated.
    """
    has_creds = body.api_key or body.api_secret or body.passphrase is not None
    has_settings = (
        body.quote_currencies is not None
        or body.max_portfolio_pct is not None
        or body.risk_overrides is not None
    )
    if not has_creds and not has_settings:
        raise HTTPException(
            status_code=422, detail="No fields provided to update"
        )

    vault = _get_vault(settings)
    store = RuntimeConfigStore.get()
    result = store.update_exchange(
        exchange_id,
        vault,
        api_key=body.api_key,
        api_secret=body.api_secret,
        passphrase=body.passphrase,
        quote_currencies=body.quote_currencies,
        max_portfolio_pct=body.max_portfolio_pct,
        risk_overrides=body.risk_overrides,
    )
    # Quote currency change may affect available pairs
    if body.quote_currencies is not None:
        MarketDataProvider.get_instance().clear_pairs_cache()
    if result is None:
        raise HTTPException(status_code=404, detail="Exchange not found")
    return ExchangeResponse(**result)


@router.post("/{exchange_id}/test", response_model=ExchangeTestResponse)
async def test_exchange(
    exchange_id: str,
    settings: AppSettings = Depends(get_app_settings),
) -> ExchangeTestResponse:
    """Test exchange connectivity by fetching markets via ccxt."""
    store = RuntimeConfigStore.get()
    entry = store.get_exchange_entry(exchange_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Exchange not found")

    vault = _get_vault(settings)
    api_key = vault.decrypt(entry.api_key_encrypted)
    api_secret = vault.decrypt(entry.api_secret_encrypted)
    passphrase = (
        vault.decrypt(entry.passphrase_encrypted) if entry.passphrase_encrypted else None
    )

    try:
        import ccxt.async_support as ccxt_async

        exchange_class = getattr(ccxt_async, entry.name, None)
        if exchange_class is None:
            return ExchangeTestResponse(
                success=False,
                message=f"ccxt does not support exchange '{entry.name}'",
            )

        config: dict = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
        }
        if passphrase:
            config["password"] = passphrase

        exchange = exchange_class(config)
        try:
            await exchange.load_markets()
            return ExchangeTestResponse(
                success=True,
                message=f"Connected to {entry.name} — {len(exchange.symbols)} markets available",
            )
        finally:
            await exchange.close()

    except ImportError:
        return ExchangeTestResponse(
            success=False,
            message="ccxt not installed. Run: pip install ccxt",
        )
    except Exception as e:
        return ExchangeTestResponse(
            success=False,
            message=f"Connection failed: {e}",
        )
