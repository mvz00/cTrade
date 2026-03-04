import { useDashboardSummary } from '@/api/hooks/useDashboard';
import { RecommendationsPanel } from '@/components/panels/RecommendationsPanel';
import { useHealth } from '@/api/hooks/useHealth';
import { Card, CardTitle, CardValue } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusDot } from '@/components/ui/StatusDot';
import { Spinner } from '@/components/ui/Spinner';
import { EquityCurveChart } from '@/components/charts/EquityCurveChart';
import { PositionPriceChart } from '@/components/charts/PositionPriceChart';
import { PortfolioDonut } from '@/components/charts/PortfolioDonut';
import { formatRelative } from '@/lib/formatters';
import { useCurrency } from '@/contexts/CurrencyContext';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/api/client';
import { REFETCH_INTERVALS } from '@/lib/constants';
import { useWebSocket } from '@/api/hooks/useWebSocket';
import { useCallback, useMemo, useState } from 'react';
import { usePositionCandles } from '@/api/hooks/useTrading';
import {
  DollarSign, TrendingUp, BarChart3, Radio, Layers, Activity,
} from 'lucide-react';

// Events that should trigger Dashboard cache invalidation
const DASHBOARD_WS_EVENTS = [
  'signal.generated',
  'order.filled',
  'position.opened',
  'position.closed',
  'risk.stop_loss_hit',
  'risk.take_profit_hit',
  'alert.triggered',
];

const HISTORY_RANGES = ['24h', '7d', '30d', '90d', 'all'] as const;
type HistoryRange = (typeof HISTORY_RANGES)[number];

const PRICE_RANGES = ['1h', '12h', '24h', '7d'] as const;
type PriceRange = (typeof PRICE_RANGES)[number];

/** Map UI range labels to API (timeframe, limit) parameters */
const PRICE_RANGE_PARAMS: Record<PriceRange, { timeframe: string; limit: number }> = {
  '1h':  { timeframe: '1m',  limit: 60 },
  '12h': { timeframe: '5m',  limit: 144 },
  '24h': { timeframe: '15m', limit: 96 },
  '7d':  { timeframe: '1h',  limit: 168 },
};

export function DashboardPage() {
  const { formatMoney } = useCurrency();
  const queryClient = useQueryClient();
  const [historyRange, setHistoryRange] = useState<HistoryRange>('7d');
  const [priceRange, setPriceRange] = useState<PriceRange>('24h');

  // WebSocket: invalidate React Query cache on relevant events
  const handleWsMessage = useCallback(
    (msg: { type: string }) => {
      if (DASHBOARD_WS_EVENTS.includes(msg.type)) {
        queryClient.invalidateQueries({ queryKey: ['dashboard'] });
        queryClient.invalidateQueries({ queryKey: ['trading'] });
        queryClient.invalidateQueries({ queryKey: ['signals'] });
      }
    },
    [queryClient],
  );

  const { connected: wsConnected } = useWebSocket({
    subscriptions: DASHBOARD_WS_EVENTS,
    onMessage: handleWsMessage,
  });

  const { data: summary, isLoading } = useDashboardSummary();
  const { data: health } = useHealth();
  const { data: status } = useQuery({ queryKey: ['dashboard', 'status'], queryFn: api.systemStatus, refetchInterval: REFETCH_INTERVALS.DASHBOARD });
  const { data: equityCurve } = useQuery({ queryKey: ['dashboard', 'equity-curve'], queryFn: api.equityCurve, refetchInterval: REFETCH_INTERVALS.DASHBOARD });
  const { data: portfolioHistory } = useQuery({
    queryKey: ['dashboard', 'portfolio-history', historyRange],
    queryFn: () => api.portfolioHistory(historyRange),
    refetchInterval: REFETCH_INTERVALS.DASHBOARD,
  });
  const { data: portfolio } = useQuery({ queryKey: ['trading', 'portfolio'], queryFn: api.portfolio, refetchInterval: REFETCH_INTERVALS.DASHBOARD });
  const { data: positions } = useQuery({ queryKey: ['trading', 'positions', 'open'], queryFn: () => api.listPositions('open'), refetchInterval: REFETCH_INTERVALS.DASHBOARD });
  const { data: signals } = useQuery({ queryKey: ['signals', { limit: 10 }], queryFn: () => api.listSignals({ limit: 10 }), refetchInterval: REFETCH_INTERVALS.SIGNALS });
  const { data: recentTrades } = useQuery({ queryKey: ['dashboard', 'recent-trades'], queryFn: api.recentTrades, refetchInterval: REFETCH_INTERVALS.DASHBOARD });

  // Open position symbols for price chart
  const openSymbols = useMemo(
    () => [...new Set((positions || []).map((p) => p.pair_symbol))],
    [positions],
  );
  const priceParams = PRICE_RANGE_PARAMS[priceRange];
  const { data: positionCandles } = usePositionCandles(
    openSymbols,
    priceParams.timeframe,
    priceParams.limit,
  );

  if (isLoading) return <Spinner />;

  const watchedPairs = (status as any)?.watched_pairs ?? 0;

  // Use portfolio-history (per-exchange) if available, fall back to legacy equity curve
  const hasPortfolioHistory = portfolioHistory && portfolioHistory.length > 0 && portfolioHistory.some(s => s.points.length > 0);

  return (
    <div>
      <PageHeader title="Dashboard" description="Portfolio overview and system status" />

      {/* Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-accent/10"><DollarSign size={18} className="text-ct-accent" /></div><CardTitle>Portfolio Value</CardTitle></div>
          <CardValue>{formatMoney(summary?.total_value_usd ?? 10000)}</CardValue>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-blue/10"><TrendingUp size={18} className="text-ct-blue" /></div><CardTitle>Daily P&L</CardTitle></div>
          <CardValue className={(summary?.daily_pnl ?? 0) > 0 ? 'text-ct-green' : (summary?.daily_pnl ?? 0) < 0 ? 'text-ct-red' : ''}>{formatMoney(summary?.daily_pnl ?? 0)}</CardValue>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-yellow/10"><Layers size={18} className="text-ct-yellow" /></div><CardTitle>Open Positions</CardTitle></div>
          <CardValue>{summary?.open_positions ?? 0}</CardValue>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-green/10"><Radio size={18} className="text-ct-green" /></div><CardTitle>Active Feeds</CardTitle></div>
          <CardValue>{summary?.active_feeds ?? 0}</CardValue>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-accent/10"><BarChart3 size={18} className="text-ct-accent" /></div><CardTitle>Trading Mode</CardTitle></div>
          <CardValue><Badge variant={summary?.trading_mode === 'live' ? 'danger' : 'warning'}>{summary?.trading_mode === 'live' ? 'Live' : 'Paper'}</Badge></CardValue>
        </Card>
      </div>

      {/* Open Positions Price Chart — only shown when positions exist */}
      {openSymbols.length > 0 && (
        <Card className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Position Prices</h3>
            <div className="flex gap-1">
              {PRICE_RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setPriceRange(r)}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    priceRange === r
                      ? 'bg-ct-accent text-white'
                      : 'bg-ct-bg-hover text-ct-text-muted hover:text-ct-text'
                  }`}
                >
                  {r.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          <PositionPriceChart series={positionCandles ?? []} />
        </Card>
      )}

      {/* Portfolio History Chart + Portfolio Donut */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <Card className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Portfolio History</h3>
            <div className="flex gap-1">
              {HISTORY_RANGES.map((r) => (
                <button
                  key={r}
                  onClick={() => setHistoryRange(r)}
                  className={`px-2.5 py-1 text-xs rounded transition-colors ${
                    historyRange === r
                      ? 'bg-ct-accent text-white'
                      : 'bg-ct-bg-hover text-ct-text-muted hover:text-ct-text'
                  }`}
                >
                  {r.toUpperCase()}
                </button>
              ))}
            </div>
          </div>
          {hasPortfolioHistory ? (
            <EquityCurveChart series={portfolioHistory!} tradingMode={summary?.trading_mode} />
          ) : (
            <EquityCurveChart data={equityCurve ?? []} />
          )}
        </Card>
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">Portfolio Breakdown</h3>
          {portfolio ? (
            <PortfolioDonut portfolio={portfolio} />
          ) : (
            <div className="flex items-center justify-center h-48 text-ct-text-dim">
              <p className="text-sm">No portfolio data</p>
            </div>
          )}
        </Card>
      </div>

      {/* Recommended Buys */}
      <div className="mb-6">
        <RecommendationsPanel />
      </div>

      {/* System Status + Positions + Signals */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* System Status */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">System Status</h3>
          <div className="space-y-3">
            {status && Object.entries(status).filter(([k]) => k !== 'watched_pairs').map(([key, val]: [string, any]) => (
              <div key={key} className="flex items-center justify-between py-2 border-b border-ct-border">
                <span className="text-sm text-ct-text capitalize">{key.replace('_', ' ')}</span>
                <StatusDot status={val.status === 'ok' ? 'ok' : 'warning'} label={val.label} />
              </div>
            ))}
            {!status && (
              <>
                <div className="flex items-center justify-between py-2 border-b border-ct-border"><span className="text-sm text-ct-text">API Server</span><StatusDot status={health?.status === 'ok' ? 'ok' : 'error'} label={health?.status === 'ok' ? 'Online' : 'Offline'} /></div>
                <div className="flex items-center justify-between py-2 border-b border-ct-border"><span className="text-sm text-ct-text">Event Bus</span><StatusDot status="ok" label="Running" /></div>
              </>
            )}
            {/* WebSocket status */}
            <div className="flex items-center justify-between py-2 border-b border-ct-border">
              <span className="text-sm text-ct-text">WebSocket</span>
              <StatusDot status={wsConnected ? 'ok' : 'error'} label={wsConnected ? 'Connected' : 'Disconnected'} />
            </div>
            {/* Watched pairs count */}
            {watchedPairs > 0 && (
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-ct-text">Watched Pairs</span>
                <span className="text-sm text-ct-text-muted font-medium">{watchedPairs}</span>
              </div>
            )}
          </div>
        </Card>

        {/* Open Positions */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">Open Positions</h3>
          {(positions || []).length === 0 ? (
            <div className="flex flex-col items-center py-8 text-ct-text-dim"><Layers size={32} className="mb-2" /><p className="text-sm">No open positions</p></div>
          ) : (
            <div className="space-y-2">
              {(positions || []).slice(0, 5).map(p => (
                <div key={p.id} className="flex items-center justify-between py-2 px-2 rounded bg-ct-bg-hover text-sm">
                  <div><span className="font-mono">{p.pair_symbol}</span> <Badge variant={p.side === 'long' ? 'success' : 'danger'}>{p.side}</Badge></div>
                  <span className={(p.unrealized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>{formatMoney(p.unrealized_pnl ?? 0)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Recent Signals */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">Recent Signals</h3>
          {(signals || []).length === 0 ? (
            <div className="flex flex-col items-center py-8 text-ct-text-dim"><Activity size={32} className="mb-2" /><p className="text-sm">No signals yet</p></div>
          ) : (
            <div className="space-y-2">
              {(signals || []).slice(0, 5).map(s => (
                <div key={s.id} className="flex items-center justify-between py-2 px-2 rounded bg-ct-bg-hover text-sm">
                  <div className="flex items-center gap-2">
                    <Badge variant={s.action === 'BUY' ? 'success' : s.action === 'SELL' ? 'danger' : 'default'}>{s.action}</Badge>
                    <span className="font-mono">{s.pair_symbol}</span>
                  </div>
                  <span className="text-xs text-ct-text-dim">{formatRelative(s.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Recent Trades */}
      <Card className="mt-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">Recent Trades</h3>
        {(recentTrades || []).length === 0 ? (
          <p className="text-sm text-ct-text-dim py-4 text-center">No trades yet. Start the trading engine to begin.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-ct-border text-ct-text-muted text-left"><th className="pb-2">Pair</th><th className="pb-2">Side</th><th className="pb-2">Entry</th><th className="pb-2">Exit</th><th className="pb-2">P&L</th><th className="pb-2">Closed</th></tr></thead>
              <tbody>
                {(recentTrades || []).map(t => (
                  <tr key={t.id} className="border-b border-ct-border/50">
                    <td className="py-2 font-mono">{t.pair_symbol}</td>
                    <td><Badge variant={t.side === 'long' ? 'success' : 'danger'}>{t.side}</Badge></td>
                    <td>{formatMoney(t.entry_price)}</td>
                    <td>{t.exit_price ? formatMoney(t.exit_price) : '—'}</td>
                    <td className={(t.realized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>{formatMoney(t.realized_pnl ?? 0)}</td>
                    <td className="text-ct-text-dim">{t.closed_at ? formatRelative(t.closed_at) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
