import { useDashboardSummary } from '@/api/hooks/useDashboard';
import { useHealth } from '@/api/hooks/useHealth';
import { Card, CardTitle, CardValue } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusDot } from '@/components/ui/StatusDot';
import { Spinner } from '@/components/ui/Spinner';
import { formatUSD, formatRelative } from '@/lib/formatters';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/api/client';
import { REFETCH_INTERVALS } from '@/lib/constants';
import {
  DollarSign, TrendingUp, BarChart3, Radio, Layers, Activity,
} from 'lucide-react';

export function DashboardPage() {
  const { data: summary, isLoading } = useDashboardSummary();
  const { data: health } = useHealth();
  const { data: status } = useQuery({ queryKey: ['dashboard', 'status'], queryFn: api.systemStatus, refetchInterval: REFETCH_INTERVALS.DASHBOARD });
  const { data: positions } = useQuery({ queryKey: ['trading', 'positions', 'open'], queryFn: () => api.listPositions('open'), refetchInterval: REFETCH_INTERVALS.DASHBOARD });
  const { data: signals } = useQuery({ queryKey: ['signals', { limit: 10 }], queryFn: () => api.listSignals({ limit: 10 }), refetchInterval: REFETCH_INTERVALS.SIGNALS });
  const { data: recentTrades } = useQuery({ queryKey: ['dashboard', 'recent-trades'], queryFn: api.recentTrades, refetchInterval: REFETCH_INTERVALS.DASHBOARD });

  if (isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader title="Dashboard" description="Portfolio overview and system status" />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-accent/10"><DollarSign size={18} className="text-ct-accent" /></div><CardTitle>Portfolio Value</CardTitle></div>
          <CardValue>{formatUSD(summary?.total_value_usd ?? 10000)}</CardValue>
        </Card>
        <Card>
          <div className="flex items-center gap-3 mb-3"><div className="p-2 rounded-lg bg-ct-blue/10"><TrendingUp size={18} className="text-ct-blue" /></div><CardTitle>Daily P&L</CardTitle></div>
          <CardValue className={(summary?.daily_pnl ?? 0) > 0 ? 'text-ct-green' : (summary?.daily_pnl ?? 0) < 0 ? 'text-ct-red' : ''}>{formatUSD(summary?.daily_pnl ?? 0)}</CardValue>
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
                <div className="flex items-center justify-between py-2"><span className="text-sm text-ct-text">Event Bus</span><StatusDot status="ok" label="Running" /></div>
              </>
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
                  <span className={(p.unrealized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>{formatUSD(p.unrealized_pnl ?? 0)}</span>
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
                    <td>{formatUSD(t.entry_price)}</td>
                    <td>{t.exit_price ? formatUSD(t.exit_price) : '—'}</td>
                    <td className={(t.realized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>{formatUSD(t.realized_pnl ?? 0)}</td>
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
