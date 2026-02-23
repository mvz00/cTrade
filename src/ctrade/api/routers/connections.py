"""External API connections management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["connections"])


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
