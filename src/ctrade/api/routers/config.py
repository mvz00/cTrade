"""Configuration API endpoints — read and update runtime config."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ctrade.api.schemas.config import (
    EmailConfigResponse,
    EmailConfigUpdate,
    RiskConfigResponse,
    RiskConfigUpdate,
    StrategyConfigResponse,
    StrategyConfigUpdate,
    TradingModeResponse,
    TradingModeUpdate,
)
from ctrade.core.config_store import RuntimeConfigStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/config", tags=["config"])


async def _store() -> RuntimeConfigStore:
    if not RuntimeConfigStore.is_initialized():
        try:
            from ctrade.settings import get_settings

            RuntimeConfigStore.initialize(get_settings())
        except Exception:
            raise HTTPException(
                status_code=503,
                detail="Configuration store not available. Server is still starting up.",
            )
    store = RuntimeConfigStore.get()
    await store.ensure_hydrated()
    return store


# ---- Trading Mode ----

@router.get("/trading-mode", response_model=TradingModeResponse)
async def get_trading_mode() -> TradingModeResponse:
    """Get current trading mode (paper/live)."""
    return TradingModeResponse(**(await _store()).get_trading())


@router.put("/trading-mode", response_model=TradingModeResponse)
async def update_trading_mode(body: TradingModeUpdate) -> TradingModeResponse:
    """Update trading mode.

    Switching to live mode requires at least one configured exchange
    and a valid encryption key.
    """
    updates = body.model_dump(exclude_none=True)

    # Validate prerequisites when switching to live mode
    if updates.get("mode") == "live":
        store = await _store()
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

    updated = (await _store()).update_trading(updates)
    return TradingModeResponse(**updated)


# ---- Strategy ----

@router.get("/strategy", response_model=StrategyConfigResponse)
async def get_strategy_config() -> StrategyConfigResponse:
    """Get current strategy configuration."""
    return StrategyConfigResponse(**(await _store()).get_strategy())


@router.put("/strategy", response_model=StrategyConfigResponse)
async def update_strategy_config(body: StrategyConfigUpdate) -> StrategyConfigResponse:
    """Update strategy configuration. Weights must sum to 1.0."""
    try:
        updated = (await _store()).update_strategy(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return StrategyConfigResponse(**updated)


# ---- Risk ----

@router.get("/risk", response_model=RiskConfigResponse)
async def get_risk_config() -> RiskConfigResponse:
    """Get current risk management configuration."""
    return RiskConfigResponse(**(await _store()).get_risk())


@router.put("/risk", response_model=RiskConfigResponse)
async def update_risk_config(body: RiskConfigUpdate) -> RiskConfigResponse:
    """Update risk management parameters."""
    updated = (await _store()).update_risk(body.model_dump(exclude_none=True))
    return RiskConfigResponse(**updated)


# ---- Email Notifications ----

@router.get("/email", response_model=EmailConfigResponse)
async def get_email_config() -> EmailConfigResponse:
    """Get email notification settings (API key masked)."""
    config = (await _store()).get_email()
    # Mask API key — never expose the encrypted blob to the frontend
    has_key = bool(config.get("api_key_encrypted"))
    safe = {k: v for k, v in config.items() if k != "api_key_encrypted"}
    safe["api_key"] = "\u2022\u2022\u2022\u2022\u2022\u2022" if has_key else ""
    return EmailConfigResponse(**safe)


@router.put("/email", response_model=EmailConfigResponse)
async def update_email_config(body: EmailConfigUpdate) -> EmailConfigResponse:
    """Update email notification settings.

    If api_key is ``"••••••"`` (the masked placeholder), the existing
    encrypted key is preserved.  Send a new plaintext value to change it.

    The email channel is hot-reloaded so changes take effect immediately
    without requiring an app restart.
    """
    store = await _store()
    updates = body.model_dump(exclude_none=True)
    updated = store.update_email(updates)

    # Hot-reload: re-register (or unregister) the email channel so
    # config changes take effect without an app restart.
    try:
        from ctrade.notifications.channels.router import NotificationRouter
        router = NotificationRouter.get_instance()

        if updated.get("enabled"):
            api_key = store.get_email_api_key_decrypted()
            to_address = updated.get("to_address", "")
            if api_key and to_address:
                from ctrade.notifications.channels.email import EmailChannel
                router.register(
                    EmailChannel(
                        api_key=api_key,
                        from_address=updated.get("from_address", ""),
                        to_address=to_address,
                        notify_on_buy=updated.get("notify_on_buy", True),
                        notify_on_sell=updated.get("notify_on_sell", True),
                    )
                )
        else:
            router.unregister("email")
    except Exception:
        logger.warning("Email channel hot-reload failed", exc_info=True)

    # Return masked response
    has_key = bool(updated.get("api_key_encrypted"))
    safe = {k: v for k, v in updated.items() if k != "api_key_encrypted"}
    safe["api_key"] = "\u2022\u2022\u2022\u2022\u2022\u2022" if has_key else ""
    return EmailConfigResponse(**safe)


@router.post("/email/test")
async def test_email() -> dict[str, bool | str]:
    """Send a test email to verify MailerSend configuration.

    Returns ``{"success": true}`` if the MailerSend API accepted the
    message (HTTP 202), or ``{"success": false, "error": "..."}`` with
    details if something went wrong.
    """
    store = await _store()
    email_cfg = store.get_email()

    if not email_cfg.get("enabled"):
        raise HTTPException(status_code=422, detail="Email notifications are disabled")

    api_key = store.get_email_api_key_decrypted()
    if not api_key:
        raise HTTPException(
            status_code=422,
            detail="No MailerSend API key configured (or decryption failed)",
        )

    to_address = email_cfg.get("to_address", "")
    if not to_address:
        raise HTTPException(status_code=422, detail="No recipient (to_address) configured")

    from_address = email_cfg.get("from_address", "")

    # Send a real test email via MailerSend
    try:
        from ctrade.notifications.channels.email import EmailChannel

        channel = EmailChannel(
            api_key=api_key,
            from_address=from_address,
            to_address=to_address,
        )

        ok = await channel.send(
            message="This is a test email from cTrade to verify your notification settings are working correctly.",
            severity="info",
            metadata={"title": "cTrade Test Email"},
        )

        if ok:
            logger.info("Test email sent successfully to %s", to_address)
            return {"success": True, "error": ""}
        else:
            logger.warning("Test email failed — MailerSend rejected the request")
            return {
                "success": False,
                "error": (
                    "MailerSend rejected the request. Check that your API key is valid "
                    "and the from_address domain is verified in your MailerSend account."
                ),
            }
    except Exception as e:
        logger.warning("Test email error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}
