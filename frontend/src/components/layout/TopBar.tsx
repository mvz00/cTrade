import { Menu } from 'lucide-react';
import { useHealth } from '@/api/hooks/useHealth';
import { useTradingMode, useUpdateTradingMode } from '@/api/hooks/useConfig';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { useToast } from '@/components/ui/Toast';
import { useSidebar } from '@/contexts/SidebarContext';
import { UserDropdown } from './UserDropdown';

export function TopBar() {
  const health = useHealth();
  const tradingMode = useTradingMode();
  const updateMode = useUpdateTradingMode();
  const { setMobileOpen } = useSidebar();
  const { toast } = useToast();

  const isOnline = health.data?.status === 'ok';
  const mode = tradingMode.data?.mode ?? 'paper';

  function handleToggleMode() {
    const newMode = mode === 'paper' ? 'live' : 'paper';
    const msg = newMode === 'live'
      ? 'Switch to LIVE trading? Real money will be used.'
      : 'Switch to Paper trading?';
    if (!window.confirm(msg)) return;
    updateMode.mutate(
      { mode: newMode },
      {
        onSuccess: () => toast(`Switched to ${newMode} trading`, 'success'),
        onError: (e) => toast(e.message, 'error'),
      },
    );
  }

  return (
    <header className="h-14 bg-ct-bg-card border-b border-ct-border flex items-center justify-between px-4 md:px-6">
      {/* Hamburger menu — mobile only */}
      <button
        className="md:hidden p-2 -ml-1 rounded-lg text-ct-text-muted hover:text-ct-text hover:bg-ct-bg-hover transition-colors"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>
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
  );
}
