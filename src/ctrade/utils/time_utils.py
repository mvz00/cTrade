"""Timezone-aware time utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Ensure a datetime is timezone-aware in UTC.

    If naive (no tzinfo), assumes UTC and adds timezone info.
    If aware but not UTC, converts to UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def timestamp_ms() -> int:
    """Get current UTC time as milliseconds since epoch."""
    return int(utc_now().timestamp() * 1000)


def from_timestamp_ms(ts_ms: int) -> datetime:
    """Convert milliseconds since epoch to UTC datetime."""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
