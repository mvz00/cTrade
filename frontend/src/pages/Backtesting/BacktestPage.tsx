import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import {
  FlaskConical,
  BarChart3,
  Settings,
} from 'lucide-react';

export function BacktestPage() {
  return (
    <div>
      <PageHeader
        title="Backtesting"
        description="Test strategies against historical data before trading"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        {/* Backtest config */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Configuration
          </h3>
          <EmptyState
            icon={<Settings size={40} />}
            title="Set up a backtest"
            description="Select strategy, trading pair, date range, and initial capital to run a simulation."
            phase={7}
            className="py-8"
          />
        </Card>

        {/* Results summary */}
        <Card className="lg:col-span-2">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Results
          </h3>
          <EmptyState
            icon={<BarChart3 size={48} />}
            title="No backtest results"
            description="Sharpe ratio, max drawdown, win rate, total return, and equity curves will appear here after a backtest run."
            phase={7}
          />
        </Card>
      </div>

      {/* Trade log */}
      <Card>
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          Simulated Trade Log
        </h3>
        <EmptyState
          icon={<FlaskConical size={40} />}
          title="Run a backtest to see trades"
          description="Every simulated trade with entry/exit times, prices, and P&L will be logged here."
          phase={7}
        />
      </Card>
    </div>
  );
}
