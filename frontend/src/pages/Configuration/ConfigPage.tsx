import { useStrategyConfig, useRiskConfig, useTradingMode } from '@/api/hooks/useConfig';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card, CardTitle } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';
import { Shield, Sliders, Plug, Key } from 'lucide-react';

function ConfigField({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-ct-border last:border-b-0">
      <span className="text-sm text-ct-text-muted">{label}</span>
      <span className="text-sm font-medium text-ct-text">{value}</span>
    </div>
  );
}

function PercentField({ label, value }: { label: string; value: number }) {
  return <ConfigField label={label} value={`${(value * 100).toFixed(1)}%`} />;
}

export function ConfigPage() {
  const { data: mode, isLoading: modeLoading } = useTradingMode();
  const { data: strategy, isLoading: stratLoading } = useStrategyConfig();
  const { data: risk, isLoading: riskLoading } = useRiskConfig();

  if (modeLoading || stratLoading || riskLoading) return <Spinner />;

  return (
    <div>
      <PageHeader
        title="Configuration"
        description="Manage trading strategy, risk parameters, and exchange connections"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Trading Mode */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-ct-yellow/10">
              <Sliders size={18} className="text-ct-yellow" />
            </div>
            <CardTitle className="mb-0">Trading Mode</CardTitle>
          </div>
          <div className="flex items-center justify-between py-3">
            <span className="text-sm text-ct-text-muted">Current Mode</span>
            <Badge variant={mode?.mode === 'live' ? 'danger' : 'warning'}>
              {mode?.mode === 'live' ? 'Live' : 'Paper'}
            </Badge>
          </div>
          <p className="text-xs text-ct-text-dim mt-3">
            Paper mode simulates trades without risking real capital. Switch to live mode only when you are confident in your strategy.
          </p>
        </Card>

        {/* Strategy Config */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-ct-accent/10">
              <Sliders size={18} className="text-ct-accent" />
            </div>
            <CardTitle className="mb-0">Strategy Settings</CardTitle>
          </div>
          {strategy ? (
            <div>
              <ConfigField label="Active Strategy" value={strategy.active_strategy} />
              <PercentField label="Technical Weight" value={strategy.technical_weight} />
              <PercentField label="Sentiment Weight" value={strategy.sentiment_weight} />
              <PercentField label="On-Chain Weight" value={strategy.onchain_weight} />
              <PercentField label="Entry Confidence" value={strategy.entry_confidence_threshold} />
              <PercentField label="Exit Confidence" value={strategy.exit_confidence_threshold} />
            </div>
          ) : (
            <p className="text-sm text-ct-text-dim">Unable to load strategy config.</p>
          )}
        </Card>

        {/* Risk Config */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-ct-red/10">
              <Shield size={18} className="text-ct-red" />
            </div>
            <CardTitle className="mb-0">Risk Management</CardTitle>
          </div>
          {risk ? (
            <div>
              <PercentField label="Max Position Size" value={risk.max_position_pct} />
              <PercentField label="Max Daily Loss" value={risk.max_daily_loss_pct} />
              <PercentField label="Max Drawdown" value={risk.max_drawdown_pct} />
              <PercentField label="Default Stop Loss" value={risk.default_stop_loss_pct} />
              <PercentField label="Default Take Profit" value={risk.default_take_profit_pct} />
            </div>
          ) : (
            <p className="text-sm text-ct-text-dim">Unable to load risk config.</p>
          )}
        </Card>

        {/* Exchange Configuration */}
        <Card>
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 rounded-lg bg-ct-blue/10">
              <Plug size={18} className="text-ct-blue" />
            </div>
            <CardTitle className="mb-0">Exchange Connection</CardTitle>
          </div>
          <EmptyState
            icon={<Key size={40} />}
            title="No exchange configured"
            description="Add your exchange API credentials and select trading pairs to start receiving market data."
            phase={1}
            className="py-8"
          />
        </Card>
      </div>
    </div>
  );
}
