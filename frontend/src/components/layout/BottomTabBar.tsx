import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  CandlestickChart,
  Activity,
  Settings,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { ROUTES } from '@/lib/constants';
import { useState } from 'react';
import { MoreMenu } from './MoreMenu';

const tabs = [
  { to: ROUTES.DASHBOARD, icon: LayoutDashboard, label: 'Dashboard' },
  { to: ROUTES.TRADING, icon: CandlestickChart, label: 'Trading' },
  { to: ROUTES.SIGNALS, icon: Activity, label: 'Signals' },
  { to: ROUTES.CONFIGURATION, icon: Settings, label: 'Config' },
];

/** Routes accessible via the "More" tab */
const moreRoutes = [
  ROUTES.SCREENER,
  ROUTES.INTELLIGENCE,
  ROUTES.ALERTS,
  ROUTES.CONNECTIONS,
  ROUTES.LOGGING,
  ROUTES.ACCOUNT,
];

export function BottomTabBar() {
  const [moreOpen, setMoreOpen] = useState(false);
  const location = useLocation();

  const isMoreActive = moreRoutes.some((r) => location.pathname.startsWith(r));

  return (
    <>
      {moreOpen && <MoreMenu onClose={() => setMoreOpen(false)} />}

      <nav
        className={cn(
          'fixed bottom-0 left-0 right-0 z-30 md:hidden',
          'bg-ct-bg-card/80 backdrop-blur-xl',
          'border-t border-ct-border/50',
          'pb-safe',
        )}
      >
        <div className="flex items-stretch justify-around h-16">
          {tabs.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMoreOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex flex-col items-center justify-center flex-1 gap-0.5',
                  'text-[10px] font-medium transition-colors',
                  'active:scale-95 active:opacity-70',
                  isActive ? 'text-ct-accent' : 'text-ct-text-dim',
                )
              }
            >
              <Icon size={22} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}

          <button
            onClick={() => setMoreOpen(!moreOpen)}
            className={cn(
              'flex flex-col items-center justify-center flex-1 gap-0.5',
              'text-[10px] font-medium transition-colors',
              'active:scale-95 active:opacity-70',
              isMoreActive || moreOpen ? 'text-ct-accent' : 'text-ct-text-dim',
            )}
          >
            <MoreHorizontal size={22} strokeWidth={1.8} />
            <span>More</span>
          </button>
        </div>
      </nav>
    </>
  );
}
