import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  CandlestickChart,
  Settings,
  Activity,
  FlaskConical,
  Bell,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { ROUTES } from '@/lib/constants';
import { useState } from 'react';

const navItems = [
  { to: ROUTES.DASHBOARD, icon: LayoutDashboard, label: 'Dashboard' },
  { to: ROUTES.TRADING, icon: CandlestickChart, label: 'Trading' },
  { to: ROUTES.CONFIGURATION, icon: Settings, label: 'Configuration' },
  { to: ROUTES.SIGNALS, icon: Activity, label: 'Signals' },
  { to: ROUTES.BACKTESTING, icon: FlaskConical, label: 'Backtesting' },
  { to: ROUTES.ALERTS, icon: Bell, label: 'Alerts' },
];

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 h-screen bg-ct-bg-card border-r border-ct-border flex flex-col z-20 transition-all duration-200',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-ct-border">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-ct-accent to-ct-blue flex items-center justify-center flex-shrink-0">
            <CandlestickChart size={16} className="text-ct-bg" />
          </div>
          {!collapsed && (
            <span className="text-lg font-bold bg-gradient-to-r from-ct-accent to-ct-blue bg-clip-text text-transparent whitespace-nowrap">
              cTrade
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-ct-accent/10 text-ct-accent'
                  : 'text-ct-text-muted hover:text-ct-text hover:bg-ct-bg-hover'
              )
            }
          >
            <Icon size={18} className="flex-shrink-0" />
            {!collapsed && <span className="whitespace-nowrap">{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-ct-border">
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-ct-text-dim hover:text-ct-text-muted hover:bg-ct-bg-hover transition-colors"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
        {!collapsed && (
          <div className="text-center text-[10px] text-ct-text-dim mt-1">v0.1.0</div>
        )}
      </div>
    </aside>
  );
}
