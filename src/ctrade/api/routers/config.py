"""Configuration API endpoints — read and update runtime config."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ctrade.api.schemas.config import (
    RiskConfigResponse,
    RiskConfigUpdate,
    StrategyConfigResponse,
    StrategyConfigUpdate,
    TradingModeResponse,
    TradingModeUpdate,
)
from ctrade.core.config_store import RuntimeConfigStore

router = APIRouter(prefix="/config", tags=["config"])


def _store() -> RuntimeConfigStore:
    return RuntimeConfigStore.get()


# ---- Trading Mode ----

@router.get("/trading-mode", response_model=TradingModeResponse)
async def get_trading_mode() -> TradingModeResponse:
    """Get current trading mode (paper/live)."""
    return TradingModeResponse(**_store().get_trading())


@router.put("/trading-mode", response_model=TradingModeResponse)
async def update_trading_mode(body: TradingModeUpdate) -> TradingModeResponse:
    """Update trading mode.

    Switching to live mode requires at least one configured exchange
    and a valid encryption key.
    """
    updates = body.model_dump(exclude_none=True)

    # Validate prerequisites when switching to live mode
    if updates.get("mode") == "live":
        store = _store()
        exchanges = store.list_exchanges()
        if not exchanges:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot switch to live mode: no exchange configured. "
                    "Add an exchange first via Settings > Exchanges."
                ),
            )

        # Verify encryption key is available (needed to decrypt API credentials)
        try:
            from ctrade.settings import get_settings

            settings = get_settings()
            key = settings.encryption_key.get_secret_value()
            if not key:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Cannot switch to live mode: no encryption key configured. "
                        "Set CTRADE_ENCRYPTION_KEY env var."
                    ),
                )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                status_code=422,
                detail="Cannot switch to live mode: failed to verify encryption key.",
            )

    updated = _store().update_trading(updates)
    return TradingModeResponse(**updated)


# ---- Strategy ----

@router.get("/strategy", response_model=StrategyConfigResponse)
async def get_strategy_config() -> StrategyConfigResponse:
    """Get current strategy configuration."""
    return StrategyConfigResponse(**_store().get_strategy())


@router.put("/strategy", response_model=StrategyConfigResponse)
async def update_strategy_config(body: StrategyConfigUpdate) -> StrategyConfigResponse:
    """Update strategy configuration. Weights must sum to 1.0."""
    try:
        updated = _store().update_strategy(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return StrategyConfigResponse(**updated)


# ---- Risk ----

@router.get("/risk", response_model=RiskConfigResponse)
async def get_risk_config() -> RiskConfigResponse:
    """Get current risk management configuration."""
    return RiskConfigResponse(**_store().get_risk())


@router.put("/risk", response_model=RiskConfigResponse)
async def update_risk_config(body: RiskConfigUpdate) -> RiskConfigResponse:
    """Update risk management parameters."""
    updated = _store().update_risk(body.model_dump(exclude_none=True))
    return RiskConfigResponse(**updated)
