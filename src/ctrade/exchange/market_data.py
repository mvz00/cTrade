"""Market data provider — fetches prices from ccxt or generates simulated data.

When no exchange is configured, provides realistic simulated market data
so the app works out of the box without API keys.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import math
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, ClassVar

from ctrade.core.enums import Timeframe
from ctrade.core.models import Candle, Ticker

logger = logging.getLogger(__name__)

# Top ~50 coins with approximate USD prices for seed/simulation data.
# Used to dynamically generate trading pairs for any quote currency.
_TOP_COINS: dict[str, float] = {
    # Major caps
    "BTC": 67000.0, "ETH": 3500.0, "SOL": 145.0, "BNB": 580.0,
    "XRP": 0.62, "ADA": 0.45, "DOGE": 0.082, "DOT": 7.20,
    "AVAX": 35.0, "LINK": 14.50, "MATIC": 0.58, "UNI": 9.80,
    "SHIB": 0.000009, "LTC": 72.0, "ATOM": 8.50, "FIL": 5.80,
    "NEAR": 5.20, "APT": 8.90, "ARB": 1.10, "OP": 2.30,
    "SUI": 1.05, "SEI": 0.42, "INJ": 22.0, "TIA": 8.50,
    "PEPE": 0.0000085, "WIF": 2.10, "FET": 1.60, "RENDER": 6.80,
    "GRT": 0.22, "AAVE": 95.0, "MKR": 1500.0, "CRV": 0.55,
    "ALGO": 0.18, "VET": 0.028, "SAND": 0.42, "MANA": 0.38,
    "AXS": 7.50, "HBAR": 0.075, "FTM": 0.35, "THETA": 1.10,
    "XLM": 0.11, "ICP": 12.0, "TRX": 0.12, "EOS": 0.78,
    "FLOW": 0.72, "CHZ": 0.068, "IMX": 1.80, "GALA": 0.028,
    "1INCH": 0.35, "SUSHI": 1.10, "COMP": 52.0,
    # Extended coverage for exchanges with 100+ pairs (e.g. CoinSpot BTC)
    "TON": 5.80, "EGLD": 38.0, "KAS": 0.12, "CELO": 0.65,
    "ROSE": 0.10, "MINA": 0.75, "KAVA": 0.68, "ZIL": 0.022,
    "ONE": 0.015, "IOTA": 0.22, "XTZ": 0.85, "NEO": 11.0,
    "QTUM": 3.20, "SNX": 2.50, "BAL": 3.80, "YFI": 6800.0,
    "LDO": 1.60, "DYDX": 1.40, "RPL": 22.0, "PENDLE": 4.50,
    "CAKE": 2.50, "ENJ": 0.28, "APE": 1.10, "CRO": 0.088,
    "KCS": 8.50, "STORJ": 0.55, "AR": 22.0, "LPT": 15.0,
    "ANKR": 0.028, "OCEAN": 0.40, "JASMY": 0.018, "FLOKI": 0.00015,
    "BONK": 0.000018, "ONDO": 0.85, "WLD": 2.20, "STX": 1.60,
    "CFX": 0.18, "RSR": 0.005, "ZRX": 0.38, "BAT": 0.22,
    "ENS": 15.0, "SKL": 0.040, "COTI": 0.065, "CELR": 0.018,
    "HOT": 0.0018, "DENT": 0.0012, "ACH": 0.022, "RLC": 1.80,
    "WAVES": 1.60, "JUP": 0.70,
}

# Approximate USD → quote currency conversion rates.
_QUOTE_RATES: dict[str, float] = {
    "USDT": 1.0, "USDC": 1.0, "USD": 1.0,
    "BTC": 1.0 / 67000.0,
    "AUD": 1.54,
    "EUR": 0.92,
}


def _generate_seed_pairs(quotes: set[str] | None = None) -> dict[str, float]:
    """Generate seed pairs by combining top coins with quote currencies.

    For each coin in ``_TOP_COINS`` and each requested quote currency,
    produces a ``BASE/QUOTE`` pair with a realistic approximate price.
    Self-pairs (e.g. BTC/BTC) are excluded.
    """
    if quotes is None:
        quotes = set(_QUOTE_RATES.keys())
    pairs: dict[str, float] = {}
    for base, usd_price in _TOP_COINS.items():
        for quote in quotes:
            if base == quote:
                continue
            rate = _QUOTE_RATES.get(quote, 1.0)
            pairs[f"{base}/{quote}"] = round(usd_price * rate, 8)
    return pairs


# Pre-generate seed prices for all known quote currencies (~250 pairs).
_SEED_PRICES: dict[str, float] = _generate_seed_pairs()

# Stablecoins and fiat treated as USD-equivalent for portfolio valuation.
_CASH_CURRENCIES: set[str] = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD",  # stablecoins
    "USD", "EUR", "GBP", "AUD", "CAD", "JPY", "CHF",  # fiat
}

# Fiat → approximate USD conversion (good enough for portfolio display).
_FIAT_TO_USD: dict[str, float] = {
    "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "AUD": 0.65,
    "CAD": 0.74, "JPY": 0.0067, "CHF": 1.13,
}

_TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
}

# Binance public spot klines (no auth required) — used as candle fallback
# when the configured exchange (e.g. CoinSpot) doesn't support OHLCV.
_BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"

# Exchanges whose ccxt module doesn't implement parse_order(), causing
# create_order() to throw NotSupported after the API call has already
# succeeded.  We monkey-patch a minimal stub on these instances.
_EXCHANGES_MISSING_PARSE_ORDER: set[str] = {"coinspot"}


def _make_stub_parse_order(instance: Any) -> Any:
    """Return a minimal ``parse_order`` for exchanges that don't implement it.

    The returned function produces a ccxt-compatible order dict with mostly
    ``None`` fields.  Downstream code in ``live_engine.py`` already handles
    missing fields gracefully (falls back to ticker price and requested qty).
    """

    def _parse_order(order_data: dict, market: Any = None) -> dict:  # noqa: ARG001
        return {
            "id": order_data.get("id") if isinstance(order_data, dict) else None,
            "clientOrderId": None,
            "timestamp": None,
            "datetime": None,
            "lastTradeTimestamp": None,
            "status": (
                "open"
                if isinstance(order_data, dict) and order_data.get("status") == "ok"
                else None
            ),
            "symbol": None,
            "type": "limit",
            "side": None,
            "price": None,
            "amount": None,
            "filled": None,
            "remaining": None,
            "cost": None,
            "fee": None,
            "average": None,
            "trades": None,
            "info": order_data if isinstance(order_data, dict) else {},
        }

    return _parse_order


class MarketDataProvider:
    """Provides market data from ccxt exchanges or simulated fallback."""

    _instance: ClassVar[MarketDataProvider | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    _TICKER_CACHE_TTL = 300  # 5 minutes — shared across snapshot task & dashboard

    def __init__(self) -> None:
        self._sim_prices: dict[str, float] = dict(_SEED_PRICES)
        self._sim_rng = random.Random(42)
        self._data_lock = threading.Lock()
        self._cached_exchange_pairs: list[str] | None = None
        self._ticker_cache: dict[str, tuple[Ticker, float]] = {}  # key → (ticker, epoch); "symbol" or "symbol:exchange_id"

    @classmethod
    def get_instance(cls) -> MarketDataProvider:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = None

    async def get_available_pairs(self) -> list[str]:
        """Return available trading pairs from ALL configured exchanges.

        For each exchange, loads markets and filters by that exchange's
        configured ``quote_currencies``.  Returns the sorted union of all
        pairs.  Falls back to the simulated seed list when no exchange is
        configured.
        """
        # Return cache if available
        if self._cached_exchange_pairs is not None:
            return self._cached_exchange_pairs

        from ctrade.core.config_store import RuntimeConfigStore
        try:
            store = RuntimeConfigStore.get()
            exchanges_list = store.list_exchanges()
        except RuntimeError:
            return list(_SEED_PRICES.keys())

        if not exchanges_list:
            return list(_SEED_PRICES.keys())

        all_pairs: set[str] = set()
        all_configured_quotes: set[str] = set()
        # Track which quote currencies received real markets from ccxt
        quotes_with_real_markets: set[str] = set()

        for ex_info in exchanges_list:
            if not ex_info.get("is_active", True):
                continue
            entry = store.get_exchange_entry(ex_info["id"])
            if not entry:
                continue

            quote_currencies = set(entry.quote_currencies)
            all_configured_quotes.update(quote_currencies)

            exchange = await self._create_ccxt_exchange(ex_info["id"])
            if not exchange:
                logger.warning(
                    "Could not create ccxt instance for %s — "
                    "seed pairs will be used for its quote currencies",
                    entry.name,
                )
                continue
            try:
                markets = await exchange.load_markets()
                for symbol, info in markets.items():
                    if (
                        info.get("quote") in quote_currencies
                        and info.get("active", True)
                        and info.get("spot", True)
                    ):
                        all_pairs.add(symbol)
                        quotes_with_real_markets.add(info.get("quote", ""))
            except Exception as e:
                logger.warning(
                    "Failed to load markets from %s: %s — "
                    "seed pairs will be used for its quote currencies",
                    entry.name, e,
                )
            finally:
                await exchange.close()

        # Supplement with seed pairs only for quote currencies where NO
        # exchange returned real markets.  This prevents showing pairs
        # (e.g. ADA/BTC) that ccxt can't actually trade on the exchange.
        for symbol in _SEED_PRICES:
            quote = symbol.split("/")[1]
            if quote in all_configured_quotes and quote not in quotes_with_real_markets:
                all_pairs.add(symbol)

        if all_pairs:
            pairs = sorted(all_pairs)
            self._cached_exchange_pairs = pairs
            logger.info(
                "Loaded %d pairs for quote currencies %s",
                len(pairs), sorted(all_configured_quotes),
            )
            return pairs

        # No pairs from any exchange — fall back to full simulated list
        return list(_SEED_PRICES.keys())

    def clear_pairs_cache(self) -> None:
        """Clear the cached exchange pairs (e.g. after exchange config change)."""
        self._cached_exchange_pairs = None

    def clear_ticker_cache(self) -> None:
        """Clear the cached ticker prices (e.g. after exchange toggle)."""
        self._ticker_cache.clear()

    async def get_ticker(self, symbol: str) -> Ticker:
        """Get current ticker for a symbol."""
        # Try ccxt first
        ticker = await self._try_ccxt_ticker(symbol)
        if ticker:
            return ticker
        # Fall back to simulated
        return self._simulated_ticker(symbol)

    async def get_candles(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[Candle]:
        """Get OHLCV candles for a symbol.

        Tries three sources in order:
        1. ccxt exchange (authenticated, exchange-native OHLCV)
        2. Binance public spot API (unauthenticated, real market data)
        3. Simulated candles (deterministic random walk, last resort)
        """
        # 1. Try the configured exchange via ccxt
        candles = await self._try_ccxt_candles(symbol, timeframe, limit)
        if candles:
            return candles

        # 2. Try Binance public spot klines (no auth needed)
        candles = await self._try_binance_public_candles(symbol, timeframe, limit)
        if candles:
            return candles

        # 3. Last resort: simulated data
        logger.warning(
            "Using simulated candles for %s (ccxt and Binance public both unavailable)",
            symbol,
        )
        return self._simulated_candles(symbol, timeframe, limit)

    async def _create_ccxt_exchange(self, exchange_id: str | None = None) -> Any | None:
        """Create an async ccxt exchange instance.

        If ``exchange_id`` is provided, uses that specific exchange.
        Otherwise, uses the first configured exchange (backward compatible).

        Returns the exchange object (caller must call ``await exchange.close()``),
        or ``None`` if no exchange is configured.
        """
        try:
            from ctrade.core.config_store import RuntimeConfigStore
            store = RuntimeConfigStore.get()
            exchanges = store.list_exchanges()
            if not exchanges:
                logger.warning("_create_ccxt_exchange: no exchanges configured")
                return None

            from ctrade.security.vault import Vault
            from ctrade.settings import get_settings
            settings = get_settings()
            key = settings.encryption_key.get_secret_value()
            if not key:
                logger.warning("_create_ccxt_exchange: no encryption key")
                return None
            vault = Vault(key)

            if exchange_id:
                entry = store.get_exchange_entry(exchange_id)
            else:
                entry = store.get_exchange_entry(exchanges[0]["id"])
            if not entry:
                logger.warning("_create_ccxt_exchange: entry not found for id=%s", exchange_id)
                return None

            import ccxt.async_support as ccxt_async
            exchange_class = getattr(ccxt_async, entry.name, None)
            if not exchange_class:
                # Try lowercase fallback (ccxt uses lowercase class names)
                exchange_class = getattr(ccxt_async, entry.name.lower(), None)
            if not exchange_class:
                logger.warning(
                    "_create_ccxt_exchange: ccxt has no class for '%s'", entry.name
                )
                return None

            api_key = vault.decrypt(entry.api_key_encrypted)
            api_secret = vault.decrypt(entry.api_secret_encrypted)
            config: dict[str, Any] = {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                # Use millisecond nonce — CoinSpot (and some other exchanges)
                # reject second-based nonces if a higher nonce was previously
                # used from another tool or session.
                "nonce": lambda: int(time.time() * 1000),
            }
            if entry.passphrase_encrypted:
                config["password"] = vault.decrypt(entry.passphrase_encrypted)

            instance = exchange_class(config)
            await instance.load_markets()

            # Extend ccxt markets with configured quote currencies.
            # Some exchanges (e.g. CoinSpot) expose only a small subset
            # of their markets via the ccxt API, but their order placement
            # endpoints accept any valid coin/market pair.  Injecting
            # synthetic market entries lets ccxt resolve symbols like
            # ADA/BTC even when load_markets() didn't return them.
            # Track which symbols are synthetic (injected by us, not returned
            # by load_markets).  Live orders must be rejected for these pairs
            # because the exchange API doesn't truly support them — tickers
            # return wrong-currency prices and orders hit the wrong endpoint.
            synthetic_symbols: set[str] = set()

            if entry and hasattr(instance, 'markets') and instance.markets:
                existing_quotes = {m.get("quote") for m in instance.markets.values()}
                missing_quotes = set(entry.quote_currencies) - existing_quotes
                if missing_quotes:
                    injected = 0
                    for base in _TOP_COINS:
                        for quote in missing_quotes:
                            sym = f"{base}/{quote}"
                            if sym not in instance.markets:
                                instance.markets[sym] = {
                                    "id": base.lower(),
                                    "symbol": sym,
                                    "base": base,
                                    "quote": quote,
                                    "baseId": base.lower(),
                                    "quoteId": quote.lower(),
                                    "type": "spot",
                                    "spot": True,
                                    "active": True,
                                    "precision": {
                                        "amount": None,
                                        "price": None,
                                        "cost": None,
                                        "base": None,
                                        "quote": None,
                                    },
                                    "limits": {
                                        "leverage": {"min": None, "max": None},
                                        "amount": {"min": None, "max": None},
                                        "price": {"min": None, "max": None},
                                        "cost": {"min": None, "max": None},
                                    },
                                    "info": {},
                                }
                                synthetic_symbols.add(sym)
                                injected += 1
                    if injected:
                        logger.info(
                            "Injected %d synthetic %s market(s) into %s "
                            "(ccxt only returned %s quotes)",
                            injected,
                            ", ".join(sorted(missing_quotes)),
                            entry.name,
                            ", ".join(sorted(existing_quotes)),
                        )

            # Expose synthetic symbols so live_engine can block orders for them.
            instance._ctrade_synthetic_symbols = synthetic_symbols  # type: ignore[attr-defined]

            # Some exchanges (e.g. CoinSpot) don't implement parse_order()
            # in their ccxt module, causing create_order() to throw
            # NotSupported *after* the API call has already succeeded.
            # Provide a minimal stub so the raw response propagates back.
            if instance.id in _EXCHANGES_MISSING_PARSE_ORDER:
                instance.parse_order = _make_stub_parse_order(instance)
                logger.debug("Patched parse_order for %s", instance.id)

            return instance
        except Exception as e:
            logger.warning("Failed to create ccxt exchange (id=%s): %s", exchange_id, e)
            return None

    async def _try_ccxt_ticker(
        self, symbol: str, exchange_id: str | None = None,
    ) -> Ticker | None:
        """Try to fetch a ticker for *symbol*.

        When ``exchange_id`` is provided, fetches ONLY from that specific
        exchange (exchange-scoped pricing for portfolio valuation).
        When ``None``, iterates all active exchanges until one succeeds
        (best-effort pricing for trading operations).

        Results are cached for ``_TICKER_CACHE_TTL`` seconds.  Cache keys
        are scoped by ``exchange_id`` to prevent cross-exchange price bleed.
        """
        cache_key = f"{symbol}:{exchange_id}" if exchange_id else symbol

        # ---- check cache first ----
        cached = self._ticker_cache.get(cache_key)
        if cached is not None:
            ticker, ts = cached
            age = time.time() - ts
            if age < self._TICKER_CACHE_TTL:
                logger.info(
                    "[PRICING] %s CACHE HIT (key=%s, age=%.0fs, price=%s)",
                    symbol, cache_key, age, ticker.last_price,
                )
                return ticker

        from ctrade.core.config_store import RuntimeConfigStore
        store: RuntimeConfigStore | None = None
        try:
            store = RuntimeConfigStore.get()
        except RuntimeError:
            return None

        def _make_ticker(data: dict) -> Ticker:
            return Ticker(
                pair_symbol=symbol,
                last_price=Decimal(str(data.get("last", 0))),
                bid=Decimal(str(data.get("bid", 0) or 0)),
                ask=Decimal(str(data.get("ask", 0) or 0)),
                high_24h=Decimal(str(data.get("high", 0) or 0)),
                low_24h=Decimal(str(data.get("low", 0) or 0)),
                volume_24h=Decimal(str(data.get("baseVolume", 0) or 0)),
                change_pct_24h=float(data.get("percentage", 0) or 0),
                timestamp=datetime.now(timezone.utc),
            )

        if exchange_id:
            # ----- Exchange-scoped: only try the specified exchange -----
            exchange = await self._create_ccxt_exchange(exchange_id)
            if exchange:
                try:
                    data = await exchange.fetch_ticker(symbol)
                    result = _make_ticker(data)
                    self._ticker_cache[cache_key] = (result, time.time())
                    logger.info(
                        "[PRICING] %s via SCOPED exchange_id=%s → price=%s",
                        symbol, exchange_id, result.last_price,
                    )
                    return result
                except Exception as exc:
                    logger.info(
                        "[PRICING] %s SCOPED exchange_id=%s ccxt FAILED: %s",
                        symbol, exchange_id, exc,
                    )
                finally:
                    await exchange.close()
            else:
                logger.info(
                    "[PRICING] %s SCOPED exchange_id=%s — ccxt exchange creation FAILED",
                    symbol, exchange_id,
                )
        else:
            # ----- Unscoped: iterate ALL active exchanges -----
            exchanges_list = store.list_exchanges()
            if not exchanges_list:
                return None

            for ex_info in exchanges_list:
                if not ex_info.get("is_active", True):
                    continue
                exchange = await self._create_ccxt_exchange(ex_info["id"])
                if not exchange:
                    continue
                try:
                    data = await exchange.fetch_ticker(symbol)
                    result = _make_ticker(data)
                    self._ticker_cache[cache_key] = (result, time.time())
                    logger.info(
                        "[PRICING] %s via UNSCOPED exchange=%s → price=%s",
                        symbol, ex_info.get("name", "?"), result.last_price,
                    )
                    return result
                except Exception:
                    pass  # try next exchange
                finally:
                    await exchange.close()

        # Fallback: try CoinSpot public prices API for AUD pairs
        if symbol.endswith("/AUD"):
            # When exchange-scoped, only use native API if this IS CoinSpot
            should_try_native = True
            if exchange_id:
                entry = store.get_exchange_entry(exchange_id)
                should_try_native = entry is not None and entry.name.lower() == "coinspot"
            if should_try_native:
                ticker = await self._fetch_coinspot_price_native(symbol)
                if ticker:
                    self._ticker_cache[cache_key] = (ticker, time.time())
                    logger.info(
                        "[PRICING] %s via CoinSpot NATIVE fallback → price=%s (AUD)",
                        symbol, ticker.last_price,
                    )
                    return ticker

        logger.info(
            "[PRICING] %s FAILED all sources (exchange_id=%s) — returning None",
            symbol, exchange_id,
        )
        return None

    @staticmethod
    async def _fetch_coinspot_price_native(symbol: str) -> Ticker | None:
        """Fetch price from CoinSpot's public prices API (no auth needed).

        CoinSpot public endpoint returns latest prices for all coins in AUD.
        """
        import aiohttp

        parts = symbol.split("/")
        if len(parts) != 2 or parts[1] != "AUD":
            return None
        base = parts[0].lower()

        url = "https://www.coinspot.com.au/pubapi/v2/latest"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            prices = data.get("prices", {})
            coin_data = prices.get(base)
            if not coin_data:
                return None

            last = Decimal(str(coin_data.get("last", 0)))
            bid = Decimal(str(coin_data.get("bid", 0) or last))
            ask = Decimal(str(coin_data.get("ask", 0) or last))

            return Ticker(
                pair_symbol=symbol,
                last_price=last,
                bid=bid,
                ask=ask,
                high_24h=Decimal("0"),
                low_24h=Decimal("0"),
                volume_24h=Decimal("0"),
                change_pct_24h=0.0,
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.debug("CoinSpot public price API failed: %s", e)
            return None

    async def _try_ccxt_candles(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[Candle] | None:
        """Try to fetch candles from a configured exchange."""
        exchange = await self._create_ccxt_exchange()
        if not exchange:
            return None
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            candles = []
            tf_enum = Timeframe(timeframe) if timeframe in [t.value for t in Timeframe] else Timeframe.H1
            for row in ohlcv:
                candles.append(Candle(
                    time=datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
                    pair_symbol=symbol,
                    timeframe=tf_enum,
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                ))
            return candles
        except Exception as e:
            logger.info("ccxt candle fetch failed for %s: %s — will try Binance public fallback", symbol, e)
            return None
        finally:
            await exchange.close()

    async def _try_binance_public_candles(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[Candle] | None:
        """Try to fetch candles from Binance public spot API (no auth needed).

        Maps any pair (e.g. "BTC/AUD", "ETH/USDT") to the Binance USDT pair
        by extracting the base currency.  This provides real market data for
        exchanges that don't support OHLCV via ccxt (like CoinSpot).

        Note: Prices will be in USDT, not the original quote currency.
        For technical analysis this is acceptable since TA indicators care
        about relative price movement (trends, momentum), not absolute prices.
        """
        import aiohttp

        base = symbol.split("/")[0] if "/" in symbol else symbol
        binance_sym = f"{base}USDT"

        params = {
            "symbol": binance_sym,
            "interval": timeframe,
            "limit": str(limit),
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    _BINANCE_SPOT_KLINES_URL,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.debug(
                            "Binance public klines HTTP %d for %s",
                            resp.status, binance_sym,
                        )
                        return None
                    klines = await resp.json()

            if not klines or not isinstance(klines, list):
                return None

            tf_enum = (
                Timeframe(timeframe)
                if timeframe in [t.value for t in Timeframe]
                else Timeframe.H1
            )

            candles: list[Candle] = []
            for k in klines:
                # Binance kline format:
                # [open_time, open, high, low, close, volume, close_time, ...]
                candles.append(Candle(
                    time=datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                    pair_symbol=symbol,  # Keep original symbol for downstream
                    timeframe=tf_enum,
                    open=Decimal(str(k[1])),
                    high=Decimal(str(k[2])),
                    low=Decimal(str(k[3])),
                    close=Decimal(str(k[4])),
                    volume=Decimal(str(k[5])),
                ))

            logger.info(
                "Binance public klines OK: %s → %s, %d candles, tf=%s",
                symbol, binance_sym, len(candles), timeframe,
            )
            return candles

        except Exception as e:
            logger.debug(
                "Binance public klines failed for %s (%s): %s",
                symbol, binance_sym, e,
            )
            return None

    # ---- Live exchange balance ----

    @staticmethod
    async def _fetch_coinspot_balance_native(
        api_key: str, api_secret: str
    ) -> tuple[dict[str, float], dict[str, float]] | None:
        """Fetch CoinSpot balances using their native REST API.

        CoinSpot's ccxt integration is unreliable (GitHub #8175).
        Their native v2 read-only endpoint works with read-only API keys.

        Returns ``(amounts, aud_values)`` tuple where:
        - ``amounts``: ``{currency: amount}`` (coin quantities)
        - ``aud_values``: ``{currency: aud_balance}`` (CoinSpot's own AUD valuation)

        Returns ``None`` on failure.
        """
        import aiohttp

        url = "https://www.coinspot.com.au/api/v2/ro/my/balances"
        nonce = str(int(time.time() * 1000))
        body = f'{{"nonce":{nonce}}}'
        sign = hmac.new(
            api_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "key": api_key,
            "sign": sign,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, data=body, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "CoinSpot native API returned HTTP %d", resp.status
                        )
                        return None
                    data = await resp.json()

            if data.get("status") != "ok":
                logger.warning("CoinSpot native API error: %s", data.get("message", "?"))
                return None

            balances: dict[str, float] = {}
            aud_values: dict[str, float] = {}
            for coin_entry in data.get("balances", []):
                for currency, info in coin_entry.items():
                    bal = float(info.get("balance", 0))
                    # Skip tiny balances — CoinSpot returns dust for many coins
                    aud_bal = float(info.get("audbalance", 0))
                    if bal > 0 and aud_bal >= 0.01:
                        cur = currency.upper()
                        balances[cur] = bal
                        aud_values[cur] = aud_bal

            logger.info(
                "CoinSpot native API: fetched %d balances (filtered dust), keys: %s",
                len(balances), list(balances.keys())[:15],
            )
            return balances, aud_values
        except Exception as e:
            logger.warning("CoinSpot native API failed: %s", e)
            return None

    async def fetch_exchange_balance(self) -> dict[str, float] | None:
        """Fetch real account balances from ALL configured exchanges.

        Iterates every active exchange, fetches its free balances via ccxt,
        and merges them into a single ``{currency: total_amount}`` dict.
        If the same currency exists on multiple exchanges the amounts are
        summed.  Returns ``None`` only if *no* exchange could be queried.
        """
        from ctrade.core.config_store import RuntimeConfigStore
        try:
            store = RuntimeConfigStore.get()
            exchanges_list = store.list_exchanges()
        except RuntimeError:
            return None

        if not exchanges_list:
            return None

        merged: dict[str, float] = {}
        any_success = False

        logger.info(
            "fetch_exchange_balance: querying %d exchange(s): %s",
            len(exchanges_list),
            [ex.get("name", "?") for ex in exchanges_list],
        )

        for ex_info in exchanges_list:
            ex_name = ex_info.get("name", "?")
            if not ex_info.get("is_active", True):
                logger.info("Skipping inactive exchange: %s", ex_name)
                continue

            ccxt_ok = False
            ccxt_count = 0
            exchange = await self._create_ccxt_exchange(ex_info["id"])
            if exchange:
                try:
                    raw = await exchange.fetch_balance()
                    free: dict[str, Any] = raw.get("free", {})
                    for cur, amt in free.items():
                        if amt and float(amt) > 0:
                            merged[cur] = merged.get(cur, 0.0) + float(amt)
                            ccxt_count += 1
                    logger.info(
                        "ccxt fetch_balance OK for %s: %d non-zero currencies",
                        ex_name, ccxt_count,
                    )
                    any_success = True
                    ccxt_ok = True
                except Exception as e:
                    logger.warning(
                        "ccxt fetch_balance failed for %s: %s",
                        ex_name, e,
                    )
                finally:
                    await exchange.close()
            else:
                logger.warning(
                    "ccxt exchange creation failed for %s (id=%s)",
                    ex_name, ex_info.get("id", "?"),
                )

            # Fallback: CoinSpot native API when ccxt fails OR returns empty
            needs_native = not ccxt_ok or ccxt_count == 0
            if needs_native and ex_name.lower() == "coinspot":
                logger.info("Trying CoinSpot native API for balance...")
                entry = store.get_exchange_entry(ex_info["id"])
                if entry:
                    from ctrade.security.vault import Vault
                    from ctrade.settings import get_settings
                    try:
                        settings = get_settings()
                        key = settings.encryption_key.get_secret_value()
                        vault = Vault(key)
                        api_key = vault.decrypt(entry.api_key_encrypted)
                        api_secret = vault.decrypt(entry.api_secret_encrypted)
                        native_result = await self._fetch_coinspot_balance_native(
                            api_key, api_secret
                        )
                        if native_result:
                            native_bal, _aud_vals = native_result
                            for cur, amt in native_bal.items():
                                merged[cur] = merged.get(cur, 0.0) + amt
                            any_success = True
                            logger.info(
                                "CoinSpot native API OK: %d currencies, total keys: %s",
                                len(native_bal), list(native_bal.keys())[:10],
                            )
                        else:
                            logger.warning("CoinSpot native API returned None")
                    except Exception as e:
                        logger.warning("CoinSpot native fallback failed: %s", e)
                else:
                    logger.warning("CoinSpot entry not found for native fallback")

        logger.info(
            "fetch_exchange_balance result: success=%s, currencies=%s",
            any_success, list(merged.keys()) if merged else "empty",
        )

        return merged if any_success else None

    async def _price_balances(
        self, balances: dict[str, float], exchange_id: str | None = None,
    ) -> dict[str, Any]:
        """Price a set of currency balances and return a portfolio summary.

        Uses a two-pass strategy:
        - Pass 1 (instant): seed-price estimates for all holdings
        - Pass 2 (capped): live ticker lookups for top 10 holdings

        When ``exchange_id`` is provided, ticker lookups are scoped to
        that exchange only (see ``_try_ccxt_ticker``).

        Returns a dict compatible with the ``PortfolioResponse`` schema.
        """
        cash_value = 0.0
        positions_value = 0.0
        non_stable_count = 0

        # ------------------------------------------------------------------
        # Pass 1: Fast valuation using seed prices (no API calls).
        # ------------------------------------------------------------------
        crypto_holdings: list[tuple[str, float, float]] = []
        for currency, amount in balances.items():
            if currency in _CASH_CURRENCIES:
                rate = _FIAT_TO_USD.get(currency, 1.0)
                cash_value += amount * rate
            else:
                seed_price = _SEED_PRICES.get(
                    f"{currency}/USDT",
                    _SEED_PRICES.get(
                        f"{currency}/USD",
                        _SEED_PRICES.get(f"{currency}/AUD", 0) * _FIAT_TO_USD.get("AUD", 0.65),
                    ),
                )
                est_usd = amount * seed_price if seed_price > 0 else 0.0
                if est_usd >= 0.01:
                    crypto_holdings.append((currency, amount, est_usd))

        crypto_holdings.sort(key=lambda x: x[2], reverse=True)

        # ------------------------------------------------------------------
        # Pass 2: Live prices for top holdings only.
        # ------------------------------------------------------------------
        _MAX_LIVE_LOOKUPS = 10

        logger.info(
            "[PORTFOLIO] _price_balances called: exchange_id=%s, %d crypto holdings, cash=$%.2f",
            exchange_id, len(crypto_holdings), cash_value,
        )

        for i, (currency, amount, est_usd) in enumerate(crypto_holdings):
            usd_value = est_usd
            price_source = "seed"
            if i < _MAX_LIVE_LOOKUPS:
                try:
                    ticker = await self._try_ccxt_ticker(f"{currency}/USDT", exchange_id)
                    if ticker is None:
                        ticker = await self._try_ccxt_ticker(f"{currency}/USD", exchange_id)
                    if ticker is None:
                        ticker = await self._try_ccxt_ticker(f"{currency}/AUD", exchange_id)
                    if ticker is not None:
                        price = float(ticker.last_price)
                        price_source = f"live:{ticker.pair_symbol}"
                        if ticker.pair_symbol.endswith("/AUD"):
                            price *= _FIAT_TO_USD.get("AUD", 0.65)
                            price_source += f"×AUD({_FIAT_TO_USD.get('AUD', 0.65)})"
                        usd_value = amount * price
                except Exception:
                    pass
            else:
                price_source = "seed(over-limit)"

            logger.info(
                "[PORTFOLIO]   %s: amount=%.8f, usd=$%.2f, source=%s (exchange_id=%s)",
                currency, amount, usd_value, price_source, exchange_id,
            )

            if usd_value >= 0.01:
                positions_value += usd_value
                non_stable_count += 1

        total_value = cash_value + positions_value
        logger.info(
            "[PORTFOLIO] _price_balances result: total=$%.2f (cash=$%.2f + positions=$%.2f), exchange_id=%s",
            total_value, cash_value, positions_value, exchange_id,
        )

        cash_bal_usd: dict[str, float] = {}
        for currency, amount in balances.items():
            if currency in _CASH_CURRENCIES:
                rate = _FIAT_TO_USD.get(currency, 1.0)
                cash_bal_usd[currency] = round(amount * rate, 2)

        return {
            "cash_balance": cash_bal_usd,
            "total_value_usd": round(total_value, 2),
            "positions_value": round(positions_value, 2),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "daily_pnl": 0.0,
            "open_positions": non_stable_count,
            "closed_positions": 0,
            "total_orders": 0,
        }

    async def fetch_exchange_portfolio(self) -> dict[str, Any] | None:
        """Build a portfolio summary from real exchange balances.

        Delegates to ``fetch_per_exchange_portfolios()`` and aggregates,
        ensuring the total always matches the sum of per-exchange values
        (and the portfolio-history chart).
        """
        per_exchange = await self.fetch_per_exchange_portfolios()
        if not per_exchange:
            logger.warning("fetch_exchange_portfolio: no exchange data returned")
            return None

        # Aggregate across all exchanges
        total_value = 0.0
        total_positions = 0.0
        total_open = 0
        merged_cash: dict[str, float] = {}

        for ex_name, portfolio in per_exchange.items():
            total_value += portfolio["total_value_usd"]
            total_positions += portfolio["positions_value"]
            total_open += portfolio["open_positions"]
            for cur, val in portfolio["cash_balance"].items():
                merged_cash[cur] = merged_cash.get(cur, 0.0) + val

        result = {
            "cash_balance": {k: round(v, 2) for k, v in merged_cash.items()},
            "total_value_usd": round(total_value, 2),
            "positions_value": round(total_positions, 2),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "daily_pnl": 0.0,
            "open_positions": total_open,
            "closed_positions": 0,
            "total_orders": 0,
        }

        logger.info(
            "fetch_exchange_portfolio: total=$%.2f (cash=$%.2f + positions=$%.2f), %d exchanges",
            result["total_value_usd"],
            sum(merged_cash.values()),
            result["positions_value"],
            len(per_exchange),
        )

        return result

    async def fetch_per_exchange_portfolios(self) -> dict[str, dict[str, Any]]:
        """Fetch portfolio for each exchange separately (for snapshots).

        Returns ``{exchange_name: portfolio_dict}`` where each portfolio_dict
        has the same shape as ``fetch_exchange_portfolio()`` output.

        Unlike ``fetch_exchange_balance()`` which merges all exchanges,
        this keeps balances separate so we can snapshot each exchange
        independently.
        """
        from ctrade.core.config_store import RuntimeConfigStore
        try:
            store = RuntimeConfigStore.get()
            exchanges_list = store.list_exchanges()
        except RuntimeError:
            return {}

        if not exchanges_list:
            return {}

        results: dict[str, dict[str, Any]] = {}

        for ex_info in exchanges_list:
            ex_name = ex_info.get("name", "?")
            if not ex_info.get("is_active", True):
                continue

            # Collect balances for this single exchange
            balances: dict[str, float] = {}
            ccxt_ok = False
            ccxt_count = 0

            exchange = await self._create_ccxt_exchange(ex_info["id"])
            if exchange:
                try:
                    raw = await exchange.fetch_balance()
                    free: dict[str, Any] = raw.get("free", {})
                    for cur, amt in free.items():
                        if amt and float(amt) > 0:
                            balances[cur] = balances.get(cur, 0.0) + float(amt)
                            ccxt_count += 1
                    ccxt_ok = True
                except Exception as e:
                    logger.warning(
                        "ccxt fetch_balance failed for %s: %s", ex_name, e,
                    )
                finally:
                    await exchange.close()

            # CoinSpot native API fallback
            coinspot_aud_values: dict[str, float] | None = None
            needs_native = not ccxt_ok or ccxt_count == 0
            if needs_native and ex_name.lower() == "coinspot":
                entry = store.get_exchange_entry(ex_info["id"])
                if entry:
                    from ctrade.security.vault import Vault
                    from ctrade.settings import get_settings
                    try:
                        settings = get_settings()
                        key = settings.encryption_key.get_secret_value()
                        vault = Vault(key)
                        api_key = vault.decrypt(entry.api_key_encrypted)
                        api_secret = vault.decrypt(entry.api_secret_encrypted)
                        native_result = await self._fetch_coinspot_balance_native(
                            api_key, api_secret,
                        )
                        if native_result:
                            native_bal, coinspot_aud_values = native_result
                            for cur, amt in native_bal.items():
                                balances[cur] = balances.get(cur, 0.0) + amt
                    except Exception as e:
                        logger.warning("CoinSpot native fallback failed: %s", e)

            if balances:
                # For CoinSpot: use the exchange's own AUD valuations directly
                # instead of re-pricing each coin via _price_balances (which
                # can fail for coins ccxt doesn't recognise and fall back to
                # stale seed prices).
                if coinspot_aud_values:
                    aud_to_usd = _FIAT_TO_USD.get("AUD", 0.65)
                    total_aud = sum(coinspot_aud_values.values())
                    total_usd = total_aud * aud_to_usd
                    non_stable = len(coinspot_aud_values)

                    # Build per-coin log for diagnostics
                    for cur, aud_val in sorted(
                        coinspot_aud_values.items(),
                        key=lambda x: x[1],
                        reverse=True,
                    ):
                        usd_val = aud_val * aud_to_usd
                        logger.info(
                            "[PORTFOLIO]   %s: amount=%.8f, aud=$%.2f, usd=$%.2f, "
                            "source=coinspot-native (exchange=%s)",
                            cur,
                            balances.get(cur, 0.0),
                            aud_val,
                            usd_val,
                            ex_name,
                        )

                    portfolio: dict[str, Any] = {
                        "cash_balance": {},
                        "total_value_usd": round(total_usd, 2),
                        "positions_value": round(total_usd, 2),
                        "unrealized_pnl": 0.0,
                        "realized_pnl": 0.0,
                        "daily_pnl": 0.0,
                        "open_positions": non_stable,
                        "closed_positions": 0,
                        "total_orders": 0,
                    }
                    logger.info(
                        "[PORTFOLIO] CoinSpot native totals: AUD=$%.2f × %.4f = USD=$%.2f (%d coins)",
                        total_aud, aud_to_usd, total_usd, non_stable,
                    )
                else:
                    ex_id_str = str(ex_info["id"])
                    logger.info(
                        "[PORTFOLIO] Pricing %s (exchange_id=%s) with %d balances: %s",
                        ex_name, ex_id_str, len(balances), list(balances.keys()),
                    )
                    portfolio = await self._price_balances(balances, exchange_id=ex_id_str)

                results[ex_name] = portfolio
                logger.info(
                    "Per-exchange portfolio for %s: $%.2f",
                    ex_name, portfolio["total_value_usd"],
                )

        return results

    def _simulated_ticker(self, symbol: str) -> Ticker:
        """Generate a simulated ticker with realistic price movement."""
        with self._data_lock:
            base_price = self._sim_prices.get(symbol)
            if base_price is None:
                base_price = _SEED_PRICES.get(symbol)
            if base_price is None:
                base_coin = symbol.split("/")[0] if "/" in symbol else symbol
                base_price = 1.0 if base_coin in _CASH_CURRENCIES else 100.0
            # Random walk: ±0.3% per tick
            change_pct = self._sim_rng.gauss(0, 0.003)
            new_price = base_price * (1 + change_pct)
            self._sim_prices[symbol] = new_price

            spread = new_price * 0.0005  # 0.05% spread
            return Ticker(
                pair_symbol=symbol,
                last_price=Decimal(str(round(new_price, 8))),
                bid=Decimal(str(round(new_price - spread, 8))),
                ask=Decimal(str(round(new_price + spread, 8))),
                high_24h=Decimal(str(round(new_price * 1.02, 8))),
                low_24h=Decimal(str(round(new_price * 0.98, 8))),
                volume_24h=Decimal(str(round(self._sim_rng.uniform(1000, 50000), 2))),
                change_pct_24h=round(change_pct * 100, 4),
                timestamp=datetime.now(timezone.utc),
            )

    def _simulated_candles(
        self, symbol: str, timeframe: str, limit: int
    ) -> list[Candle]:
        """Generate simulated candle history with deterministic random walk."""
        minutes = _TIMEFRAME_MINUTES.get(timeframe, 60)
        tf_enum = Timeframe(timeframe) if timeframe in [t.value for t in Timeframe] else Timeframe.H1
        base = _SEED_PRICES.get(symbol)
        if base is None:
            base_coin = symbol.split("/")[0] if "/" in symbol else symbol
            base = 1.0 if base_coin in _CASH_CURRENCIES else 100.0

        # Use symbol+timeframe as seed for reproducibility
        seed = int(hashlib.md5(f"{symbol}:{timeframe}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        price = base * 0.95  # Start slightly below seed

        for i in range(limit):
            t = now - timedelta(minutes=minutes * (limit - i))
            # Trend + noise
            trend = math.sin(i / 20) * 0.008
            noise = rng.gauss(0, 0.02)
            change = trend + noise

            open_price = price
            close_price = price * (1 + change)
            high = max(open_price, close_price) * (1 + abs(rng.gauss(0, 0.008)))
            low = min(open_price, close_price) * (1 - abs(rng.gauss(0, 0.008)))
            volume = rng.uniform(100, 5000)

            candles.append(Candle(
                time=t,
                pair_symbol=symbol,
                timeframe=tf_enum,
                open=Decimal(str(round(open_price, 8))),
                high=Decimal(str(round(high, 8))),
                low=Decimal(str(round(low, 8))),
                close=Decimal(str(round(close_price, 8))),
                volume=Decimal(str(round(volume, 2))),
            ))
            price = close_price

        return candles

    def get_current_price(self, symbol: str) -> float:
        """Get current price for paper engine P&L calculations.

        Priority: ticker cache (real exchange data) → sim prices → seed
        prices → stablecoin detection → 100.0 fallback.
        """
        with self._data_lock:
            # 1. Check ticker cache first (real exchange prices from async fetches)
            cached = self._ticker_cache.get(symbol)
            if cached:
                ticker, _ts = cached
                return float(ticker.last_price)

            # 2. Check sim prices / seed prices
            base = self._sim_prices.get(symbol) or _SEED_PRICES.get(symbol)
            if base is None:
                # 3. Stablecoin pairs (USDC/USDT, DAI/USDT, etc.) → ~1.0
                base_coin = symbol.split("/")[0] if "/" in symbol else symbol
                base = 1.0 if base_coin in _CASH_CURRENCIES else 100.0

            change = self._sim_rng.gauss(0, 0.005)
            new_price = base * (1 + change)
            self._sim_prices[symbol] = new_price
            return round(new_price, 8)
