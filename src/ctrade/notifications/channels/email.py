"""Email (SMTP) notification channel."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

logger = logging.getLogger(__name__)

# Severity → emoji + color for HTML email
_SEVERITY_STYLE = {
    "info": ("#3498DB", "\u2139\ufe0f"),
    "warning": ("#F39C12", "\u26a0\ufe0f"),
    "critical": ("#E74C3C", "\U0001f6a8"),
    "success": ("#2ECC71", "\u2705"),
}


class EmailChannel:
    """Send notifications via SMTP email.

    Implements the ``NotificationChannel`` protocol:
      ``async send(message, severity, metadata) -> bool``

    Uses Python's built-in ``smtplib`` via ``asyncio.to_thread()``
    to avoid blocking the event loop.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_address: str,
        to_address: str,
        use_tls: bool = True,
    ) -> None:
        self.name = "email"
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._username = username
        self._password = password
        self._from_address = from_address
        self._to_address = to_address
        self._use_tls = use_tls

    async def send(
        self,
        message: str,
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Send an email notification via SMTP (runs in thread pool)."""
        try:
            meta = metadata or {}
            subject = self._build_subject(message, severity, meta)
            html_body = self._build_html(message, severity, meta)

            msg = MIMEMultipart("alternative")
            msg["From"] = self._from_address
            msg["To"] = self._to_address
            msg["Subject"] = subject

            # Plain text fallback
            msg.attach(MIMEText(message, "plain"))
            # HTML version
            msg.attach(MIMEText(html_body, "html"))

            await asyncio.to_thread(self._send_smtp, msg)
            logger.debug("Email notification sent: %s", subject)
            return True
        except Exception:
            logger.warning("Failed to send email notification", exc_info=True)
            return False

    def _send_smtp(self, msg: MIMEMultipart) -> None:
        """Synchronous SMTP send (called in thread pool)."""
        if self._use_tls:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                if self._username and self._password:
                    server.login(self._username, self._password)
                server.sendmail(self._from_address, [self._to_address], msg.as_string())
        else:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=15) as server:
                if self._username and self._password:
                    server.login(self._username, self._password)
                server.sendmail(self._from_address, [self._to_address], msg.as_string())

    @staticmethod
    def _build_subject(
        message: str, severity: str, meta: dict[str, Any],
    ) -> str:
        """Build a concise email subject line."""
        emoji = _SEVERITY_STYLE.get(severity, _SEVERITY_STYLE["info"])[1]
        title = meta.get("title", "")
        if title:
            return f"{emoji} cTrade: {title}"
        # Truncate message for subject
        short = message[:80] + ("..." if len(message) > 80 else "")
        return f"{emoji} cTrade: {short}"

    @staticmethod
    def _build_html(
        message: str, severity: str, meta: dict[str, Any],
    ) -> str:
        """Build an HTML email body with order details."""
        color = _SEVERITY_STYLE.get(severity, _SEVERITY_STYLE["info"])[0]

        # Build detail rows from metadata
        detail_rows = ""
        field_labels = {
            "pair": "Pair",
            "side": "Side",
            "quantity": "Quantity",
            "price": "Price",
            "fee": "Fee",
            "mode": "Mode",
            "alert_type": "Alert Type",
            "value": "Value",
        }
        for key, label in field_labels.items():
            if key in meta:
                val = meta[key]
                if isinstance(val, float):
                    val = f"{val:.8g}"
                detail_rows += (
                    f'<tr><td style="padding:4px 12px 4px 0;color:#888;">'
                    f"{label}</td>"
                    f'<td style="padding:4px 0;font-weight:600;">'
                    f"{val}</td></tr>"
                )

        details_table = ""
        if detail_rows:
            details_table = (
                f'<table style="margin:16px 0;border-collapse:collapse;">'
                f"{detail_rows}</table>"
            )

        return f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
                     max-width:480px;margin:0 auto;padding:24px;">
            <div style="border-left:4px solid {color};padding:12px 16px;
                        background:#f8f9fa;border-radius:4px;">
                <h2 style="margin:0 0 8px;font-size:16px;color:#333;">
                    {meta.get("title", "cTrade Notification")}
                </h2>
                <p style="margin:0;color:#555;font-size:14px;">{message}</p>
            </div>
            {details_table}
            <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
            <p style="color:#aaa;font-size:11px;margin:0;">
                Sent by cTrade &bull; Automated trading notification
            </p>
        </div>
        """
