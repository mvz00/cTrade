import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  CandlestickChart,
  Settings,
  Cable,
  Activity,
  Brain,
  Flame,
  Bell,
  UserCog,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { cn } from '@/lib/cn';
import { ROUTES } from '@/lib/constants';
import { useSidebar } from '@/contexts/SidebarContext';

const navItems = [
  { to: ROUTES.DASHBOARD, icon: LayoutDashboard, label: 'Dashboard' },
  { to: ROUTES.TRADING, icon: CandlestickChart, label: 'Trading' },
  { to: ROUTES.CONFIGURATION, icon: Settings, label: 'Configuration' },
  { to: ROUTES.CONNECTIONS, icon: Cable, label: 'Connections' },
  { to: ROUTES.SIGNALS, icon: Activity, label: 'Signals' },
  { to: ROUTES.INTELLIGENCE, icon: Brain, label: 'Intelligence' },
  { to: ROUTES.SCREENER, icon: Flame, label: 'Screener' },
  { to: ROUTES.ALERTS, icon: Bell, label: 'Alerts' },
];

export function Sidebar() {
  const { collapsed, setCollapsed, mobileOpen, setMobileOpen } = useSidebar();

  /** On mobile, close the overlay when a nav link is clicked. */
  const closeMobile = () => setMobileOpen(false);

  /**
   * Label visibility:
   * - Mobile (overlay): always show labels (sidebar is always w-56)
   * - Desktop collapsed: hide labels (icon-only w-16)
   * - Desktop expanded: show labels (w-56)
   *
   * Achieved with: className={cn('whitespace-nowrap', collapsed && 'md:hidden')}
   * → On mobile (<md), md:hidden doesn't apply so labels always show.
   * → On desktop (>=md), collapsed adds md:hidden to hide labels.
   */
  const labelClass = cn('whitespace-nowrap', collapsed && 'md:hidden');

  return (
    <aside
      className={cn(
        'fixed left-0 top-0 h-screen bg-ct-bg-card border-r border-ct-border',
        'flex flex-col z-20 transition-all duration-200',
        // Width: always w-56 on mobile, w-56/w-16 on desktop
        collapsed ? 'w-56 md:w-16' : 'w-56',
        // Mobile: off-screen by default, slides in when mobileOpen
        mobileOpen ? 'translate-x-0' : '-translate-x-full',
        // Desktop: always visible regardless of mobileOpen
        'md:translate-x-0',
      )}
    >
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-ct-border">
        <div className="flex items-center gap-2.5 overflow-hidden">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-ct-accent to-ct-blue flex items-center justify-center flex-shrink-0">
            <CandlestickChart size={16} className="text-ct-bg" />
          </div>
          <span className={cn(
            'text-lg font-bold bg-gradient-to-r from-ct-accent to-ct-blue bg-clip-text text-transparent whitespace-nowrap',
            collapsed && 'md:hidden',
          )}>
            cTrade
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 flex flex-col">
        <div className="space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              onClick={closeMobile}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-ct-accent/10 text-ct-accent'
                    : 'text-ct-text-muted hover:text-ct-text hover:bg-ct-bg-hover',
                )
              }
            >
              <Icon size={18} className="flex-shrink-0" />
              <span className={labelClass}>{label}</span>
            </NavLink>
          ))}
        </div>

        {/* Account link at bottom */}
        <div className="mt-auto pt-3 border-t border-ct-border">
          <NavLink
            to={ROUTES.ACCOUNT}
            onClick={closeMobile}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-ct-accent/10 text-ct-accent'
                  : 'text-ct-text-muted hover:text-ct-text hover:bg-ct-bg-hover',
              )
            }
          >
            <UserCog size={18} className="flex-shrink-0" />
            <span className={labelClass}>Account</span>
          </NavLink>
        </div>
      </nav>

      {/* Footer */}
      <div className="p-2 border-t border-ct-border">
        {/* Desktop: collapse toggle */}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full hidden md:flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-ct-text-dim hover:text-ct-text-muted hover:bg-ct-bg-hover transition-colors"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          {!collapsed && <span className="text-xs">Collapse</span>}
        </button>
        {/* Mobile: close button */}
        <button
          onClick={() => setMobileOpen(false)}
          className="w-full flex md:hidden items-center justify-center gap-2 px-3 py-2 rounded-lg text-ct-text-dim hover:text-ct-text-muted hover:bg-ct-bg-hover transition-colors"
        >
          <ChevronLeft size={16} />
          <span className="text-xs">Close</span>
        </button>
        <div className={cn('text-center text-[10px] text-ct-text-dim mt-1', collapsed && 'md:hidden')}>
          v0.1.0
        </div>
      </div>
    </aside>
  );
}
