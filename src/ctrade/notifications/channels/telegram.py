"""Telegram bot notification channel."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {
    "info": "\u2139\ufe0f",        # ℹ️
    "warning": "\u26a0\ufe0f",     # ⚠️
    "critical": "\U0001f6a8",      # 🚨
    "success": "\u2705",           # ✅
}

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramChannel:
    """Send notifications via Telegram Bot API.

    Implements the ``NotificationChannel`` protocol:
      ``async send(message, severity, metadata) -> bool``
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.name = "telegram"
        self._bot_token = bot_token
        self._chat_id = chat_id

    async def send(
        self,
        message: str,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send a Markdown-formatted message to the configured chat."""
        meta = metadata or {}
        emoji = _SEVERITY_EMOJI.get(severity, _SEVERITY_EMOJI["info"])

        lines = [f"{emoji} *{meta.get('title', 'cTrade Alert')}*", ""]
        lines.append(message)

        if "pair" in meta:
            lines.append(f"\nPair: `{meta['pair']}`")
        if "alert_type" in meta:
            lines.append(f"Type: `{meta['alert_type']}`")

        text = "\n".join(lines)
        url = _TELEGRAM_API.format(token=self._bot_token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            logger.debug("Telegram notification sent: %s", message[:80])
            return True
        except Exception:
            logger.warning("Failed to send Telegram notification", exc_info=True)
            return False
