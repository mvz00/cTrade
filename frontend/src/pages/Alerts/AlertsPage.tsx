import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { EmptyState } from '@/components/ui/EmptyState';
import {
  Bell,
  BellPlus,
  History,
} from 'lucide-react';

export function AlertsPage() {
  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Configure price alerts, signal notifications, and system warnings"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active alerts */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Active Alerts
          </h3>
          <EmptyState
            icon={<Bell size={40} />}
            title="No active alerts"
            description="Set up price alerts, volume spikes, sentiment shifts, and signal triggers to get notified."
            phase={8}
          />
        </Card>

        {/* Create alert */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            Create Alert
          </h3>
          <EmptyState
            icon={<BellPlus size={40} />}
            title="Alert builder"
            description="Define conditions (price above/below, RSI threshold, new signal) and notification channels (email, Telegram, Discord)."
            phase={8}
          />
        </Card>
      </div>

      {/* Alert history */}
      <Card className="mt-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          Alert History
        </h3>
        <EmptyState
          icon={<History size={40} />}
          title="No alert history"
          description="Triggered alerts with timestamps and outcomes will be logged here."
          phase={8}
        />
      </Card>
    </div>
  );
}
