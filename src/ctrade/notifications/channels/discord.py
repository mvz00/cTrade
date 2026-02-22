"""Discord webhook notification channel."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Embed color mapping by severity
_SEVERITY_COLORS = {
    "info": 0x3498DB,       # Blue
    "warning": 0xF39C12,    # Yellow/Amber
    "critical": 0xE74C3C,   # Red
    "success": 0x2ECC71,    # Green
}


class DiscordChannel:
    """Send notifications via Discord webhook.

    Implements the ``NotificationChannel`` protocol:
      ``async send(message, severity, metadata) -> bool``
    """

    def __init__(self, webhook_url: str) -> None:
        self.name = "discord"
        self._webhook_url = webhook_url

    async def send(
        self,
        message: str,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """POST a rich embed to the Discord webhook."""
        meta = metadata or {}
        color = _SEVERITY_COLORS.get(severity, _SEVERITY_COLORS["info"])

        embed: dict[str, Any] = {
            "title": meta.get("title", "cTrade Alert"),
            "description": message,
            "color": color,
            "footer": {"text": "cTrade"},
        }

        # Optional fields
        fields: list[dict[str, Any]] = []
        if "pair" in meta:
            fields.append({"name": "Pair", "value": meta["pair"], "inline": True})
        if "alert_type" in meta:
            fields.append({"name": "Type", "value": meta["alert_type"], "inline": True})
        if fields:
            embed["fields"] = fields

        payload = {"embeds": [embed]}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
            logger.debug("Discord notification sent: %s", message[:80])
            return True
        except Exception:
            logger.warning("Failed to send Discord notification", exc_info=True)
            return False
