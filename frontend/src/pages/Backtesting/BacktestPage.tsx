import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useRunBacktest, useBacktestResults } from '@/api/hooks/useBacktest';
import { usePairs } from '@/api/hooks/useTrading';
import { formatUSD, formatPercentRaw, formatNumber, formatRelative } from '@/lib/formatters';
import {
  FlaskConical, BarChart3, Settings, TrendingUp, TrendingDown, Target, Activity,
} from 'lucide-react';

export function BacktestPage() {
  const { data: pairs } = usePairs();
  const { data: pastResults } = useBacktestResults();
  const runBacktest = useRunBacktest();

  const [symbol, setSymbol] = useState('BTC/USDT');
  const [capital, setCapital] = useState(10000);
  const [numCandles, setNumCandles] = useState(200);
  const [timeframe, setTimeframe] = useState('1h');
  const [entryThreshold, setEntryThreshold] = useState(0.65);
  const [exitThreshold, setExitThreshold] = useState(0.35);

  // The latest result to display (from mutation or last in history)
  const result = runBacktest.data ?? (pastResults && pastResults.length > 0 ? pastResults[pastResults.length - 1] : null);

  function handleRun() {
    runBacktest.mutate({
      symbol,
      initial_capital: capital,
      num_candles: numCandles,
      timeframe,
      entry_threshold: entryThreshold,
      exit_threshold: exitThreshold,
    });
  }

  return (
    <div>
      <PageHeader title="Backtesting" description="Test strategies against historical data before trading" />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Backtest Configuration */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <Settings size={14} className="inline mr-1" />
            Configuration
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-ct-text-muted mb-1">Trading Pair</label>
              <select
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
              >
                {(pairs || []).map(p => (
                  <option key={p.symbol} value={p.symbol}>{p.symbol}</option>
                ))}
                {(!pairs || pairs.length === 0) && (
                  <>
                    <option value="BTC/USDT">BTC/USDT</option>
                    <option value="ETH/USDT">ETH/USDT</option>
                    <option value="SOL/USDT">SOL/USDT</option>
                  </>
                )}
              </select>
            </div>

            <div>
              <label className="block text-xs text-ct-text-muted mb-1">Initial Capital ($)</label>
              <input
                type="number"
                value={capital}
                onChange={e => setCapital(Number(e.target.value))}
                min={100}
                step={1000}
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
              />
            </div>

            <div>
              <label className="block text-xs text-ct-text-muted mb-1">Number of Candles</label>
              <input
                type="number"
                value={numCandles}
                onChange={e => setNumCandles(Number(e.target.value))}
                min={50}
                max={1000}
                step={50}
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
              />
            </div>

            <div>
              <label className="block text-xs text-ct-text-muted mb-1">Timeframe</label>
              <select
                value={timeframe}
                onChange={e => setTimeframe(e.target.value)}
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
              >
                <option value="1m">1 minute</option>
                <option value="5m">5 minutes</option>
                <option value="15m">15 minutes</option>
                <option value="1h">1 hour</option>
                <option value="4h">4 hours</option>
                <option value="1d">1 day</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-ct-text-muted mb-1">Entry Threshold</label>
                <input
                  type="number"
                  value={entryThreshold}
                  onChange={e => setEntryThreshold(Number(e.target.value))}
                  min={0.5}
                  max={0.95}
                  step={0.05}
                  className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
                />
              </div>
              <div>
                <label className="block text-xs text-ct-text-muted mb-1">Exit Threshold</label>
                <input
                  type="number"
                  value={exitThreshold}
                  onChange={e => setExitThreshold(Number(e.target.value))}
                  min={0.1}
                  max={0.5}
                  step={0.05}
                  className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
                />
              </div>
            </div>

            <button
              onClick={handleRun}
              disabled={runBacktest.isPending}
              className="w-full bg-ct-accent hover:bg-ct-accent/90 text-ct-bg font-medium rounded-lg px-4 py-2.5 text-sm transition-colors disabled:opacity-50"
            >
              {runBacktest.isPending ? (
                <span className="flex items-center justify-center gap-2"><Spinner className="w-4 h-4" /> Running...</span>
              ) : (
                <span className="flex items-center justify-center gap-2"><FlaskConical size={16} /> Run Backtest</span>
              )}
            </button>

            {runBacktest.isError && (
              <p className="text-xs text-ct-red">{(runBacktest.error as Error).message}</p>
            )}
          </div>
        </Card>

        {/* Results Summary */}
        <Card className="lg:col-span-2">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <BarChart3 size={14} className="inline mr-1" />
            Results
          </h3>
          {!result ? (
            <div className="flex flex-col items-center py-12 text-ct-text-dim">
              <BarChart3 size={48} className="mb-3" />
              <p className="text-sm">Run a backtest to see results</p>
            </div>
          ) : (
            <div>
              {/* Metrics Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <MetricCard
                  label="Total Return"
                  value={formatPercentRaw(result.total_return_pct)}
                  icon={<TrendingUp size={16} />}
                  color={result.total_return_pct >= 0 ? 'text-ct-green' : 'text-ct-red'}
                />
                <MetricCard
                  label="Final Value"
                  value={formatUSD(result.final_value)}
                  icon={<Activity size={16} />}
                  color="text-ct-accent"
                />
                <MetricCard
                  label="Sharpe Ratio"
                  value={formatNumber(result.sharpe_ratio, 2)}
                  icon={<Target size={16} />}
                  color={result.sharpe_ratio >= 1 ? 'text-ct-green' : result.sharpe_ratio >= 0 ? 'text-ct-yellow' : 'text-ct-red'}
                />
                <MetricCard
                  label="Max Drawdown"
                  value={formatPercentRaw(result.max_drawdown_pct)}
                  icon={<TrendingDown size={16} />}
                  color="text-ct-red"
                />
              </div>

              <div className="grid grid-cols-3 gap-4 mb-6">
                <div className="text-center p-3 rounded-lg bg-ct-bg-hover">
                  <div className="text-xs text-ct-text-muted mb-1">Total Trades</div>
                  <div className="text-lg font-semibold text-ct-text">{result.total_trades}</div>
                </div>
                <div className="text-center p-3 rounded-lg bg-ct-bg-hover">
                  <div className="text-xs text-ct-text-muted mb-1">Win Rate</div>
                  <div className={`text-lg font-semibold ${result.win_rate >= 50 ? 'text-ct-green' : 'text-ct-red'}`}>
                    {formatPercentRaw(result.win_rate)}
                  </div>
                </div>
                <div className="text-center p-3 rounded-lg bg-ct-bg-hover">
                  <div className="text-xs text-ct-text-muted mb-1">W / L</div>
                  <div className="text-lg font-semibold text-ct-text">
                    <span className="text-ct-green">{result.winning_trades}</span>
                    {' / '}
                    <span className="text-ct-red">{result.losing_trades}</span>
                  </div>
                </div>
              </div>

              {/* Equity Curve (text-based) */}
              {result.equity_curve && result.equity_curve.length > 0 && (
                <div>
                  <h4 className="text-xs text-ct-text-muted uppercase tracking-wider mb-2">Equity Curve</h4>
                  <div className="h-32 flex items-end gap-px">
                    {sampleEquityCurve(result.equity_curve, 60).map((point, i) => {
                      const min = Math.min(...sampleEquityCurve(result.equity_curve, 60).map(p => p.value));
                      const max = Math.max(...sampleEquityCurve(result.equity_curve, 60).map(p => p.value));
                      const range = max - min || 1;
                      const height = ((point.value - min) / range) * 100;
                      const isGain = point.value >= result.initial_capital;
                      return (
                        <div
                          key={i}
                          className={`flex-1 rounded-t ${isGain ? 'bg-ct-green/60' : 'bg-ct-red/60'}`}
                          style={{ height: `${Math.max(2, height)}%` }}
                          title={`${formatUSD(point.value)}`}
                        />
                      );
                    })}
                  </div>
                  <div className="flex justify-between text-xs text-ct-text-dim mt-1">
                    <span>{formatUSD(result.equity_curve[0]?.value ?? result.initial_capital)}</span>
                    <span>{formatUSD(result.equity_curve[result.equity_curve.length - 1]?.value ?? result.final_value)}</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* Trade Log */}
      <Card>
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          <FlaskConical size={14} className="inline mr-1" />
          Simulated Trade Log
        </h3>
        {!result || result.trade_log.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-ct-text-dim">
            <FlaskConical size={32} className="mb-2" />
            <p className="text-sm">Run a backtest to see simulated trades</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ct-border text-ct-text-muted text-left">
                  <th className="pb-2 pr-4">#</th>
                  <th className="pb-2 pr-4">Pair</th>
                  <th className="pb-2 pr-4">Side</th>
                  <th className="pb-2 pr-4">Entry</th>
                  <th className="pb-2 pr-4">Exit</th>
                  <th className="pb-2 pr-4">Qty</th>
                  <th className="pb-2 pr-4">P&L</th>
                  <th className="pb-2">P&L %</th>
                </tr>
              </thead>
              <tbody>
                {result.trade_log.map((t, i) => (
                  <tr key={i} className="border-b border-ct-border/50">
                    <td className="py-2 pr-4 text-ct-text-dim">{i + 1}</td>
                    <td className="py-2 pr-4 font-mono">{t.pair_symbol}</td>
                    <td className="py-2 pr-4">
                      <Badge variant={t.side === 'long' ? 'success' : 'danger'}>{t.side}</Badge>
                    </td>
                    <td className="py-2 pr-4">{formatUSD(t.entry_price)}</td>
                    <td className="py-2 pr-4">{formatUSD(t.exit_price)}</td>
                    <td className="py-2 pr-4">{formatNumber(t.quantity, 6)}</td>
                    <td className={`py-2 pr-4 ${t.pnl >= 0 ? 'text-ct-green' : 'text-ct-red'}`}>
                      {formatUSD(t.pnl)}
                    </td>
                    <td className={`py-2 ${t.pnl_pct >= 0 ? 'text-ct-green' : 'text-ct-red'}`}>
                      {formatPercentRaw(t.pnl_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Past Results */}
      {pastResults && pastResults.length > 1 && (
        <Card className="mt-6">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">Past Results</h3>
          <div className="space-y-2">
            {pastResults.slice().reverse().map(r => (
              <div key={r.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-ct-bg-hover text-sm">
                <div className="flex items-center gap-3">
                  <span className="font-mono">{r.symbol}</span>
                  <Badge variant={r.total_return_pct >= 0 ? 'success' : 'danger'}>
                    {formatPercentRaw(r.total_return_pct)}
                  </Badge>
                </div>
                <div className="flex items-center gap-4 text-ct-text-dim">
                  <span>{r.total_trades} trades</span>
                  <span>Win: {formatPercentRaw(r.win_rate)}</span>
                  <span>{formatRelative(r.created_at)}</span>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function MetricCard({ label, value, icon, color }: { label: string; value: string; icon: React.ReactNode; color: string }) {
  return (
    <div className="p-3 rounded-lg bg-ct-bg-hover">
      <div className="flex items-center gap-1.5 mb-1">
        <span className={color}>{icon}</span>
        <span className="text-xs text-ct-text-muted">{label}</span>
      </div>
      <div className={`text-lg font-semibold ${color}`}>{value}</div>
    </div>
  );
}

function sampleEquityCurve(curve: { timestamp: string; value: number }[], maxPoints: number) {
  if (curve.length <= maxPoints) return curve;
  const step = curve.length / maxPoints;
  const sampled: typeof curve = [];
  for (let i = 0; i < maxPoints; i++) {
    sampled.push(curve[Math.floor(i * step)]);
  }
  return sampled;
}
