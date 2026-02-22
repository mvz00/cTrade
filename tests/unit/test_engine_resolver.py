"""Tests for the engine resolver."""

from __future__ import annotations

import pytest

from ctrade.exchange.engine_resolver import get_engine
from ctrade.exchange.live_engine import LiveEngine
from ctrade.exchange.paper_engine import PaperEngine


class TestEngineResolver:
    """Test get_engine() routing."""

    def test_returns_paper_engine_by_default(self):
        """Default mode is paper — should return PaperEngine."""
        engine = get_engine()
        assert isinstance(engine, PaperEngine)

    def test_returns_paper_engine_when_mode_is_paper(self):
        """Explicit paper mode returns PaperEngine."""
        from ctrade.core.config_store import RuntimeConfigStore

        store = RuntimeConfigStore.get()
        store.update_trading({"mode": "paper"})

        engine = get_engine()
        assert isinstance(engine, PaperEngine)

    def test_returns_paper_engine_when_live_but_no_exchange(self):
        """Live mode without configured exchange falls back to PaperEngine."""
        from ctrade.core.config_store import RuntimeConfigStore

        store = RuntimeConfigStore.get()
        store.update_trading({"mode": "live"})

        # No exchanges configured by default in test fixtures
        engine = get_engine()
        assert isinstance(engine, PaperEngine)

        # Reset
        store.update_trading({"mode": "paper"})

    def test_returns_live_engine_when_live_and_exchange_configured(self):
        """Live mode with a configured exchange returns LiveEngine."""
        from ctrade.core.config_store import RuntimeConfigStore
        from ctrade.security.vault import Vault

        store = RuntimeConfigStore.get()
        vault = Vault(Vault.generate_key())

        # Add a fake exchange
        store.add_exchange(
            name="kraken",
            exchange_type="spot",
            api_key="test-key",
            api_secret="test-secret",
            vault=vault,
        )
        store.update_trading({"mode": "live"})

        engine = get_engine()
        assert isinstance(engine, LiveEngine)

        # Cleanup
        store.update_trading({"mode": "paper"})
        exchanges = store.list_exchanges()
        for ex in exchanges:
            store.remove_exchange(ex["id"])

        LiveEngine.reset()
