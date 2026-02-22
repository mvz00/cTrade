"""Tests for the LiveEngine."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ctrade.exchange.live_engine import LiveEngine


def _make_mock_ticker(price: float = 67000.0):
    """Create a mock Ticker object with a given last_price."""
    ticker = MagicMock()
    ticker.last_price = Decimal(str(price))
    return ticker


def _make_mock_mdp(
    exchange: AsyncMock | None = None,
    price: float = 67000.0,
) -> MagicMock:
    """Create a fully configured mock MarketDataProvider."""
    mock_mdp = MagicMock()
    mock_mdp._create_ccxt_exchange = AsyncMock(return_value=exchange)
    mock_mdp._try_ccxt_ticker = AsyncMock(return_value=_make_mock_ticker(price))
    mock_mdp.get_current_price = MagicMock(return_value=price)
    return mock_mdp


@pytest.fixture(autouse=True)
def _reset_live_engine():
    """Reset LiveEngine singleton between tests."""
    LiveEngine.reset()
    yield
    LiveEngine.reset()


class TestLiveEngineSingleton:
    """Test singleton pattern."""

    def test_singleton_returns_same_instance(self):
        a = LiveEngine.get_instance()
        b = LiveEngine.get_instance()
        assert a is b

    def test_reset_clears_instance(self):
        a = LiveEngine.get_instance()
        LiveEngine.reset()
        b = LiveEngine.get_instance()
        assert a is not b


class TestLiveEngineWatchedPairs:
    """Watched pairs are delegated to PaperEngine (shared)."""

    def test_watched_pairs_delegated(self):
        from ctrade.exchange.paper_engine import PaperEngine

        paper = PaperEngine.get_instance()
        live = LiveEngine.get_instance()

        paper.add_watched_pair("BTC/USDT")
        assert "BTC/USDT" in live.get_watched_pairs()

        live.add_watched_pair("ETH/USDT")
        assert "ETH/USDT" in paper.get_watched_pairs()


class TestLiveEnginePlaceOrder:
    """Test place_order with mocked ccxt."""

    @pytest.mark.asyncio
    async def test_place_order_success(self):
        """Successful market order via ccxt."""
        live = LiveEngine.get_instance()

        mock_exchange = AsyncMock()
        mock_exchange.create_market_buy_order = AsyncMock(return_value={
            "id": "exchange-123",
            "average": 67000.0,
            "filled": 0.001,
            "fee": {"cost": 0.067, "currency": "USDT"},
        })
        mock_exchange.close = AsyncMock()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp_cls.get_instance.return_value = _make_mock_mdp(mock_exchange)

            order = await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        assert order.status == "filled"
        assert float(order.avg_fill_price) == 67000.0
        assert float(order.fee) == 0.067
        mock_exchange.create_market_buy_order.assert_called_once_with("BTC/USDT", 0.001)
        mock_exchange.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_place_order_ccxt_failure(self):
        """Order is rejected when ccxt raises an exception."""
        live = LiveEngine.get_instance()

        mock_exchange = AsyncMock()
        mock_exchange.create_market_buy_order = AsyncMock(
            side_effect=Exception("Insufficient balance")
        )
        mock_exchange.close = AsyncMock()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp_cls.get_instance.return_value = _make_mock_mdp(mock_exchange)

            order = await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        assert order.status == "rejected"
        assert "Exchange error" in order.error_message

    @pytest.mark.asyncio
    async def test_place_order_no_exchange(self):
        """Order rejected when no exchange is configured."""
        live = LiveEngine.get_instance()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp = _make_mock_mdp(exchange=None)
            mock_mdp_cls.get_instance.return_value = mock_mdp

            order = await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        assert order.status == "rejected"
        assert "No exchange configured" in order.error_message

    @pytest.mark.asyncio
    async def test_place_order_max_size_enforced(self):
        """Order rejected when it exceeds max_order_usdt."""
        live = LiveEngine.get_instance()

        from ctrade.core.config_store import RuntimeConfigStore

        store = RuntimeConfigStore.get()
        store.update_trading({"max_order_usdt": 5.0})

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp = _make_mock_mdp(price=67000.0)
            mock_mdp_cls.get_instance.return_value = mock_mdp

            # Try to buy 0.01 BTC = $670 >> $5 max
            order = await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.01,
            )

        assert order.status == "rejected"
        assert "exceeds max" in order.error_message

        # Reset
        store.update_trading({"max_order_usdt": 100.0})

    @pytest.mark.asyncio
    async def test_place_order_max_size_skipped_when_no_ticker(self):
        """Order proceeds when no real ticker is available for size check."""
        live = LiveEngine.get_instance()

        from ctrade.core.config_store import RuntimeConfigStore

        store = RuntimeConfigStore.get()
        store.update_trading({"max_order_usdt": 5.0})

        mock_exchange = AsyncMock()
        mock_exchange.create_market_buy_order = AsyncMock(return_value={
            "id": "ex-99",
            "average": 67000.0,
            "filled": 0.001,
            "fee": {"cost": 0.067, "currency": "USDT"},
        })
        mock_exchange.close = AsyncMock()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp = _make_mock_mdp(mock_exchange)
            # No ticker available → size check skipped → order proceeds
            mock_mdp._try_ccxt_ticker = AsyncMock(return_value=None)
            mock_mdp_cls.get_instance.return_value = mock_mdp

            order = await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        # Should proceed to exchange despite size check being skipped
        assert order.status == "filled"

        # Reset
        store.update_trading({"max_order_usdt": 100.0})


class TestLiveEnginePortfolio:
    """Test portfolio fetching."""

    @pytest.mark.asyncio
    async def test_get_portfolio_delegates_to_market_data(self):
        """get_portfolio uses MarketDataProvider.fetch_exchange_portfolio."""
        live = LiveEngine.get_instance()

        mock_portfolio = {
            "cash_balance": {"USDT": 65.0},
            "total_value_usd": 65.0,
            "positions_value": 0.0,
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "daily_pnl": 0.0,
            "open_positions": 0,
            "closed_positions": 0,
            "total_orders": 0,
        }

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp = MagicMock()
            mock_mdp.fetch_exchange_portfolio = AsyncMock(return_value=mock_portfolio)
            mock_mdp_cls.get_instance.return_value = mock_mdp

            result = await live.get_portfolio()

        assert result["total_value_usd"] == 65.0
        assert result["cash_balance"]["USDT"] == 65.0

    @pytest.mark.asyncio
    async def test_get_portfolio_fallback_when_fetch_fails(self):
        """Returns empty portfolio when exchange fetch fails."""
        live = LiveEngine.get_instance()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp = MagicMock()
            mock_mdp.fetch_exchange_portfolio = AsyncMock(return_value=None)
            mock_mdp_cls.get_instance.return_value = mock_mdp

            result = await live.get_portfolio()

        assert result["total_value_usd"] == 0.0


class TestLiveEnginePositions:
    """Test position tracking."""

    @pytest.mark.asyncio
    async def test_position_created_on_buy_fill(self):
        """A filled buy order creates a LONG position."""
        live = LiveEngine.get_instance()

        mock_exchange = AsyncMock()
        mock_exchange.create_market_buy_order = AsyncMock(return_value={
            "id": "ex-1",
            "average": 67000.0,
            "filled": 0.001,
            "fee": {"cost": 0.067, "currency": "USDT"},
        })
        mock_exchange.close = AsyncMock()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp_cls.get_instance.return_value = _make_mock_mdp(mock_exchange)

            await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

        positions = live.get_positions(status="open")
        assert len(positions) == 1
        assert positions[0]["pair_symbol"] == "BTC/USDT"
        assert positions[0]["side"] == "long"

    @pytest.mark.asyncio
    async def test_close_position(self):
        """Closing a position creates an opposite order and closes the position."""
        live = LiveEngine.get_instance()

        mock_exchange = AsyncMock()
        # Buy order
        mock_exchange.create_market_buy_order = AsyncMock(return_value={
            "id": "ex-1",
            "average": 67000.0,
            "filled": 0.001,
            "fee": {"cost": 0.067, "currency": "USDT"},
        })
        # Sell order (close)
        mock_exchange.create_market_sell_order = AsyncMock(return_value={
            "id": "ex-2",
            "average": 68000.0,
            "filled": 0.001,
            "fee": {"cost": 0.068, "currency": "USDT"},
        })
        mock_exchange.close = AsyncMock()

        with patch(
            "ctrade.exchange.market_data.MarketDataProvider"
        ) as mock_mdp_cls:
            mock_mdp_cls.get_instance.return_value = _make_mock_mdp(mock_exchange)

            # Open position
            await live.place_order(
                symbol="BTC/USDT",
                side="buy",
                order_type="market",
                quantity=0.001,
            )

            # Close it
            positions = live.get_positions(status="open")
            assert len(positions) == 1
            await live.close_position(positions[0]["id"])

        # Position should be closed
        open_positions = live.get_positions(status="open")
        assert len(open_positions) == 0

        closed = live.get_positions(status="closed")
        assert len(closed) == 1
        assert closed[0]["realized_pnl"] is not None
