import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import { Badge } from '@/components/ui/Badge';
import { useTradingMode } from '@/api/hooks/useConfig';
import {
  CandlestickChart,
  ArrowUpDown,
  ClipboardList,
  Layers,
} from 'lucide-react';

export function TradingPage() {
  const { data: mode } = useTradingMode();

  return (
    <div>
      <PageHeader
        title="Trading"
        description="Live trading view and order management"
        actions={
          <Badge variant={mode?.mode === 'live' ? 'danger' : 'warning'}>
            {mode?.mode === 'live' ? 'Live' : 'Paper'} Trading
          </Badge>
        }
      />

      {/* Price chart placeholder */}
      <Card className="mb-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          Price Chart
        </h3>
        <EmptyState
          icon={<CandlestickChart size={48} />}
          title="Chart coming soon"
          description="Real-time candlestick charts with TradingView lightweight-charts will display here once exchange connectivity is wired up."
          phase={1}
        />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Order entry */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Place Order
          </h3>
          <EmptyState
            icon={<ArrowUpDown size={40} />}
            title="Order entry"
            description="Buy/sell order form with market, limit, and stop-limit support."
            phase={1}
          />
        </Card>

        {/* Open orders */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Open Orders
          </h3>
          <EmptyState
            icon={<ClipboardList size={40} />}
            title="No open orders"
            description="Active orders will be listed here with cancel/modify options."
            phase={3}
          />
        </Card>

        {/* Positions */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Positions
          </h3>
          <EmptyState
            icon={<Layers size={40} />}
            title="No positions"
            description="Open positions with P&L, stop-loss, and take-profit levels."
            phase={3}
          />
        </Card>
      </div>

      {/* Trade history */}
      <Card className="mt-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          Trade History
        </h3>
        <EmptyState
          icon={<ClipboardList size={40} />}
          title="No trades yet"
          description="Completed trades with entry/exit prices, P&L, and fees will appear here."
          phase={3}
        />
      </Card>
    </div>
  );
}
