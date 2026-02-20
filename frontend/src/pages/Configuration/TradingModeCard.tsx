import { useTradingMode, useUpdateTradingMode } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { Toggle } from '@/components/ui/Toggle';
import { useToast } from '@/components/ui/Toast';
import { Sliders } from 'lucide-react';
import { useState } from 'react';

export function TradingModeCard() {
  const { data: mode } = useTradingMode();
  const updateMode = useUpdateTradingMode();
  const { toast } = useToast();
  const [confirming, setConfirming] = useState(false);

  const isLive = mode?.mode === 'live';

  function handleToggle(checked: boolean) {
    if (checked && !confirming) {
      // Switching to live — require confirmation
      setConfirming(true);
      return;
    }
    setConfirming(false);
    updateMode.mutate(
      { mode: checked ? 'live' : 'paper' },
      {
        onSuccess: (data) => toast(`Trading mode set to ${data.mode}`, 'success'),
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  return (
    <Card>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-ct-yellow/10">
          <Sliders size={18} className="text-ct-yellow" />
        </div>
        <CardTitle className="mb-0">Trading Mode</CardTitle>
      </div>

      <Toggle
        label="Mode"
        description="Paper mode simulates trades without risking real capital"
        checked={isLive}
        onChange={handleToggle}
        inactiveLabel="Paper"
        activeLabel="Live"
      />

      {confirming && (
        <div className="mt-3 p-3 rounded-lg border border-ct-red/30 bg-ct-red/5">
          <p className="text-sm text-ct-red font-medium mb-2">
            Switch to live trading?
          </p>
          <p className="text-xs text-ct-text-muted mb-3">
            Live mode will execute real trades on your exchange. Make sure your strategy
            is well-tested in paper mode first.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => handleToggle(true)}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-ct-red text-white hover:bg-ct-red/90"
            >
              Confirm Switch to Live
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
