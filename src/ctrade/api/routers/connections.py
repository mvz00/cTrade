"""External API connections management endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["connections"])


class ConnectionCredentialsRequest(BaseModel):
    """Request body for updating connection credentials."""

    credentials: dict[str, str]


@router.get("/connections")
async def list_connections() -> dict[str, Any]:
    """List all external API connections with their current status.

    Returns cached feed state — no external HTTP calls are made.
    """
    from ctrade.feeds.connection_registry import get_all_connection_statuses

    statuses = get_all_connection_statuses()
    return {"connections": [s.to_dict() for s in statuses]}


@router.post("/connections/{name}/test")
async def test_connection_endpoint(name: str) -> dict[str, Any]:
    """Test a specific external API connection with a lightweight probe.

    Makes an actual HTTP request to the external API and returns the result
    with latency information.
    """
    from ctrade.feeds.connection_registry import test_connection

    result = await test_connection(name)
    return result.to_dict()


@router.put("/connections/{name}/credentials")
async def update_connection_credentials(
    name: str,
    body: ConnectionCredentialsRequest,
) -> dict[str, Any]:
    """Update API credentials for a connection.

    Encrypts the provided credentials and persists them in the runtime config store.
    These credentials take priority over environment variables.
    """
    from ctrade.core.config_store import RuntimeConfigStore
    from ctrade.feeds.connection_registry import get_connection_def
    from ctrade.security.vault import Vault
    from ctrade.settings import get_settings

    # Validate connection exists
    conn_def = get_connection_def(name)
    if conn_def is None:
        raise HTTPException(status_code=404, detail=f"Unknown connection: {name}")

    # Exchange (ccxt) credentials are managed on the Exchanges page
    if name == "Exchange (ccxt)":
        raise HTTPException(
            status_code=400,
            detail="Exchange credentials are managed on the Exchanges page",
        )

    if not conn_def.credential_fields:
        raise HTTPException(
            status_code=400,
            detail=f"{name} does not have configurable credentials",
        )

    # Validate field keys match the connection's credential_fields
    valid_keys = {f.key for f in conn_def.credential_fields}
    for field_key in body.credentials:
        if field_key not in valid_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown credential field '{field_key}' for {name}. "
                f"Valid fields: {', '.join(sorted(valid_keys))}",
            )

    # Filter out empty values (empty means "keep current")
    non_empty = {k: v for k, v in body.credentials.items() if v.strip()}
    if not non_empty:
        raise HTTPException(status_code=422, detail="No credential values provided")

    # Encrypt and store
    settings = get_settings()
    encryption_key = settings.encryption_key.get_secret_value()
    if not encryption_key:
        raise HTTPException(
            status_code=500,
            detail="No encryption key configured. Set CTRADE_ENCRYPTION_KEY env var.",
        )

    vault = Vault(encryption_key)
    store = RuntimeConfigStore.get()
    store.set_feed_credentials(name, non_empty, vault)
    logger.info("Connection credentials updated: %s", name)

    return {"message": f"Credentials for {name} updated successfully"}
