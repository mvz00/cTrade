"""Tests for the paper trading engine."""

from __future__ import annotations

import pytest

from ctrade.exchange.market_data import MarketDataProvider
from ctrade.exchange.paper_engine import PaperEngine


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons before each test."""
    PaperEngine.reset()
    MarketDataProvider.reset()
    yield
    PaperEngine.reset()
    MarketDataProvider.reset()


class TestPaperEngineInit:
    def test_initial_balance(self):
        engine = PaperEngine.get_instance()
        portfolio = engine.get_portfolio()
        assert portfolio["total_value_usd"] == 10000.0
        assert portfolio["cash_balance"]["USDT"] == 10000.0

    def test_singleton(self):
        e1 = PaperEngine.get_instance()
        e2 = PaperEngine.get_instance()
        assert e1 is e2

    def test_reset(self):
        e1 = PaperEngine.get_instance()
        PaperEngine.reset()
        e2 = PaperEngine.get_instance()
        assert e1 is not e2

    def test_empty_orders(self):
        engine = PaperEngine.get_instance()
        assert engine.get_orders() == []

    def test_empty_positions(self):
        engine = PaperEngine.get_instance()
        assert engine.get_positions() == []

    def test_equity_curve_initial(self):
        engine = PaperEngine.get_instance()
        curve = engine.get_equity_curve()
        assert len(curve) == 1
        assert curve[0]["total_value"] == 10000.0


class TestWatchedPairs:
    def test_add_pair(self):
        engine = PaperEngine.get_instance()
        assert engine.add_watched_pair("BTC/USDT") is True
        assert "BTC/USDT" in engine.get_watched_pairs()

    def test_add_duplicate_pair(self):
        engine = PaperEngine.get_instance()
        engine.add_watched_pair("BTC/USDT")
        assert engine.add_watched_pair("BTC/USDT") is False

    def test_remove_pair(self):
        engine = PaperEngine.get_instance()
        engine.add_watched_pair("BTC/USDT")
        assert engine.remove_watched_pair("BTC/USDT") is True
        assert "BTC/USDT" not in engine.get_watched_pairs()

    def test_remove_nonexistent(self):
        engine = PaperEngine.get_instance()
        assert engine.remove_watched_pair("FAKE/PAIR") is False


class TestOrderExecution:
    def test_market_buy_fills_immediately(self):
        engine = PaperEngine.get_instance()
        order = engine.place_order("BTC/USDT", "buy", "market", 0.01)
        assert order.status == "filled"
        assert order.filled_quantity > 0
        assert order.avg_fill_price is not None
        assert order.fee > 0

    def test_market_sell_fills_immediately(self):
        engine = PaperEngine.get_instance()
        # Buy first to have some BTC
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        # Now sell
        order = engine.place_order("BTC/USDT", "sell", "market", 0.01)
        assert order.status == "filled"

    def test_insufficient_balance_rejected(self):
        engine = PaperEngine.get_instance()
        # Try to buy way more than we can afford
        order = engine.place_order("BTC/USDT", "buy", "market", 100.0)
        assert order.status == "rejected"
        assert "Insufficient" in (order.error_message or "")

    def test_sell_without_holdings_rejected(self):
        engine = PaperEngine.get_instance()
        order = engine.place_order("BTC/USDT", "sell", "market", 1.0)
        assert order.status == "rejected"

    def test_order_appears_in_list(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        orders = engine.get_orders()
        assert len(orders) == 1
        assert orders[0]["pair_symbol"] == "BTC/USDT"

    def test_limit_order_stays_pending(self):
        engine = PaperEngine.get_instance()
        order = engine.place_order("BTC/USDT", "buy", "limit", 0.01, price=50000.0)
        assert order.status == "pending"


class TestPositionManagement:
    def test_buy_creates_long_position(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        positions = engine.get_positions("open")
        assert len(positions) == 1
        assert positions[0]["side"] == "long"
        assert positions[0]["pair_symbol"] == "BTC/USDT"

    def test_sell_closes_long_position(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        engine.place_order("BTC/USDT", "sell", "market", 0.01)
        open_pos = engine.get_positions("open")
        closed_pos = engine.get_positions("closed")
        assert len(open_pos) == 0
        assert len(closed_pos) == 1
        assert closed_pos[0]["realized_pnl"] is not None

    def test_close_position_by_id(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        positions = engine.get_positions("open")
        pos_id = positions[0]["id"]
        order = engine.close_position(pos_id)
        assert order is not None
        assert order.status == "filled"

    def test_close_nonexistent_position(self):
        engine = PaperEngine.get_instance()
        result = engine.close_position("nonexistent-id")
        assert result is None


class TestPortfolio:
    def test_portfolio_after_buy(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        portfolio = engine.get_portfolio()
        assert portfolio["open_positions"] == 1
        assert portfolio["total_orders"] == 1
        assert portfolio["cash_balance"]["USDT"] < 10000.0

    def test_portfolio_after_round_trip(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        engine.place_order("BTC/USDT", "sell", "market", 0.01)
        portfolio = engine.get_portfolio()
        assert portfolio["open_positions"] == 0
        assert portfolio["closed_positions"] == 1
        assert portfolio["total_orders"] == 2

    def test_equity_curve_grows_with_trades(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        curve = engine.get_equity_curve()
        assert len(curve) >= 2  # Initial + after trade

    def test_recent_trades_empty_initially(self):
        engine = PaperEngine.get_instance()
        trades = engine.get_recent_trades()
        assert trades == []

    def test_recent_trades_after_close(self):
        engine = PaperEngine.get_instance()
        engine.place_order("BTC/USDT", "buy", "market", 0.01)
        engine.place_order("BTC/USDT", "sell", "market", 0.01)
        trades = engine.get_recent_trades()
        assert len(trades) == 1
