import { useLoggingConfig, useUpdateLoggingConfig, usePurgeLogs } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { NumberInput } from '@/components/ui/NumberInput';
import { useToast } from '@/components/ui/Toast';
import { ScrollText, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

export function LogManagementCard() {
  const { data: config } = useLoggingConfig();
  const updateConfig = useUpdateLoggingConfig();
  const purgeLogs = usePurgeLogs();
  const { toast } = useToast();

  const [rolloverDays, setRolloverDays] = useState(7);
  const [confirming, setConfirming] = useState(false);

  // Sync form with server data
  useEffect(() => {
    if (config) {
      setRolloverDays(config.log_rollover_days);
    }
  }, [config]);

  const isDirty = config ? rolloverDays !== config.log_rollover_days : false;

  function handleSave() {
    updateConfig.mutate(
      { log_rollover_days: rolloverDays },
      {
        onSuccess: () => toast('Log rollover settings saved', 'success'),
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  function handlePurge() {
    setConfirming(false);
    purgeLogs.mutate(undefined, {
      onSuccess: (result) => {
        const total = result.audit_log_deleted + result.log_entries_deleted + result.memory_cleared;
        toast(
          `Logs purged: ${result.audit_log_deleted} audit + ${result.log_entries_deleted} log entries + ${result.memory_cleared} in-memory (${total} total)`,
          'success'
        );
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
        <CardTitle className="mb-0">Log Management</CardTitle>
      </div>

      <p className="text-xs text-ct-text-muted mb-4">
        Configure automatic log retention and purge stored logs from the database.
      </p>

      <NumberInput
        label="Log Rollover Days"
        value={rolloverDays}
        onChange={setRolloverDays}
        min={1}
        max={365}
        suffix="days"
        tooltip="Log entries older than this many days are automatically deleted. Applies to both audit logs and application log entries."
      />

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
          disabled={purgeLogs.isPending || confirming}
          className="px-4 py-2 rounded-lg text-sm font-medium border border-ct-red/50 text-ct-red hover:bg-ct-red/10 disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
          <Trash2 size={14} />
          {purgeLogs.isPending ? 'Purging...' : 'Purge All Logs'}
        </button>
      </div>

      {confirming && (
        <div className="mt-3 p-3 rounded-lg border border-ct-red/30 bg-ct-red/5">
          <p className="text-sm text-ct-red font-medium mb-2">
            Purge all logs?
          </p>
          <p className="text-xs text-ct-text-muted mb-3">
            This will permanently delete all entries from the audit log and application log
            tables, plus clear the in-memory log buffer. This action cannot be undone.
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
