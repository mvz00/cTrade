import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppLayout } from '@/components/layout/AppLayout';
import { DashboardPage } from '@/pages/Dashboard/DashboardPage';
import { TradingPage } from '@/pages/Trading/TradingPage';
import { ConfigPage } from '@/pages/Configuration/ConfigPage';
import { SignalsPage } from '@/pages/Signals/SignalsPage';
import { BacktestPage } from '@/pages/Backtesting/BacktestPage';
import { AlertsPage } from '@/pages/Alerts/AlertsPage';
import { AccountPage } from '@/pages/Account/AccountPage';
import { ScreenerPage } from '@/pages/Screener/ScreenerPage';
import { IntelligencePage } from '@/pages/Intelligence/IntelligencePage';
import { LoginPage } from '@/pages/Login/LoginPage';
import { ToastProvider } from '@/components/ui/Toast';
import { AuthProvider, useAuth } from '@/contexts/AuthContext';
import { ROUTES } from '@/lib/constants';
import type { ReactNode } from 'react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
    },
  },
});

/** Redirect to /login if not authenticated. */
function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} replace />;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          {/* Public route */}
          <Route path={ROUTES.LOGIN} element={<LoginPage />} />

          {/* Protected routes */}
          <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
            <Route index element={<Navigate to={ROUTES.DASHBOARD} replace />} />
            <Route path={ROUTES.DASHBOARD} element={<DashboardPage />} />
            <Route path={ROUTES.TRADING} element={<TradingPage />} />
            <Route path={ROUTES.CONFIGURATION} element={<ConfigPage />} />
            <Route path={ROUTES.SIGNALS} element={<SignalsPage />} />
            <Route path={ROUTES.INTELLIGENCE} element={<IntelligencePage />} />
            <Route path={ROUTES.SCREENER} element={<ScreenerPage />} />
            <Route path={ROUTES.BACKTESTING} element={<BacktestPage />} />
            <Route path={ROUTES.ALERTS} element={<AlertsPage />} />
            <Route path={ROUTES.ACCOUNT} element={<AccountPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
