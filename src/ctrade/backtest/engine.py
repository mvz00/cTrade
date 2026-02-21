"""Backtesting engine — runs strategies against historical data."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ctrade.analysis.technical.engine import TechnicalAnalysisEngine
from ctrade.core.enums import SignalAction
from ctrade.exchange.market_data import MarketDataProvider


class BacktestEngine:
    """Runs backtests by simulating trades on historical candle data."""

    def __init__(self) -> None:
        self._ta_engine = TechnicalAnalysisEngine()
        self._results: list[dict[str, Any]] = []

    async def run(
        self,
        symbol: str,
        initial_capital: float = 10000.0,
        num_candles: int = 200,
        timeframe: str = "1h",
        entry_threshold: float = 0.65,
        exit_threshold: float = 0.35,
        fee_pct: float = 0.001,
    ) -> dict[str, Any]:
        """Run a backtest and return results."""
        market = MarketDataProvider.get_instance()
        candles = await market.get_candles(symbol, timeframe, num_candles)

        if len(candles) < 50:
            raise ValueError(f"Not enough candle data: got {len(candles)}, need at least 50")

        # Simulate walk-forward
        cash = initial_capital
        position_qty = 0.0
        position_entry = 0.0
        equity_curve: list[dict[str, Any]] = []
        trades: list[dict[str, Any]] = []
        entry_time: datetime | None = None
        peak = initial_capital
        max_drawdown = 0.0

        window_size = 50  # Minimum candles for TA

        for i in range(window_size, len(candles)):
            window = candles[i - window_size:i + 1]
            current_price = float(window[-1].close)
            current_time = window[-1].time

            # Portfolio value
            portfolio_value = cash + position_qty * current_price
            equity_curve.append({
                "timestamp": current_time.isoformat(),
                "value": round(portfolio_value, 2),
            })

            # Track drawdown
            if portfolio_value > peak:
                peak = portfolio_value
            dd = (peak - portfolio_value) / peak if peak > 0 else 0
            if dd > max_drawdown:
                max_drawdown = dd

            # Run TA
            signal, _ = self._ta_engine.analyze(
                window,
                entry_threshold=entry_threshold,
                exit_threshold=exit_threshold,
            )

            # Execute signals
            if signal.action == SignalAction.BUY and position_qty == 0:
                # Buy
                cost = cash * 0.95  # Use 95% of cash
                fee = cost * fee_pct
                buy_qty = (cost - fee) / current_price
                position_qty = buy_qty
                position_entry = current_price
                entry_time = current_time
                cash -= cost

            elif signal.action == SignalAction.SELL and position_qty > 0:
                # Sell
                proceeds = position_qty * current_price
                fee = proceeds * fee_pct
                cash += proceeds - fee

                pnl = (current_price - position_entry) * position_qty - fee
                pnl_pct = ((current_price - position_entry) / position_entry * 100) if position_entry > 0 else 0

                trades.append({
                    "pair_symbol": symbol,
                    "side": "long",
                    "entry_price": round(position_entry, 4),
                    "exit_price": round(current_price, 4),
                    "quantity": round(position_qty, 8),
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "entry_time": entry_time.isoformat() if entry_time else "",
                    "exit_time": current_time.isoformat(),
                })

                position_qty = 0.0
                position_entry = 0.0
                entry_time = None

        # Close any remaining position at last price
        if position_qty > 0:
            last_price = float(candles[-1].close)
            proceeds = position_qty * last_price
            fee = proceeds * fee_pct
            cash += proceeds - fee
            pnl = (last_price - position_entry) * position_qty - fee
            pnl_pct = ((last_price - position_entry) / position_entry * 100) if position_entry > 0 else 0

            trades.append({
                "pair_symbol": symbol,
                "side": "long",
                "entry_price": round(position_entry, 4),
                "exit_price": round(last_price, 4),
                "quantity": round(position_qty, 8),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "entry_time": entry_time.isoformat() if entry_time else "",
                "exit_time": candles[-1].time.isoformat(),
            })
            position_qty = 0.0

        final_value = cash
        total_return_pct = ((final_value - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0

        winning = [t for t in trades if t["pnl"] > 0]
        losing = [t for t in trades if t["pnl"] <= 0]
        win_rate = len(winning) / len(trades) * 100 if trades else 0

        # Simplified Sharpe ratio from equity curve
        sharpe = self._compute_sharpe(equity_curve)

        result = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": round(win_rate, 1),
            "max_drawdown_pct": round(max_drawdown * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "equity_curve": equity_curve,
            "trade_log": trades,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._results.append(result)
        return result

    def get_results(self) -> list[dict[str, Any]]:
        """Get all past backtest results."""
        return list(reversed(self._results))

    @staticmethod
    def _compute_sharpe(equity_curve: list[dict[str, Any]]) -> float:
        """Compute annualized Sharpe ratio from equity curve."""
        if len(equity_curve) < 2:
            return 0.0

        values = [p["value"] for p in equity_curve]
        returns = []
        for i in range(1, len(values)):
            if values[i - 1] > 0:
                returns.append((values[i] - values[i - 1]) / values[i - 1])

        if not returns or len(returns) < 2:
            return 0.0

        import numpy as np
        mean_r = float(np.mean(returns))
        std_r = float(np.std(returns))

        if std_r == 0:
            return 0.0

        # Annualize (assume hourly data, ~8760 periods/year)
        sharpe = (mean_r / std_r) * math.sqrt(8760)
        return sharpe
