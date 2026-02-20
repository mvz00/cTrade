import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AppLayout } from '@/components/layout/AppLayout';
import { DashboardPage } from '@/pages/Dashboard/DashboardPage';
import { TradingPage } from '@/pages/Trading/TradingPage';
import { ConfigPage } from '@/pages/Configuration/ConfigPage';
import { SignalsPage } from '@/pages/Signals/SignalsPage';
import { BacktestPage } from '@/pages/Backtesting/BacktestPage';
import { AlertsPage } from '@/pages/Alerts/AlertsPage';
import { ToastProvider } from '@/components/ui/Toast';
import { ROUTES } from '@/lib/constants';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 5_000,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to={ROUTES.DASHBOARD} replace />} />
            <Route path={ROUTES.DASHBOARD} element={<DashboardPage />} />
            <Route path={ROUTES.TRADING} element={<TradingPage />} />
            <Route path={ROUTES.CONFIGURATION} element={<ConfigPage />} />
            <Route path={ROUTES.SIGNALS} element={<SignalsPage />} />
            <Route path={ROUTES.BACKTESTING} element={<BacktestPage />} />
            <Route path={ROUTES.ALERTS} element={<AlertsPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
