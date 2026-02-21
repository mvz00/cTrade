"""Exchange management API endpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ctrade.api.deps import get_app_settings
from ctrade.api.schemas.config import (
    AvailableExchangeResponse,
    ExchangeAddRequest,
    ExchangeResponse,
    ExchangeTestResponse,
)
from ctrade.core.config_store import RuntimeConfigStore
from ctrade.exchange.market_data import MarketDataProvider
from ctrade.security.vault import Vault
from ctrade.settings import AppSettings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exchanges", tags=["exchanges"])

# __file__ = src/ctrade/api/routers/exchanges.py → parents[4] = project root
_EXCHANGES_TOML = Path(__file__).resolve().parents[4] / "config" / "exchanges.toml"


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
    )
    # New exchange → refresh available pairs from it
    MarketDataProvider.get_instance().clear_pairs_cache()
    return ExchangeResponse(**result)


@router.delete("/{exchange_id}", status_code=204)
async def delete_exchange(exchange_id: str) -> None:
    """Remove an exchange configuration."""
    store = RuntimeConfigStore.get()
    if not store.remove_exchange(exchange_id):
        raise HTTPException(status_code=404, detail="Exchange not found")
    # Exchange removed → refresh available pairs
    MarketDataProvider.get_instance().clear_pairs_cache()


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
