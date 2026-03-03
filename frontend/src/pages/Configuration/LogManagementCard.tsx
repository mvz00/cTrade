import { useLoggingConfig, useUpdateLoggingConfig, usePurgeAllData } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { NumberInput } from '@/components/ui/NumberInput';
import { useToast } from '@/components/ui/Toast';
import { ScrollText, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

export function LogManagementCard() {
  const { data: config } = useLoggingConfig();
  const updateConfig = useUpdateLoggingConfig();
  const purgeAll = usePurgeAllData();
  const { toast } = useToast();

  const [logDays, setLogDays] = useState(7);
  const [dataDays, setDataDays] = useState(30);
  const [confirming, setConfirming] = useState(false);

  // Sync form with server data
  useEffect(() => {
    if (config) {
      setLogDays(config.log_rollover_days);
      setDataDays(config.data_rollover_days);
    }
  }, [config]);

  const isDirty = config
    ? logDays !== config.log_rollover_days || dataDays !== config.data_rollover_days
    : false;

  function handleSave() {
    updateConfig.mutate(
      { log_rollover_days: logDays, data_rollover_days: dataDays },
      {
        onSuccess: () => toast('Rollover settings saved', 'success'),
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  function handlePurge() {
    setConfirming(false);
    purgeAll.mutate(undefined, {
      onSuccess: (result) => {
        const parts: string[] = [];
        for (const [table, count] of Object.entries(result.tables_cleared)) {
          if (count > 0) parts.push(`${table}: ${count}`);
        }
        if (result.memory_cleared > 0) parts.push(`memory: ${result.memory_cleared}`);
        const detail = parts.length > 0 ? parts.join(', ') : 'all tables already empty';
        toast(`Purged ${result.total_deleted} total rows (${detail})`, 'success');
      },
      onError: (err) => toast(err.message, 'error'),
    });
  }

  return (
    <Card>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-ct-accent/10">
          <ScrollText size={18} className="text-ct-accent" />
        </div>
        <CardTitle className="mb-0">Data Management</CardTitle>
      </div>

      <p className="text-xs text-ct-text-muted mb-4">
        Configure automatic data retention and purge stored data from the database.
        Rollover runs hourly and deletes rows older than the configured period.
      </p>

      <div className="space-y-3">
        <NumberInput
          label="Log Rollover"
          value={logDays}
          onChange={setLogDays}
          min={1}
          max={365}
          suffix="days"
          tooltip="Application log entries and audit log records older than this are automatically deleted."
        />
        <NumberInput
          label="Data Rollover"
          value={dataDays}
          onChange={setDataDays}
          min={1}
          max={365}
          suffix="days"
          tooltip="Trading data (signals, orders, closed positions, candles, sentiment, on-chain metrics, portfolio snapshots, alert history) older than this is automatically deleted. Open positions are never deleted."
        />
      </div>

      <div className="mt-4 flex gap-2">
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending || !isDirty}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-ct-accent text-ct-bg hover:bg-ct-accent/90 disabled:opacity-50 transition-colors"
        >
          {updateConfig.isPending ? 'Saving...' : 'Save Settings'}
        </button>
        <button
          onClick={() => setConfirming(true)}
          disabled={purgeAll.isPending || confirming}
          className="px-4 py-2 rounded-lg text-sm font-medium border border-ct-red/50 text-ct-red hover:bg-ct-red/10 disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
          <Trash2 size={14} />
          {purgeAll.isPending ? 'Purging...' : 'Purge All Data'}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 p-3 rounded-lg border border-ct-red/30 bg-ct-red/5">
          <p className="text-sm text-ct-red font-medium mb-2">
            Purge all accumulated data?
          </p>
          <p className="text-xs text-ct-text-muted mb-3">
            This will permanently delete all data from: logs, audit log, signals, orders,
            positions, candles, sentiment, on-chain metrics, portfolio snapshots, and alert
            history. This action cannot be undone.
          </p>
          <div className="flex gap-2">
            <button
              onClick={handlePurge}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-ct-red text-white hover:bg-ct-red/90"
            >
              Confirm Purge
            </button>
            <button
              onClick={() => setConfirming(false)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-ct-bg-card border border-ct-border text-ct-text hover:bg-ct-bg-hover"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </Card>
  );
}
