import { useHealth } from '@/api/hooks/useHealth';
import { useTradingMode } from '@/api/hooks/useConfig';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { UserDropdown } from './UserDropdown';

export function TopBar() {
  const health = useHealth();
  const tradingMode = useTradingMode();

  const isOnline = health.data?.status === 'ok';
  const mode = tradingMode.data?.mode ?? 'paper';

  return (
    <header className="h-14 bg-ct-bg-card border-b border-ct-border flex items-center justify-between px-6">
      <div />

      <div className="flex items-center gap-4">
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
