import { NavLink } from 'react-router-dom';
import { Flame, Brain, Bell, Cable, ScrollText, UserCog } from 'lucide-react';
import { cn } from '@/lib/cn';
import { ROUTES } from '@/lib/constants';
import { useEffect } from 'react';

const moreItems = [
  { to: ROUTES.SCREENER, icon: Flame, label: 'Screener' },
  { to: ROUTES.INTELLIGENCE, icon: Brain, label: 'Intelligence' },
  { to: ROUTES.ALERTS, icon: Bell, label: 'Alerts' },
  { to: ROUTES.CONNECTIONS, icon: Cable, label: 'Connections' },
  { to: ROUTES.LOGGING, icon: ScrollText, label: 'Logging' },
  { to: ROUTES.ACCOUNT, icon: UserCog, label: 'Account' },
];

interface MoreMenuProps {
  onClose: () => void;
}

export function MoreMenu({ onClose }: MoreMenuProps) {
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, []);

  return (
    <div className="fixed inset-0 z-40 md:hidden">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Bottom sheet */}
      <div
        className={cn(
          'absolute bottom-16 left-0 right-0',
          'bg-ct-bg-card border-t border-ct-border rounded-t-2xl',
          'pb-safe animate-slide-up',
        )}
      >
        {/* Handle bar */}
        <div className="flex justify-center pt-3 pb-2">
          <div className="w-10 h-1 rounded-full bg-ct-border" />
        </div>

        {/* Navigation grid */}
        <nav className="px-4 pb-4">
          <div className="grid grid-cols-3 gap-2">
            {moreItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                onClick={onClose}
                className={({ isActive }) =>
                  cn(
                    'flex flex-col items-center gap-2 p-4 rounded-xl',
                    'text-xs font-medium transition-colors',
                    'active:scale-95',
                    isActive
                      ? 'bg-ct-accent/10 text-ct-accent'
                      : 'bg-ct-bg-hover text-ct-text-muted',
                  )
                }
              >
                <Icon size={24} strokeWidth={1.8} />
                <span>{label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
      </div>
    </div>
  );
}
