import { Outlet } from 'react-router-dom';
import { SidebarProvider, useSidebar } from '@/contexts/SidebarContext';
import { cn } from '@/lib/cn';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { BottomTabBar } from './BottomTabBar';

function AppLayoutInner() {
  const { collapsed, mobileOpen, setMobileOpen } = useSidebar();

  return (
    <div className="min-h-screen bg-ct-bg">
      <Sidebar />

      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-10 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <div
        className={cn(
          'flex flex-col min-h-screen transition-all duration-200',
          collapsed ? 'md:ml-16' : 'md:ml-56',
        )}
      >
        <TopBar />
        <main className="flex-1 p-4 md:p-6 pb-24 md:pb-6 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* Bottom tab bar — mobile only */}
      <BottomTabBar />
    </div>
  );
}

export function AppLayout() {
  return (
    <SidebarProvider>
      <AppLayoutInner />
    </SidebarProvider>
  );
}
