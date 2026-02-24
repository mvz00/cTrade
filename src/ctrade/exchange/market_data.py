"""Market data provider — fetches prices from ccxt or generates simulated data.

When no exchange is configured, provides realistic simulated market data
so the app works out of the box without API keys.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, ClassVar

from ctrade.core.enums import Timeframe
from ctrade.core.models import Candle, Ticker

logger = logging.getLogger(__name__)

# Seed prices for simulated pairs
_SEED_PRICES: dict[str, float] = {
    "BTC/USDT": 67000.0,
    "ETH/USDT": 3500.0,
    "SOL/USDT": 145.0,
    "BNB/USDT": 580.0,
    "XRP/USDT": 0.62,
    "ADA/USDT": 0.45,
    "DOGE/USDT": 0.082,
    "DOT/USDT": 7.20,
    "AVAX/USDT": 35.0,
    "LINK/USDT": 14.50,
}

_TIMEFRAME_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440, "1w": 10080,
}


class MarketDataProvider:
    """Provides market data from ccxt exchanges or simulated fallback."""

    _instance: ClassVar[MarketDataProvider | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self) -> None:
        self._sim_prices: dict[str, float] = dict(_SEED_PRICES)
        self._sim_rng = random.Random(42)
        self._data_lock = threading.Lock()
        self._cached_exchange_pairs: list[str] | None = None

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
        """Return available trading pairs from the configured exchange.

        Fetches all USDT-quoted spot pairs via ``load_markets()`` on first
        call and caches the result.  Falls back to the simulated seed list
        when no exchange is configured.
        """
        # Return cache if available
        if self._cached_exchange_pairs is not None:
            return self._cached_exchange_pairs

        exchange = await self._create_ccxt_exchange()
        if not exchange:
            return list(_SEED_PRICES.keys())

        try:
            markets = await exchange.load_markets()
            pairs: list[str] = sorted(
                symbol
                for symbol, info in markets.items()
                if (
                    info.get("quote") == "USDT"
                    and info.get("active", True)
                    and info.get("spot", True)
                )
            )
            if pairs:
                self._cached_exchange_pairs = pairs
                logger.info("Loaded %d USDT pairs from exchange", len(pairs))
                return pairs
            # Exchange returned no matching pairs — fall back
            return list(_SEED_PRICES.keys())
        except Exception as e:
            logger.debug("Failed to load exchange markets: %s", e)
            return list(_SEED_PRICES.keys())
        finally:
            await exchange.close()

    def clear_pairs_cache(self) -> None:
        """Clear the cached exchange pairs (e.g. after exchange config change)."""
        self._cached_exchange_pairs = None

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
        """Get OHLCV candles for a symbol."""
        candles = await self._try_ccxt_candles(symbol, timeframe, limit)
        if candles:
            return candles
        return self._simulated_candles(symbol, timeframe, limit)

    async def _create_ccxt_exchange(self) -> Any | None:
        """Create an async ccxt exchange instance from the first configured exchange.

        Returns the exchange object (caller must call ``await exchange.close()``),
        or ``None`` if no exchange is configured.
        """
        try:
            from ctrade.core.config_store import RuntimeConfigStore
            store = RuntimeConfigStore.get()
            exchanges = store.list_exchanges()
            if not exchanges:
                return None

            from ctrade.security.vault import Vault
            from ctrade.settings import get_settings
            settings = get_settings()
            key = settings.encryption_key.get_secret_value()
            if not key:
                return None
            vault = Vault(key)

            entry = store.get_exchange_entry(exchanges[0]["id"])
            if not entry:
                return None

            import ccxt.async_support as ccxt_async
            exchange_class = getattr(ccxt_async, entry.name, None)
            if not exchange_class:
                return None

            api_key = vault.decrypt(entry.api_key_encrypted)
            api_secret = vault.decrypt(entry.api_secret_encrypted)
            config: dict[str, Any] = {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
            }
            if entry.passphrase_encrypted:
                config["password"] = vault.decrypt(entry.passphrase_encrypted)

            return exchange_class(config)
        except Exception as e:
            logger.debug("Failed to create ccxt exchange: %s", e)
            return None

    async def _try_ccxt_ticker(self, symbol: str) -> Ticker | None:
        """Try to fetch ticker from a configured exchange."""
        exchange = await self._create_ccxt_exchange()
        if not exchange:
            return None
        try:
            data = await exchange.fetch_ticker(symbol)
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
        except Exception as e:
            logger.debug("ccxt ticker fetch failed for %s: %s", symbol, e)
            return None
        finally:
            await exchange.close()

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
            logger.debug("ccxt candle fetch failed for %s: %s", symbol, e)
            return None
        finally:
            await exchange.close()

    # ---- Live exchange balance ----

    async def fetch_exchange_balance(self) -> dict[str, float] | None:
        """Fetch real account balances from the configured exchange.

        Returns ``{currency: free_amount}`` for non-zero balances,
        or ``None`` if no exchange is configured or the fetch fails.
        """
        exchange = await self._create_ccxt_exchange()
        if not exchange:
            return None
        try:
            raw = await exchange.fetch_balance()
            # raw["free"] is {currency: amount} — filter out zero balances
            free: dict[str, Any] = raw.get("free", {})
            return {
                cur: float(amt)
                for cur, amt in free.items()
                if amt and float(amt) > 0
            }
        except Exception as e:
            logger.warning("Failed to fetch exchange balance: %s", e)
            return None
        finally:
            await exchange.close()

    async def fetch_exchange_portfolio(self) -> dict[str, Any] | None:
        """Build a portfolio summary from real exchange balances.

        Returns a dict compatible with the ``PortfolioResponse`` schema,
        or ``None`` if the balance fetch fails.

        Uses only real exchange tickers for pricing (never simulated fallback)
        to avoid inflating dust balances with fake prices.
        """
        balances = await self.fetch_exchange_balance()
        if balances is None:
            return None

        # Stablecoins and fiat treated as USD-equivalent
        _CASH_CURRENCIES = {
            "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD",  # stablecoins
            "USD", "EUR", "GBP", "AUD", "CAD", "JPY", "CHF",  # fiat
        }
        # Fiat → approximate USD conversion (good enough for portfolio display)
        _FIAT_TO_USD: dict[str, float] = {
            "USD": 1.0, "EUR": 1.08, "GBP": 1.27, "AUD": 0.65,
            "CAD": 0.74, "JPY": 0.0067, "CHF": 1.13,
        }

        cash_value = 0.0
        positions_value = 0.0
        non_stable_count = 0

        for currency, amount in balances.items():
            if currency in _CASH_CURRENCIES:
                # Stablecoins count as $1, fiat uses approximate rate
                rate = _FIAT_TO_USD.get(currency, 1.0)
                cash_value += amount * rate
            else:
                # Convert to USD using REAL exchange ticker only
                # (never fall back to simulated prices for portfolio valuation)
                symbol = f"{currency}/USDT"
                try:
                    ticker = await self._try_ccxt_ticker(symbol)
                    if ticker is None:
                        # Try with /USD pair (common on Kraken)
                        ticker = await self._try_ccxt_ticker(f"{currency}/USD")
                    if ticker is None:
                        logger.debug(
                            "No real ticker for %s (amount=%.8f), skipping",
                            currency, amount,
                        )
                        continue
                    usd_value = amount * float(ticker.last_price)
                    # Skip dust (< $0.01)
                    if usd_value < 0.01:
                        continue
                    positions_value += usd_value
                    non_stable_count += 1
                except Exception:
                    logger.debug("Could not price %s, skipping", symbol)

        total_value = cash_value + positions_value

        return {
            "cash_balance": balances,
            "total_value_usd": round(total_value, 2),
            "positions_value": round(positions_value, 2),
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "daily_pnl": 0.0,
            "open_positions": non_stable_count,
            "closed_positions": 0,
            "total_orders": 0,
        }

    def _simulated_ticker(self, symbol: str) -> Ticker:
        """Generate a simulated ticker with realistic price movement."""
        with self._data_lock:
            base_price = self._sim_prices.get(symbol, 100.0)
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
        base = _SEED_PRICES.get(symbol, 100.0)

        # Use symbol+timeframe as seed for reproducibility
        seed = int(hashlib.md5(f"{symbol}:{timeframe}".encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)

        now = datetime.now(timezone.utc)
        candles: list[Candle] = []
        price = base * 0.95  # Start slightly below seed

        for i in range(limit):
            t = now - timedelta(minutes=minutes * (limit - i))
            # Trend + noise
            trend = math.sin(i / 20) * 0.002
            noise = rng.gauss(0, 0.005)
            change = trend + noise

            open_price = price
            close_price = price * (1 + change)
            high = max(open_price, close_price) * (1 + abs(rng.gauss(0, 0.002)))
            low = min(open_price, close_price) * (1 - abs(rng.gauss(0, 0.002)))
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
        """Get current simulated price synchronously (for paper engine)."""
        with self._data_lock:
            base = self._sim_prices.get(symbol, _SEED_PRICES.get(symbol, 100.0))
            change = self._sim_rng.gauss(0, 0.005)
            new_price = base * (1 + change)
            self._sim_prices[symbol] = new_price
            return round(new_price, 8)
