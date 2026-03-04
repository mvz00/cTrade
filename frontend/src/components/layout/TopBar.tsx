import { useHealth } from '@/api/hooks/useHealth';
import { useTradingMode, useUpdateTradingMode } from '@/api/hooks/useConfig';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { useToast } from '@/components/ui/Toast';
import { ConfirmDialog, useConfirm } from '@/components/ui/ConfirmDialog';
import { UserDropdown } from './UserDropdown';

export function TopBar() {
  const health = useHealth();
  const tradingMode = useTradingMode();
  const updateMode = useUpdateTradingMode();
  const { toast } = useToast();
  const { confirm, dialogProps } = useConfirm();

  const isOnline = health.data?.status === 'ok';
  const mode = tradingMode.data?.mode ?? 'paper';

  async function handleToggleMode() {
    const newMode = mode === 'paper' ? 'live' : 'paper';
    const title = newMode === 'live' ? 'Switch to Live Trading' : 'Switch to Paper Trading';
    const message = newMode === 'live'
      ? 'You are about to switch to LIVE trading. Real money will be used for all trades.'
      : 'Switch back to Paper trading mode? No real money will be used.';
    const ok = await confirm({
      title,
      message,
      confirmLabel: newMode === 'live' ? 'Go Live' : 'Switch',
      variant: newMode === 'live' ? 'danger' : 'primary',
    });
    if (!ok) return;
    updateMode.mutate(
      { mode: newMode },
      {
        onSuccess: () => toast(`Switched to ${newMode} trading`, 'success'),
        onError: (e) => toast(e.message, 'error'),
      },
    );
  }

  return (
    <>
      <header className="h-14 pt-safe bg-ct-bg-card border-b border-ct-border flex items-center justify-between px-4 md:px-6">
        {/* Mobile: app brand */}
        <div className="md:hidden flex items-center gap-2">
          <span className="text-sm font-bold bg-gradient-to-r from-ct-accent to-ct-blue bg-clip-text text-transparent">
            cTrade
          </span>
        </div>
        {/* Desktop spacer */}
        <div className="hidden md:block" />

        <div className="flex items-center gap-3 md:gap-4">
          <button
            onClick={handleToggleMode}
            disabled={updateMode.isPending}
            className="cursor-pointer hover:opacity-80 transition-opacity disabled:opacity-50"
            title={`Click to switch to ${mode === 'paper' ? 'live' : 'paper'} trading`}
          >
            <Badge variant={mode === 'paper' ? 'warning' : 'danger'}>
              {mode === 'paper' ? '📄 Paper' : '🔴 Live'}
            </Badge>
          </button>
          <StatusDot
            status={health.isLoading ? 'loading' : isOnline ? 'ok' : 'error'}
            label={health.isLoading ? 'Connecting...' : isOnline ? 'Online' : 'Offline'}
          />
          <UserDropdown />
        </div>
      </header>

      <ConfirmDialog {...dialogProps} />
    </>
  );
}
