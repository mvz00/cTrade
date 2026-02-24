import { Menu } from 'lucide-react';
import { useHealth } from '@/api/hooks/useHealth';
import { useTradingMode } from '@/api/hooks/useConfig';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { useSidebar } from '@/contexts/SidebarContext';
import { UserDropdown } from './UserDropdown';

export function TopBar() {
  const health = useHealth();
  const tradingMode = useTradingMode();
  const { setMobileOpen } = useSidebar();

  const isOnline = health.data?.status === 'ok';
  const mode = tradingMode.data?.mode ?? 'paper';

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
        <Badge variant={mode === 'paper' ? 'warning' : 'danger'}>
          {mode === 'paper' ? 'Paper Trading' : 'Live Trading'}
        </Badge>
        <StatusDot
          status={health.isLoading ? 'loading' : isOnline ? 'ok' : 'error'}
          label={health.isLoading ? 'Connecting...' : isOnline ? 'Online' : 'Offline'}
        />
        <UserDropdown />
      </div>
    </header>
  );
}
