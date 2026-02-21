import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useAlerts, useCreateAlert, useDeleteAlert, useToggleAlert, useAlertHistory } from '@/api/hooks/useAlerts';
import { usePairs } from '@/api/hooks/useTrading';
import { formatRelative, formatUSD, formatNumber } from '@/lib/formatters';
import {
  Bell, BellPlus, History, Trash2, ToggleLeft, ToggleRight,
} from 'lucide-react';

const ALERT_TYPES = [
  { value: 'price_above', label: 'Price Above', description: 'Triggers when price rises above value' },
  { value: 'price_below', label: 'Price Below', description: 'Triggers when price drops below value' },
  { value: 'signal_buy', label: 'BUY Signal', description: 'Triggers when a BUY signal is generated (value = min confidence)' },
  { value: 'signal_sell', label: 'SELL Signal', description: 'Triggers when a SELL signal is generated (value = min confidence)' },
  { value: 'pnl_above', label: 'P&L Above', description: 'Triggers when total P&L exceeds value ($)' },
  { value: 'pnl_below', label: 'P&L Below', description: 'Triggers when total P&L drops below value ($)' },
];

export function AlertsPage() {
  const { data: alerts } = useAlerts();
  const { data: history } = useAlertHistory();
  const { data: pairs } = usePairs();
  const createAlert = useCreateAlert();
  const deleteAlert = useDeleteAlert();
  const toggleAlert = useToggleAlert();

  const [alertType, setAlertType] = useState('price_above');
  const [symbol, setSymbol] = useState('BTC/USDT');
  const [value, setValue] = useState(70000);
  const [message, setMessage] = useState('');

  function handleCreate() {
    createAlert.mutate(
      {
        alert_type: alertType,
        symbol,
        value,
        message: message || undefined,
      },
      {
        onSuccess: () => {
          setMessage('');
        },
      },
    );
  }

  const selectedType = ALERT_TYPES.find(t => t.value === alertType);
  const isPriceType = alertType.startsWith('price_');
  const isSignalType = alertType.startsWith('signal_');

  return (
    <div>
      <PageHeader
        title="Alerts"
        description="Configure price alerts, signal notifications, and system warnings"
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active Alerts */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <Bell size={14} className="inline mr-1" />
            Active Alerts
          </h3>
          {(!alerts || alerts.length === 0) ? (
            <div className="flex flex-col items-center py-8 text-ct-text-dim">
              <Bell size={40} className="mb-3" />
              <p className="text-sm">No alerts configured</p>
              <p className="text-xs mt-1">Create an alert to get started</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {alerts.map(alert => (
                <div key={alert.id} className="flex items-center justify-between py-3 px-3 rounded-lg bg-ct-bg-hover">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Badge variant={alert.is_active ? 'success' : 'default'}>
                        {ALERT_TYPES.find(t => t.value === alert.alert_type)?.label ?? alert.alert_type}
                      </Badge>
                      <span className="font-mono text-sm text-ct-text">{alert.symbol}</span>
                    </div>
                    <div className="text-xs text-ct-text-dim">
                      {alert.alert_type.startsWith('price_') && `$${formatNumber(alert.value, 2)}`}
                      {alert.alert_type.startsWith('signal_') && `Confidence >= ${(alert.value * 100).toFixed(0)}%`}
                      {alert.alert_type.startsWith('pnl_') && `${formatUSD(alert.value)}`}
                      {alert.message && ` — ${alert.message}`}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 ml-2">
                    <button
                      onClick={() => toggleAlert.mutate(alert.id)}
                      className="p-1.5 rounded hover:bg-ct-border transition-colors"
                      title={alert.is_active ? 'Disable' : 'Enable'}
                    >
                      {alert.is_active ? (
                        <ToggleRight size={18} className="text-ct-green" />
                      ) : (
                        <ToggleLeft size={18} className="text-ct-text-dim" />
                      )}
                    </button>
                    <button
                      onClick={() => deleteAlert.mutate(alert.id)}
                      className="p-1.5 rounded hover:bg-ct-red/20 transition-colors"
                      title="Delete alert"
                    >
                      <Trash2 size={16} className="text-ct-red" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Create Alert */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <BellPlus size={14} className="inline mr-1" />
            Create Alert
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-xs text-ct-text-muted mb-1">Alert Type</label>
              <select
                value={alertType}
                onChange={e => setAlertType(e.target.value)}
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
              >
                {ALERT_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              {selectedType && (
                <p className="text-xs text-ct-text-dim mt-1">{selectedType.description}</p>
              )}
            </div>

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
              <label className="block text-xs text-ct-text-muted mb-1">
                {isPriceType ? 'Target Price ($)' : isSignalType ? 'Min Confidence (0-1)' : 'P&L Value ($)'}
              </label>
              <input
                type="number"
                value={value}
                onChange={e => setValue(Number(e.target.value))}
                step={isPriceType ? 100 : isSignalType ? 0.05 : 10}
                min={isSignalType ? 0 : undefined}
                max={isSignalType ? 1 : undefined}
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
              />
            </div>

            <div>
              <label className="block text-xs text-ct-text-muted mb-1">Message (optional)</label>
              <input
                type="text"
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="Custom notification message..."
                className="w-full bg-ct-bg border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text placeholder:text-ct-text-dim"
              />
            </div>

            <button
              onClick={handleCreate}
              disabled={createAlert.isPending}
              className="w-full bg-ct-accent hover:bg-ct-accent/90 text-ct-bg font-medium rounded-lg px-4 py-2.5 text-sm transition-colors disabled:opacity-50"
            >
              <span className="flex items-center justify-center gap-2">
                <BellPlus size={16} />
                {createAlert.isPending ? 'Creating...' : 'Create Alert'}
              </span>
            </button>

            {createAlert.isError && (
              <p className="text-xs text-ct-red">{(createAlert.error as Error).message}</p>
            )}
            {createAlert.isSuccess && (
              <p className="text-xs text-ct-green">Alert created successfully</p>
            )}
          </div>
        </Card>
      </div>

      {/* Alert History */}
      <Card className="mt-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
          <History size={14} className="inline mr-1" />
          Alert History
        </h3>
        {(!history || history.length === 0) ? (
          <div className="flex flex-col items-center py-8 text-ct-text-dim">
            <History size={32} className="mb-2" />
            <p className="text-sm">No triggered alerts yet</p>
            <p className="text-xs mt-1">Alerts will appear here when their conditions are met</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-ct-border text-ct-text-muted text-left">
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Pair</th>
                  <th className="pb-2 pr-4">Triggered Value</th>
                  <th className="pb-2 pr-4">Message</th>
                  <th className="pb-2">Triggered</th>
                </tr>
              </thead>
              <tbody>
                {history.map(h => (
                  <tr key={h.id} className="border-b border-ct-border/50">
                    <td className="py-2 pr-4">
                      <Badge variant="warning">
                        {ALERT_TYPES.find(t => t.value === h.alert_type)?.label ?? h.alert_type}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 font-mono">{h.symbol}</td>
                    <td className="py-2 pr-4">
                      {h.alert_type.startsWith('price_') && formatUSD(h.triggered_value)}
                      {h.alert_type.startsWith('signal_') && `${(h.triggered_value * 100).toFixed(0)}%`}
                      {h.alert_type.startsWith('pnl_') && formatUSD(h.triggered_value)}
                    </td>
                    <td className="py-2 pr-4 text-ct-text-dim max-w-xs truncate">{h.message}</td>
                    <td className="py-2 text-ct-text-dim">{formatRelative(h.triggered_at)}</td>
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
