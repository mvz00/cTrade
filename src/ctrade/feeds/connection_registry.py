"""External API connection registry — defines all known connections and test probes.

The registry provides:
- ``get_all_connection_statuses()`` — reads cached state from feed singletons (no HTTP)
- ``test_connection(name)`` — lightweight HTTP probe with 10s timeout
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TEST_TIMEOUT = 10.0  # seconds


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CredentialFieldDef:
    """Definition of a single credential field for a connection."""

    key: str            # e.g. "api_key"
    label: str          # e.g. "API Key"
    env_var: str        # e.g. "CTRADE_FEEDS__COINMARKETCAP_API_KEY"
    is_secret: bool = True


@dataclass
class ConnectionDef:
    """Static definition of an external API connection."""

    name: str
    feed_name: str
    base_urls: list[str]
    requires_key: bool
    key_env_var: str
    description: str
    credential_fields: list[CredentialFieldDef] = field(default_factory=list)


@dataclass
class ConnectionStatus:
    """Runtime status of a connection (returned by GET /connections)."""

    name: str
    feed_name: str
    base_urls: list[str]
    requires_key: bool
    key_configured: bool
    feed_enabled: bool
    feed_healthy: bool
    status: str  # "untested" | "ok" | "error" | "disabled"
    last_checked: str | None
    error_message: str | None
    description: str
    credential_fields: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "feed_name": self.feed_name,
            "base_urls": self.base_urls,
            "requires_key": self.requires_key,
            "key_configured": self.key_configured,
            "feed_enabled": self.feed_enabled,
            "feed_healthy": self.feed_healthy,
            "status": self.status,
            "last_checked": self.last_checked,
            "error_message": self.error_message,
            "description": self.description,
            "credential_fields": self.credential_fields,
        }


@dataclass
class ConnectionTestResult:
    """Result of a connection test probe (returned by POST /connections/{name}/test)."""

    name: str
    success: bool
    latency_ms: int
    message: str
    tested_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "message": self.message,
            "tested_at": self.tested_at,
        }


# ---------------------------------------------------------------------------
# Connection definitions
# ---------------------------------------------------------------------------

_CONNECTIONS: list[ConnectionDef] = [
    ConnectionDef(
        name="CoinMarketCap",
        feed_name="coinmarketcap",
        base_urls=["https://pro-api.coinmarketcap.com"],
        requires_key=True,
        key_env_var="CTRADE_FEEDS__COINMARKETCAP_API_KEY",
        description="Market cap listings and momentum scores",
        credential_fields=[
            CredentialFieldDef(
                key="api_key",
                label="API Key",
                env_var="CTRADE_FEEDS__COINMARKETCAP_API_KEY",
            ),
        ],
    ),
    ConnectionDef(
        name="CryptoCompare",
        feed_name="sentiment",
        base_urls=["https://min-api.cryptocompare.com"],
        requires_key=False,
        key_env_var="",
        description="Crypto news for sentiment analysis",
    ),
    ConnectionDef(
        name="CoinGecko",
        feed_name="onchain",
        base_urls=["https://api.coingecko.com"],
        requires_key=False,
        key_env_var="",
        description="Market data, trending coins, and on-chain metrics",
    ),
    ConnectionDef(
        name="Reddit",
        feed_name="social_velocity",
        base_urls=["https://old.reddit.com", "https://www.reddit.com"],
        requires_key=False,
        key_env_var="",
        description="Subreddit mentions for social velocity tracking",
    ),
    ConnectionDef(
        name="Blockchain.info",
        feed_name="onchain",
        base_urls=["https://api.blockchain.info"],
        requires_key=False,
        key_env_var="",
        description="Bitcoin network stats and mempool data",
    ),
    ConnectionDef(
        name="Binance Futures",
        feed_name="market_sentiment",
        base_urls=["https://fapi.binance.com"],
        requires_key=False,
        key_env_var="",
        description="Long/short ratios, taker volume, and CVD data",
    ),
    ConnectionDef(
        name="Fear & Greed Index",
        feed_name="market_sentiment",
        base_urls=["https://api.alternative.me"],
        requires_key=False,
        key_env_var="",
        description="Crypto Fear & Greed Index",
    ),
    ConnectionDef(
        name="Exchange (ccxt)",
        feed_name="derivatives",
        base_urls=[],
        requires_key=True,
        key_env_var="(configured via Exchange settings)",
        description="Derivatives data (funding, OI, order book)",
    ),
]


def get_connection_def(name: str) -> ConnectionDef | None:
    """Look up a connection definition by name."""
    return next((c for c in _CONNECTIONS if c.name == name), None)


# ---------------------------------------------------------------------------
# Status retrieval (reads cached feed state — no external calls)
# ---------------------------------------------------------------------------


def get_all_connection_statuses() -> list[ConnectionStatus]:
    """Return the current status of all known connections.

    This reads cached state from feed singletons and settings — it makes
    NO external HTTP calls and is safe to call on every request.
    """
    from ctrade.settings import get_settings

    settings = get_settings()
    statuses: list[ConnectionStatus] = []

    # Build a map of feed_name → (enabled, healthy, last_fetch_time)
    feed_info = _get_feed_info()

    for conn in _CONNECTIONS:
        # Check if the required API key is configured
        key_configured = True
        if conn.requires_key:
            if conn.name == "Exchange (ccxt)":
                from ctrade.core.config_store import RuntimeConfigStore
                try:
                    store = RuntimeConfigStore.get()
                    key_configured = bool(store.list_exchanges())
                except RuntimeError:
                    key_configured = False
            elif conn.key_env_var:
                key_configured = bool(
                    _get_secret_value(settings, conn.key_env_var, connection_name=conn.name)
                )

        fi = feed_info.get(conn.feed_name)
        feed_enabled = fi["enabled"] if fi else False
        feed_healthy = fi["healthy"] if fi else False
        last_checked = fi["last_checked"] if fi else None

        # Determine status
        if conn.requires_key and not key_configured:
            status = "disabled"
        elif not feed_enabled:
            status = "disabled"
        elif feed_healthy:
            status = "ok"
        elif last_checked:
            status = "error"
        else:
            status = "untested"

        statuses.append(
            ConnectionStatus(
                name=conn.name,
                feed_name=conn.feed_name,
                base_urls=conn.base_urls,
                requires_key=conn.requires_key,
                key_configured=key_configured,
                feed_enabled=feed_enabled,
                feed_healthy=feed_healthy,
                status=status,
                last_checked=last_checked,
                error_message=None,
                description=conn.description,
                credential_fields=[
                    {"key": f.key, "label": f.label, "is_secret": f.is_secret}
                    for f in conn.credential_fields
                ],
            )
        )

    return statuses


def _get_feed_info() -> dict[str, dict[str, Any]]:
    """Collect enabled/healthy/last_fetch from all feed singletons."""
    info: dict[str, dict[str, Any]] = {}

    feed_classes = [
        ("coinmarketcap", "ctrade.feeds.coinmarketcap", "CoinMarketCapFeed"),
        ("sentiment", "ctrade.feeds.sentiment", "SentimentFeed"),
        ("onchain", "ctrade.feeds.onchain", "OnChainFeed"),
        ("derivatives", "ctrade.feeds.derivatives", "DerivativesFeed"),
        ("market_sentiment", "ctrade.feeds.market_sentiment", "MarketSentimentFeed"),
        ("cvd", "ctrade.feeds.cvd", "CVDFeed"),
        ("social_velocity", "ctrade.feeds.social_velocity", "SocialVelocityFeed"),
    ]

    for feed_name, module_path, class_name in feed_classes:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            instance = cls.get_instance()
            last_fetch = getattr(instance, "_last_fetch_time", 0)
            info[feed_name] = {
                "enabled": instance.is_enabled,
                "healthy": instance._healthy,
                "last_checked": (
                    datetime.fromtimestamp(last_fetch, tz=timezone.utc).isoformat()
                    if last_fetch > 0
                    else None
                ),
            }
        except Exception:
            info[feed_name] = {
                "enabled": False,
                "healthy": False,
                "last_checked": None,
            }

    return info


def _get_secret_value(settings: Any, env_var: str, connection_name: str = "") -> str:
    """Resolve a credential: RuntimeConfigStore first, then env var fallback.

    Priority:
    1. RuntimeConfigStore (UI-configured via Connections page)
    2. Environment variable (via FeedSettings)
    """
    # 1. Check RuntimeConfigStore first (UI-configured credentials)
    if connection_name:
        try:
            from ctrade.core.config_store import RuntimeConfigStore

            store = RuntimeConfigStore.get()
            enc = store.get_feed_credential(connection_name, "api_key")
            if enc is not None:
                from ctrade.security.vault import Vault

                enc_key = settings.encryption_key.get_secret_value()
                if enc_key:
                    vault = Vault(enc_key)
                    return vault.decrypt(enc)
        except (RuntimeError, Exception):
            pass  # Store not initialized or decryption failed — fall through

    # 2. Fall back to env var resolution
    # env_var like "CTRADE_FEEDS__COINMARKETCAP_API_KEY" → settings.feeds.coinmarketcap_api_key
    key = env_var.replace("CTRADE_FEEDS__", "").lower()
    feeds = settings.feeds
    attr = getattr(feeds, key, None)
    if attr is None:
        return ""
    if hasattr(attr, "get_secret_value"):
        return attr.get_secret_value()
    return str(attr)


# ---------------------------------------------------------------------------
# Connection test probes (makes actual HTTP calls)
# ---------------------------------------------------------------------------

# Test URLs: lightweight endpoints that return quickly
_TEST_PROBES: dict[str, str] = {
    "CoinMarketCap": "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?limit=1&convert=USD",
    "CryptoCompare": "https://min-api.cryptocompare.com/data/v2/news/?lang=EN&limit=1",
    "CoinGecko": "https://api.coingecko.com/api/v3/ping",
    "Reddit": "https://old.reddit.com/r/cryptocurrency/hot.json?limit=1",
    "Blockchain.info": "https://api.blockchain.info/stats",
    "Binance Futures": "https://fapi.binance.com/fapi/v1/ping",
    "Fear & Greed Index": "https://api.alternative.me/fng/?limit=1",
}


async def test_connection(name: str) -> ConnectionTestResult:
    """Test a specific connection by name with a lightweight HTTP probe.

    Returns a ``ConnectionTestResult`` with success/failure, latency, and message.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Special case: Exchange (ccxt) — test via ccxt, not HTTP
    if name == "Exchange (ccxt)":
        return await _test_exchange_connection(now)

    probe_url = _TEST_PROBES.get(name)
    if not probe_url:
        return ConnectionTestResult(
            name=name,
            success=False,
            latency_ms=0,
            message=f"Unknown connection: {name}",
            tested_at=now,
        )

    # Build headers (CoinMarketCap needs API key)
    headers: dict[str, str] = {"Accept": "application/json"}
    if name == "CoinMarketCap":
        from ctrade.settings import get_settings

        settings = get_settings()
        api_key = _get_secret_value(
            settings, "CTRADE_FEEDS__COINMARKETCAP_API_KEY", connection_name="CoinMarketCap"
        )
        if not api_key:
            return ConnectionTestResult(
                name=name,
                success=False,
                latency_ms=0,
                message="API key not configured",
                tested_at=now,
            )
        headers["X-CMC_PRO_API_KEY"] = api_key

    # Reddit needs a user-agent
    if name == "Reddit":
        headers["User-Agent"] = "cTrade/0.1 (connection-test)"

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
            resp = await client.get(probe_url, headers=headers)
            latency = int((time.monotonic() - start) * 1000)

            if resp.status_code < 400:
                return ConnectionTestResult(
                    name=name,
                    success=True,
                    latency_ms=latency,
                    message=f"Connected successfully ({latency}ms)",
                    tested_at=now,
                )
            else:
                return ConnectionTestResult(
                    name=name,
                    success=False,
                    latency_ms=latency,
                    message=f"HTTP {resp.status_code}: {resp.reason_phrase}",
                    tested_at=now,
                )
    except httpx.TimeoutException:
        latency = int((time.monotonic() - start) * 1000)
        return ConnectionTestResult(
            name=name,
            success=False,
            latency_ms=latency,
            message=f"Connection timed out after {_TEST_TIMEOUT}s",
            tested_at=now,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ConnectionTestResult(
            name=name,
            success=False,
            latency_ms=latency,
            message=str(exc),
            tested_at=now,
        )


async def _test_exchange_connection(tested_at: str) -> ConnectionTestResult:
    """Test the configured exchange connection via ccxt."""
    start = time.monotonic()
    try:
        from ctrade.exchange.market_data import MarketDataProvider
        provider = MarketDataProvider.get_instance()
        exchange = await provider._create_ccxt_exchange()
        await exchange.close()
        latency = int((time.monotonic() - start) * 1000)
        return ConnectionTestResult(
            name="Exchange (ccxt)",
            success=True,
            latency_ms=latency,
            message=f"Exchange connected ({latency}ms)",
            tested_at=tested_at,
        )
    except Exception as exc:
        latency = int((time.monotonic() - start) * 1000)
        return ConnectionTestResult(
            name="Exchange (ccxt)",
            success=False,
            latency_ms=latency,
            message=str(exc),
            tested_at=tested_at,
        )
