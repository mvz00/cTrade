"""Alerts API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ctrade.api.schemas.alerts import (
    AlertConfigResponse,
    AlertHistoryResponse,
    CreateAlertRequest,
)
from ctrade.notifications.alert_manager import AlertManager

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/", response_model=list[AlertConfigResponse])
async def list_alerts() -> list[AlertConfigResponse]:
    """List all alert configurations."""
    mgr = AlertManager.get_instance()
    return [AlertConfigResponse(**a) for a in mgr.list_alerts()]


@router.post("/", response_model=AlertConfigResponse, status_code=201)
async def create_alert(body: CreateAlertRequest) -> AlertConfigResponse:
    """Create a new alert."""
    mgr = AlertManager.get_instance()
    result = mgr.create_alert(
        alert_type=body.alert_type,
        symbol=body.symbol,
        value=body.value,
        message=body.message,
    )
    return AlertConfigResponse(**result)


@router.delete("/{alert_id}", status_code=204)
async def delete_alert(alert_id: str) -> None:
    """Delete an alert."""
    mgr = AlertManager.get_instance()
    if not mgr.delete_alert(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")


@router.put("/{alert_id}/toggle", response_model=AlertConfigResponse)
async def toggle_alert(alert_id: str) -> AlertConfigResponse:
    """Toggle an alert on/off."""
    mgr = AlertManager.get_instance()
    result = mgr.toggle_alert(alert_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertConfigResponse(**result)


@router.get("/history", response_model=list[AlertHistoryResponse])
async def alert_history(
    limit: int = Query(50, ge=1, le=200),
) -> list[AlertHistoryResponse]:
    """Get triggered alert history."""
    mgr = AlertManager.get_instance()
    return [AlertHistoryResponse(**h) for h in mgr.get_history(limit=limit)]
