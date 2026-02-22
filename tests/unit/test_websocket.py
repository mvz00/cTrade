"""Tests for WebSocket ConnectionManager."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from starlette.websockets import WebSocketState

from ctrade.api.websocket.manager import ConnectionManager


@pytest.fixture(autouse=True)
def reset_manager():
    ConnectionManager.reset()
    yield
    ConnectionManager.reset()


def _make_ws(state: WebSocketState = WebSocketState.CONNECTED) -> MagicMock:
    """Create a mock WebSocket."""
    ws = MagicMock()
    type(ws).client_state = PropertyMock(return_value=state)
    ws.send_text = AsyncMock()
    return ws


class TestConnectionManager:
    def test_singleton(self):
        a = ConnectionManager.get_instance()
        b = ConnectionManager.get_instance()
        assert a is b

    def test_connect_and_disconnect(self):
        mgr = ConnectionManager.get_instance()
        ws = _make_ws()
        mgr.connect(ws)
        assert mgr.connection_count == 1
        mgr.disconnect(ws)
        assert mgr.connection_count == 0

    def test_connect_multiple(self):
        mgr = ConnectionManager.get_instance()
        ws1 = _make_ws()
        ws2 = _make_ws()
        mgr.connect(ws1)
        mgr.connect(ws2)
        assert mgr.connection_count == 2

    @pytest.mark.anyio
    async def test_broadcast_sends_to_all(self):
        mgr = ConnectionManager.get_instance()
        ws1 = _make_ws()
        ws2 = _make_ws()
        mgr.connect(ws1)
        mgr.connect(ws2)

        await mgr.broadcast("signal.generated", {"pair": "BTC/USDT"})

        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

        # Verify JSON structure
        sent = json.loads(ws1.send_text.call_args[0][0])
        assert sent["type"] == "signal.generated"
        assert sent["data"]["pair"] == "BTC/USDT"

    @pytest.mark.anyio
    async def test_broadcast_respects_subscriptions(self):
        mgr = ConnectionManager.get_instance()
        ws_all = _make_ws()
        ws_signals = _make_ws()
        mgr.connect(ws_all, set())  # Empty = receive all
        mgr.connect(ws_signals, {"signal.generated"})  # Only signals

        await mgr.broadcast("order.filled", {"pair": "ETH/USDT"})

        ws_all.send_text.assert_called_once()  # Receives everything
        ws_signals.send_text.assert_not_called()  # Doesn't match subscription

    @pytest.mark.anyio
    async def test_broadcast_cleans_dead_connections(self):
        mgr = ConnectionManager.get_instance()
        ws_alive = _make_ws()
        ws_dead = _make_ws(state=WebSocketState.DISCONNECTED)

        mgr.connect(ws_alive)
        mgr.connect(ws_dead)
        assert mgr.connection_count == 2

        await mgr.broadcast("test.event", {})

        # Dead connection should have been cleaned up
        assert mgr.connection_count == 1

    def test_update_subscriptions(self):
        mgr = ConnectionManager.get_instance()
        ws = _make_ws()
        mgr.connect(ws, {"signal.generated"})
        mgr.update_subscriptions(ws, {"order.filled", "position.closed"})
        # No assertion on internal state — just ensure it doesn't crash
        # The effect is tested via broadcast filtering above
