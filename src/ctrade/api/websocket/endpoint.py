"""WebSocket endpoint and event-bus forwarder."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ctrade.api.websocket.manager import ConnectionManager
from ctrade.core.events import Event, EventBus, EventTypes

logger = logging.getLogger(__name__)

router = APIRouter()

# Event types forwarded from the EventBus to WebSocket clients
_FORWARDED_EVENTS: list[str] = [
    EventTypes.SIGNAL_GENERATED,
    EventTypes.ORDER_CREATED,
    EventTypes.ORDER_FILLED,
    EventTypes.ORDER_CANCELLED,
    EventTypes.ORDER_REJECTED,
    EventTypes.POSITION_OPENED,
    EventTypes.POSITION_CLOSED,
    EventTypes.STOP_LOSS_HIT,
    EventTypes.TAKE_PROFIT_HIT,
    EventTypes.CIRCUIT_BREAKER_TRIGGERED,
    EventTypes.ALERT_TRIGGERED,
    EventTypes.TICKER_UPDATE,
    EventTypes.SENTIMENT_UPDATE,
    EventTypes.ONCHAIN_UPDATE,
    EventTypes.LOG_ENTRY,
]


def register_event_forwarder(bus: EventBus) -> None:
    """Subscribe a handler for each forwarded event type that broadcasts
    to all connected WebSocket clients.
    """
    manager = ConnectionManager.get_instance()

    async def _forward(event: Event) -> None:
        if manager.connection_count > 0:
            await manager.broadcast(event.event_type, event.data)

    for evt in _FORWARDED_EVENTS:
        bus.subscribe(evt, _forward)

    logger.info("WebSocket event forwarder registered for %d event types", len(_FORWARDED_EVENTS))


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    """Main WebSocket endpoint.

    Protocol:
    1. Client connects (optionally with ``?token=<jwt>`` for auth).
    2. Within 2 seconds, client may send ``{"subscribe": ["signal.generated", ...]}``
       to filter which events they receive.  Empty or missing = receive all.
    3. Server sends ``{"type": "connected", "data": {...}}`` acknowledgement.
    4. Server pushes events as they happen.
    5. Client can send re-subscribe messages at any time.
    """
    await ws.accept()

    manager = ConnectionManager.get_instance()
    subscriptions: set[str] = set()

    # Optional: read initial subscription filter (with 2s timeout)
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=2.0)
        msg = json.loads(raw)
        if isinstance(msg.get("subscribe"), list):
            subscriptions = set(msg["subscribe"])
    except (asyncio.TimeoutError, json.JSONDecodeError, WebSocketDisconnect):
        pass  # No subscribe message or invalid — receive everything

    manager.connect(ws, subscriptions)

    # Send connection ack
    try:
        await ws.send_text(json.dumps({
            "type": "connected",
            "data": {
                "subscriptions": sorted(subscriptions) if subscriptions else "all",
                "available_events": sorted(_FORWARDED_EVENTS),
            },
        }))
    except Exception:
        manager.disconnect(ws)
        return

    # Keep-alive loop — listen for re-subscribe messages
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                if isinstance(msg.get("subscribe"), list):
                    subscriptions = set(msg["subscribe"])
                    manager.update_subscriptions(ws, subscriptions)
                    await ws.send_text(json.dumps({
                        "type": "subscribed",
                        "data": {"subscriptions": sorted(subscriptions) if subscriptions else "all"},
                    }))
            except json.JSONDecodeError:
                pass  # Ignore invalid JSON
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws)
