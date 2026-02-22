"""Tests for notification channels (Discord, Telegram, Router)."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from ctrade.notifications.channels.discord import DiscordChannel
from ctrade.notifications.channels.router import NotificationRouter
from ctrade.notifications.channels.telegram import TelegramChannel


@pytest.fixture(autouse=True)
def reset_router():
    NotificationRouter.reset()
    yield
    NotificationRouter.reset()


class TestDiscordChannel:
    @respx.mock
    @pytest.mark.anyio
    async def test_send_success(self):
        webhook_url = "https://discord.com/api/webhooks/123/abc"
        respx.post(webhook_url).mock(return_value=Response(204))

        channel = DiscordChannel(webhook_url)
        assert channel.name == "discord"
        result = await channel.send("Test alert", severity="info", metadata={"pair": "BTC/USDT"})
        assert result is True

    @respx.mock
    @pytest.mark.anyio
    async def test_send_failure(self):
        webhook_url = "https://discord.com/api/webhooks/123/abc"
        respx.post(webhook_url).mock(return_value=Response(500, text="Server Error"))

        channel = DiscordChannel(webhook_url)
        result = await channel.send("Test alert")
        assert result is False


class TestTelegramChannel:
    @respx.mock
    @pytest.mark.anyio
    async def test_send_success(self):
        respx.post("https://api.telegram.org/bot123:TOKEN/sendMessage").mock(
            return_value=Response(200, json={"ok": True})
        )

        channel = TelegramChannel("123:TOKEN", "456")
        assert channel.name == "telegram"
        result = await channel.send("Test alert", severity="warning", metadata={"pair": "ETH/USDT"})
        assert result is True

    @respx.mock
    @pytest.mark.anyio
    async def test_send_failure(self):
        respx.post("https://api.telegram.org/bot123:TOKEN/sendMessage").mock(
            return_value=Response(403, text="Forbidden")
        )

        channel = TelegramChannel("123:TOKEN", "456")
        result = await channel.send("Test alert")
        assert result is False


class TestNotificationRouter:
    def test_singleton(self):
        a = NotificationRouter.get_instance()
        b = NotificationRouter.get_instance()
        assert a is b

    def test_register_channel(self):
        router = NotificationRouter.get_instance()
        channel = DiscordChannel("https://example.com/webhook")
        router.register(channel)
        assert "discord" in router.list_channels()

    @respx.mock
    @pytest.mark.anyio
    async def test_dispatch_multiple_channels(self):
        respx.post("https://discord.com/api/webhooks/123/abc").mock(
            return_value=Response(204)
        )
        respx.post("https://api.telegram.org/bot123:TOKEN/sendMessage").mock(
            return_value=Response(200, json={"ok": True})
        )

        router = NotificationRouter.get_instance()
        router.register(DiscordChannel("https://discord.com/api/webhooks/123/abc"))
        router.register(TelegramChannel("123:TOKEN", "456"))

        results = await router.dispatch("Alert fired!", severity="critical")
        assert results["discord"] is True
        assert results["telegram"] is True

    @pytest.mark.anyio
    async def test_dispatch_empty(self):
        router = NotificationRouter.get_instance()
        results = await router.dispatch("No channels")
        assert results == {}
