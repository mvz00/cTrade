import { useDashboardSummary } from '@/api/hooks/useDashboard';
import { useHealth } from '@/api/hooks/useHealth';
import { Card, CardTitle, CardValue } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { EmptyState } from '@/components/ui/EmptyState';
import { PageHeader } from '@/components/ui/PageHeader';
import { StatusDot } from '@/components/ui/StatusDot';
import { Spinner } from '@/components/ui/Spinner';
import { formatUSD } from '@/lib/formatters';
import {
  DollarSign,
  TrendingUp,
  BarChart3,
  Radio,
  LineChart,
  Activity,
  Layers,
} from 'lucide-react';

export function DashboardPage() {
  const { data: summary, isLoading } = useDashboardSummary();
  const { data: health } = useHealth();

  if (isLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Portfolio overview and system status"
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-ct-accent/10">
              <DollarSign size={18} className="text-ct-accent" />
            </div>
            <CardTitle>Portfolio Value</CardTitle>
          </div>
          <CardValue>{formatUSD(summary?.total_value_usd ?? 0)}</CardValue>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-ct-blue/10">
              <TrendingUp size={18} className="text-ct-blue" />
            </div>
            <CardTitle>Daily P&L</CardTitle>
          </div>
          <CardValue className={summary?.daily_pnl && summary.daily_pnl > 0 ? 'text-ct-green' : summary?.daily_pnl && summary.daily_pnl < 0 ? 'text-ct-red' : ''}>
            {formatUSD(summary?.daily_pnl ?? 0)}
          </CardValue>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-ct-yellow/10">
              <Layers size={18} className="text-ct-yellow" />
            </div>
            <CardTitle>Open Positions</CardTitle>
          </div>
          <CardValue>{summary?.open_positions ?? 0}</CardValue>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-ct-green/10">
              <Radio size={18} className="text-ct-green" />
            </div>
            <CardTitle>Active Feeds</CardTitle>
          </div>
          <CardValue>{summary?.active_feeds ?? 0}</CardValue>
        </Card>

        <Card>
          <div className="flex items-center gap-3 mb-3">
            <div className="p-2 rounded-lg bg-ct-accent/10">
              <BarChart3 size={18} className="text-ct-accent" />
            </div>
            <CardTitle>Trading Mode</CardTitle>
          </div>
          <CardValue>
            <Badge variant={summary?.trading_mode === 'live' ? 'danger' : 'warning'}>
              {summary?.trading_mode === 'live' ? 'Live' : 'Paper'}
            </Badge>
          </CardValue>
        </Card>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Equity Curve - spans 2 columns */}
        <Card className="lg:col-span-2">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Equity Curve
          </h3>
          <EmptyState
            icon={<LineChart size={48} />}
            title="No portfolio data yet"
            description="The equity curve will display your portfolio value over time once trading begins."
            phase={1}
          />
        </Card>

        {/* System Status */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            System Status
          </h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2 border-b border-ct-border">
              <span className="text-sm text-ct-text">API Server</span>
              <StatusDot
                status={health?.status === 'ok' ? 'ok' : 'error'}
                label={health?.status === 'ok' ? 'Online' : 'Offline'}
              />
            </div>
            <div className="flex items-center justify-between py-2 border-b border-ct-border">
              <span className="text-sm text-ct-text">Database</span>
              <StatusDot status="warning" label="Not connected" />
            </div>
            <div className="flex items-center justify-between py-2 border-b border-ct-border">
              <span className="text-sm text-ct-text">Redis</span>
              <StatusDot status="warning" label="Not connected" />
            </div>
            <div className="flex items-center justify-between py-2 border-b border-ct-border">
              <span className="text-sm text-ct-text">Exchange Feed</span>
              <StatusDot status="warning" label="Not configured" />
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-sm text-ct-text">Event Bus</span>
              <StatusDot status="ok" label="Running" />
            </div>
          </div>
        </Card>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Open Positions
          </h3>
          <EmptyState
            icon={<Layers size={40} />}
            title="No open positions"
            description="Positions will appear here once the trading engine starts executing trades."
            phase={3}
          />
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Recent Signals
          </h3>
          <EmptyState
            icon={<Activity size={40} />}
            title="No signals yet"
            description="Trading signals will appear here once technical analysis and feeds are connected."
            phase={2}
          />
        </Card>
      </div>
    </div>
  );
}
