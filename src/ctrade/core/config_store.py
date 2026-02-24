"""Runtime configuration store with JSON file persistence.

Holds mutable copies of trading, risk, and strategy settings that can be
updated at runtime via the API.  Initialised from Pydantic AppSettings on
startup; persisted state is restored from ``config/runtime_state.json`` if
it exists, so changes survive server restarts.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from ctrade.security.vault import Vault
from ctrade.settings import AppSettings

logger = logging.getLogger(__name__)

# Path to the persisted state file (project_root/config/runtime_state.json).
# In Docker (non-editable install), __file__ is in site-packages so the
# parents[3] trick won't reach /app.  Use CTRADE_CONFIG_DIR when set.
_config_env = os.environ.get("CTRADE_CONFIG_DIR")
_CONFIG_DIR = Path(_config_env) if _config_env else Path(__file__).resolve().parents[3] / "config"
_STATE_FILE = _CONFIG_DIR / "runtime_state.json"


@dataclass
class ExchangeEntry:
    """An exchange connection stored in memory."""

    id: str
    name: str
    exchange_type: str
    api_key_encrypted: bytes
    api_secret_encrypted: bytes
    passphrase_encrypted: bytes | None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_public_dict(self) -> dict[str, Any]:
        """Return a dict safe to expose via the API (no credentials)."""
        return {
            "id": self.id,
            "name": self.name,
            "exchange_type": self.exchange_type,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
        }


class RuntimeConfigStore:
    """Singleton store for mutable runtime configuration with disk persistence."""

    _instance: ClassVar[RuntimeConfigStore | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, settings: AppSettings) -> None:
        # Start with defaults from settings
        self._trading: dict[str, Any] = {
            "mode": settings.trading.mode,
            "default_quote_currency": settings.trading.default_quote_currency,
            "max_open_positions": settings.trading.max_open_positions,
            "max_order_usdt": settings.trading.max_order_usdt,
            "order_timeout_seconds": settings.trading.order_timeout_seconds,
        }
        self._strategy: dict[str, Any] = {
            "active_strategy": settings.strategy.active_strategy,
            "technical_weight": settings.strategy.technical_weight,
            "sentiment_weight": settings.strategy.sentiment_weight,
            "onchain_weight": settings.strategy.onchain_weight,
            "derivatives_weight": settings.strategy.derivatives_weight,
            "market_sentiment_weight": settings.strategy.market_sentiment_weight,
            "cvd_weight": settings.strategy.cvd_weight,
            "social_velocity_weight": settings.strategy.social_velocity_weight,
            "strategy_mode": settings.strategy.strategy_mode,
            "short_min_1h_change_pct": settings.strategy.short_min_1h_change_pct,
            "entry_confidence_threshold": settings.strategy.entry_confidence_threshold,
            "exit_confidence_threshold": settings.strategy.exit_confidence_threshold,
        }
        self._risk: dict[str, Any] = {
            "max_position_pct": settings.risk.max_position_pct,
            "max_daily_loss_pct": settings.risk.max_daily_loss_pct,
            "max_drawdown_pct": settings.risk.max_drawdown_pct,
            "default_stop_loss_pct": settings.risk.default_stop_loss_pct,
            "default_take_profit_pct": settings.risk.default_take_profit_pct,
        }
        self._exchanges: list[ExchangeEntry] = []
        self._feed_credentials: dict[str, dict[str, bytes]] = {}
        self._data_lock = threading.Lock()

        # Restore persisted state (overlays on top of defaults)
        self._load_from_disk()

    # ---- Singleton lifecycle ----

    @classmethod
    def initialize(cls, settings: AppSettings) -> RuntimeConfigStore:
        """Create the singleton instance from application settings."""
        with cls._lock:
            cls._instance = cls(settings)
            return cls._instance

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the store has been initialized."""
        return cls._instance is not None

    @classmethod
    def get(cls) -> RuntimeConfigStore:
        """Return the singleton instance.  Raises if not initialized."""
        if cls._instance is None:
            raise RuntimeError("RuntimeConfigStore not initialized. Call initialize() first.")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    # ---- Persistence ----

    def _save_to_disk(self) -> None:
        """Persist current state to JSON file.  Never raises — logs errors."""
        try:
            exchanges_data = []
            for ex in self._exchanges:
                ex_dict: dict[str, Any] = {
                    "id": ex.id,
                    "name": ex.name,
                    "exchange_type": ex.exchange_type,
                    "api_key_encrypted": base64.b64encode(ex.api_key_encrypted).decode(),
                    "api_secret_encrypted": base64.b64encode(ex.api_secret_encrypted).decode(),
                    "passphrase_encrypted": (
                        base64.b64encode(ex.passphrase_encrypted).decode()
                        if ex.passphrase_encrypted
                        else None
                    ),
                    "is_active": ex.is_active,
                    "created_at": ex.created_at.isoformat(),
                }
                exchanges_data.append(ex_dict)

            feed_creds_data: dict[str, dict[str, str]] = {}
            for conn_name, fields in self._feed_credentials.items():
                feed_creds_data[conn_name] = {
                    k: base64.b64encode(v).decode() for k, v in fields.items()
                }

            state = {
                "trading": dict(self._trading),
                "strategy": dict(self._strategy),
                "risk": dict(self._risk),
                "exchanges": exchanges_data,
                "feed_credentials": feed_creds_data,
            }

            # Ensure config directory exists
            _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write: write to temp file, then rename
            tmp_path = _STATE_FILE.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

            # On Windows, os.replace is atomic within the same volume
            os.replace(str(tmp_path), str(_STATE_FILE))
            logger.debug("Config state persisted to %s", _STATE_FILE)

        except Exception:
            logger.exception("Failed to persist config state to disk")

    def _load_from_disk(self) -> None:
        """Restore state from JSON file if it exists.  Never raises."""
        try:
            if not _STATE_FILE.exists():
                logger.debug("No persisted config state found at %s", _STATE_FILE)
                return

            raw = _STATE_FILE.read_text(encoding="utf-8")
            state = json.loads(raw)

            # Overlay trading, strategy, risk settings
            if "trading" in state and isinstance(state["trading"], dict):
                self._trading.update(state["trading"])

            if "strategy" in state and isinstance(state["strategy"], dict):
                self._strategy.update(state["strategy"])

                # Migration: ensure all weight keys exist and weights sum to 1.0
                _WEIGHT_KEYS = [
                    "technical_weight", "sentiment_weight", "onchain_weight",
                    "derivatives_weight", "market_sentiment_weight",
                    "cvd_weight", "social_velocity_weight",
                ]
                missing_keys = [k for k in _WEIGHT_KEYS if k not in state["strategy"]]
                if missing_keys:
                    # Old config is missing new weight(s).  Scale existing weights
                    # down proportionally to make room for the defaults.
                    _DEFAULT_WEIGHTS = {
                        "technical_weight": 0.30,
                        "sentiment_weight": 0.10,
                        "onchain_weight": 0.08,
                        "derivatives_weight": 0.17,
                        "market_sentiment_weight": 0.17,
                        "cvd_weight": 0.10,
                        "social_velocity_weight": 0.08,
                    }
                    # Sum of new default weights for the missing keys
                    new_weight_total = sum(_DEFAULT_WEIGHTS[k] for k in missing_keys)
                    remaining = 1.0 - new_weight_total
                    # Sum of existing weights
                    existing_keys = [k for k in _WEIGHT_KEYS if k not in missing_keys]
                    old_total = sum(self._strategy.get(k, 0) for k in existing_keys)
                    if old_total > 0 and remaining > 0:
                        scale = remaining / old_total
                        for k in existing_keys:
                            self._strategy[k] = round(self._strategy.get(k, 0) * scale, 4)
                    # Insert new weights with defaults
                    for k in missing_keys:
                        self._strategy[k] = _DEFAULT_WEIGHTS[k]
                    logger.info(
                        "Migrated strategy weights: added %s",
                        ", ".join(f"{k}={_DEFAULT_WEIGHTS[k]}" for k in missing_keys),
                    )

            if "risk" in state and isinstance(state["risk"], dict):
                self._risk.update(state["risk"])

            # Restore exchanges (per-exchange error handling so one bad
            # entry doesn't prevent loading the rest)
            if "exchanges" in state and isinstance(state["exchanges"], list):
                restored: list[ExchangeEntry] = []
                for i, ex_data in enumerate(state["exchanges"]):
                    try:
                        passphrase_enc = ex_data.get("passphrase_encrypted")
                        entry = ExchangeEntry(
                            id=ex_data["id"],
                            name=ex_data["name"],
                            exchange_type=ex_data["exchange_type"],
                            api_key_encrypted=base64.b64decode(ex_data["api_key_encrypted"]),
                            api_secret_encrypted=base64.b64decode(ex_data["api_secret_encrypted"]),
                            passphrase_encrypted=(
                                base64.b64decode(passphrase_enc) if passphrase_enc else None
                            ),
                            is_active=ex_data.get("is_active", True),
                            created_at=datetime.fromisoformat(ex_data["created_at"]),
                        )
                        restored.append(entry)
                    except Exception:
                        logger.exception("Failed to restore exchange entry %d — skipping", i)
                self._exchanges = restored

            # Restore feed credentials
            if "feed_credentials" in state and isinstance(state["feed_credentials"], dict):
                restored_creds: dict[str, dict[str, bytes]] = {}
                for conn_name, fields in state["feed_credentials"].items():
                    try:
                        restored_creds[conn_name] = {
                            k: base64.b64decode(v) for k, v in fields.items()
                        }
                    except Exception:
                        logger.exception(
                            "Failed to restore feed credentials for %s — skipping",
                            conn_name,
                        )
                self._feed_credentials = restored_creds

            logger.info(
                "Restored config state from disk (%d exchanges, %d feed credentials)",
                len(self._exchanges),
                len(self._feed_credentials),
            )

        except Exception:
            logger.exception("Failed to load config state from disk — using defaults")

    # ---- Trading config ----

    def get_trading(self) -> dict[str, Any]:
        with self._data_lock:
            return dict(self._trading)

    def update_trading(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._data_lock:
            self._trading.update(updates)
            result = dict(self._trading)
        self._save_to_disk()
        return result

    # ---- Strategy config ----

    def get_strategy(self) -> dict[str, Any]:
        with self._data_lock:
            return dict(self._strategy)

    def update_strategy(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._data_lock:
            merged = {**self._strategy, **updates}
            # Validate weights sum to 1.0
            weights = (
                merged.get("technical_weight", 0)
                + merged.get("sentiment_weight", 0)
                + merged.get("onchain_weight", 0)
                + merged.get("derivatives_weight", 0)
                + merged.get("market_sentiment_weight", 0)
                + merged.get("cvd_weight", 0)
                + merged.get("social_velocity_weight", 0)
            )
            if abs(weights - 1.0) > 0.001:
                raise ValueError(
                    f"Strategy weights must sum to 1.0, got {weights:.3f}"
                )
            self._strategy.update(updates)
            result = dict(self._strategy)
        self._save_to_disk()
        return result

    # ---- Risk config ----

    def get_risk(self) -> dict[str, Any]:
        with self._data_lock:
            return dict(self._risk)

    def update_risk(self, updates: dict[str, Any]) -> dict[str, Any]:
        with self._data_lock:
            self._risk.update(updates)
            result = dict(self._risk)
        self._save_to_disk()
        return result

    # ---- Feed credential management ----

    def get_feed_credential(self, connection_name: str, field_key: str) -> bytes | None:
        """Get an encrypted credential for a connection field."""
        with self._data_lock:
            conn = self._feed_credentials.get(connection_name)
            if conn is None:
                return None
            return conn.get(field_key)

    def set_feed_credentials(
        self,
        connection_name: str,
        credentials: dict[str, str],
        vault: Vault,
    ) -> None:
        """Encrypt and store credentials for a connection.

        Args:
            connection_name: The connection name (e.g. "CoinMarketCap").
            credentials: Plaintext credential key-value pairs to encrypt.
            vault: Vault instance for encryption.
        """
        with self._data_lock:
            encrypted: dict[str, bytes] = {}
            for key, value in credentials.items():
                if value:  # skip empty values
                    encrypted[key] = vault.encrypt(value)
            if encrypted:
                self._feed_credentials[connection_name] = encrypted
        self._save_to_disk()

    def get_feed_credential_decrypted(
        self,
        connection_name: str,
        field_key: str,
        vault: Vault,
    ) -> str | None:
        """Decrypt and return a feed credential value."""
        enc = self.get_feed_credential(connection_name, field_key)
        if enc is None:
            return None
        return vault.decrypt(enc)

    # ---- Exchange management ----

    def list_exchanges(self) -> list[dict[str, Any]]:
        with self._data_lock:
            return [ex.to_public_dict() for ex in self._exchanges]

    def add_exchange(
        self,
        name: str,
        exchange_type: str,
        api_key: str,
        api_secret: str,
        vault: Vault,
        passphrase: str | None = None,
    ) -> dict[str, Any]:
        entry = ExchangeEntry(
            id=str(uuid.uuid4()),
            name=name,
            exchange_type=exchange_type,
            api_key_encrypted=vault.encrypt(api_key),
            api_secret_encrypted=vault.encrypt(api_secret),
            passphrase_encrypted=vault.encrypt(passphrase) if passphrase else None,
        )
        with self._data_lock:
            self._exchanges.append(entry)
            result = entry.to_public_dict()
        self._save_to_disk()
        return result

    def update_exchange(
        self,
        exchange_id: str,
        vault: Vault,
        api_key: str | None = None,
        api_secret: str | None = None,
        passphrase: str | None = None,
    ) -> dict[str, Any] | None:
        """Update credentials for an existing exchange.

        Only non-None, non-empty fields are re-encrypted and updated.
        Returns the public dict on success, or None if not found.
        """
        with self._data_lock:
            entry = next((e for e in self._exchanges if e.id == exchange_id), None)
            if entry is None:
                return None
            if api_key:
                entry.api_key_encrypted = vault.encrypt(api_key)
            if api_secret:
                entry.api_secret_encrypted = vault.encrypt(api_secret)
            if passphrase is not None:
                # Allow clearing passphrase with empty string
                entry.passphrase_encrypted = vault.encrypt(passphrase) if passphrase else None
            result = entry.to_public_dict()
        self._save_to_disk()
        return result

    def get_exchange_entry(self, exchange_id: str) -> ExchangeEntry | None:
        with self._data_lock:
            for ex in self._exchanges:
                if ex.id == exchange_id:
                    return ex
            return None

    def remove_exchange(self, exchange_id: str) -> bool:
        with self._data_lock:
            before = len(self._exchanges)
            self._exchanges = [ex for ex in self._exchanges if ex.id != exchange_id]
            removed = len(self._exchanges) < before
        if removed:
            self._save_to_disk()
        return removed
