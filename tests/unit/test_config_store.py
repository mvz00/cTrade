"""Tests for RuntimeConfigStore."""

import pytest

from ctrade.core.config_store import RuntimeConfigStore
from ctrade.security.vault import Vault


class TestConfigStoreTrading:
    def test_get_trading_defaults(self):
        store = RuntimeConfigStore.get()
        trading = store.get_trading()
        assert trading["mode"] == "paper"
        assert trading["default_quote_currency"] == "USDT"

    def test_update_trading_mode(self):
        store = RuntimeConfigStore.get()
        updated = store.update_trading({"mode": "live"})
        assert updated["mode"] == "live"
        # Verify persists on re-read
        assert store.get_trading()["mode"] == "live"

    def test_update_trading_partial(self):
        store = RuntimeConfigStore.get()
        store.update_trading({"max_open_positions": 10})
        trading = store.get_trading()
        assert trading["max_open_positions"] == 10
        assert trading["mode"] == "paper"  # Unchanged


class TestConfigStoreStrategy:
    def test_get_strategy_defaults(self):
        store = RuntimeConfigStore.get()
        strategy = store.get_strategy()
        assert strategy["active_strategy"] == "combined"
        assert strategy["technical_weight"] == 0.40
        assert strategy["derivatives_weight"] == 0.25

    def test_update_strategy_valid_weights(self):
        store = RuntimeConfigStore.get()
        updated = store.update_strategy({
            "technical_weight": 0.50,
            "sentiment_weight": 0.20,
            "onchain_weight": 0.10,
            "derivatives_weight": 0.20,
        })
        assert updated["technical_weight"] == 0.50
        assert updated["sentiment_weight"] == 0.20
        assert updated["onchain_weight"] == 0.10
        assert updated["derivatives_weight"] == 0.20

    def test_update_strategy_invalid_weights_rejected(self):
        store = RuntimeConfigStore.get()
        with pytest.raises(ValueError, match="must sum to 1.0"):
            store.update_strategy({
                "technical_weight": 0.90,
                # sentiment=0.20, onchain=0.15, derivatives=0.25 → sum=1.50
            })

    def test_update_strategy_threshold_only(self):
        store = RuntimeConfigStore.get()
        updated = store.update_strategy({"entry_confidence_threshold": 0.80})
        assert updated["entry_confidence_threshold"] == 0.80
        # Weights unchanged
        assert updated["technical_weight"] == 0.40


class TestConfigStoreRisk:
    def test_get_risk_defaults(self):
        store = RuntimeConfigStore.get()
        risk = store.get_risk()
        assert risk["max_position_pct"] == 0.10
        assert risk["default_stop_loss_pct"] == 0.03

    def test_update_risk(self):
        store = RuntimeConfigStore.get()
        updated = store.update_risk({"max_position_pct": 0.15, "default_stop_loss_pct": 0.05})
        assert updated["max_position_pct"] == 0.15
        assert updated["default_stop_loss_pct"] == 0.05


class TestConfigStoreExchanges:
    def _vault(self):
        return Vault(Vault.generate_key())

    def test_list_exchanges_empty(self):
        store = RuntimeConfigStore.get()
        assert store.list_exchanges() == []

    def test_add_exchange(self):
        store = RuntimeConfigStore.get()
        vault = self._vault()
        result = store.add_exchange(
            name="binance",
            exchange_type="spot",
            api_key="test-key",
            api_secret="test-secret",
            vault=vault,
        )
        assert result["name"] == "binance"
        assert result["exchange_type"] == "spot"
        assert result["is_active"] is True
        assert "id" in result

    def test_list_exchanges_after_add(self):
        store = RuntimeConfigStore.get()
        vault = self._vault()
        store.add_exchange("binance", "spot", "k", "s", vault)
        exchanges = store.list_exchanges()
        assert len(exchanges) == 1
        assert exchanges[0]["name"] == "binance"
        # Credentials should NOT be in public dict
        assert "api_key" not in exchanges[0]
        assert "api_key_encrypted" not in exchanges[0]

    def test_remove_exchange(self):
        store = RuntimeConfigStore.get()
        vault = self._vault()
        result = store.add_exchange("binance", "spot", "k", "s", vault)
        assert store.remove_exchange(result["id"]) is True
        assert store.list_exchanges() == []

    def test_remove_nonexistent_exchange(self):
        store = RuntimeConfigStore.get()
        assert store.remove_exchange("nonexistent-id") is False

    def test_get_exchange_entry(self):
        store = RuntimeConfigStore.get()
        vault = self._vault()
        result = store.add_exchange("binance", "spot", "my-key", "my-secret", vault)
        entry = store.get_exchange_entry(result["id"])
        assert entry is not None
        assert entry.name == "binance"
        # Verify we can decrypt credentials
        assert vault.decrypt(entry.api_key_encrypted) == "my-key"
        assert vault.decrypt(entry.api_secret_encrypted) == "my-secret"
