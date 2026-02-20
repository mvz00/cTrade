import type {
  HealthResponse,
  DashboardSummary,
  TradingModeResponse,
  StrategyConfig,
  RiskConfig,
} from './types';

const API_BASE = '/api/v1';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  health: () => apiFetch<HealthResponse>('/health'),
  dashboardSummary: () => apiFetch<DashboardSummary>('/dashboard/summary'),
  tradingMode: () => apiFetch<TradingModeResponse>('/config/trading-mode'),
  strategyConfig: () => apiFetch<StrategyConfig>('/config/strategy'),
  riskConfig: () => apiFetch<RiskConfig>('/config/risk'),
};
