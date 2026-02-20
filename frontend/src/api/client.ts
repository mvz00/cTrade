import type {
  HealthResponse,
  DashboardSummary,
  TradingModeResponse,
  TradingModeUpdate,
  StrategyConfig,
  StrategyConfigUpdate,
  RiskConfig,
  RiskConfigUpdate,
  ExchangeInfo,
  ExchangeAddRequest,
  ExchangeTestResult,
  AvailableExchange,
} from './types';

const API_BASE = '/api/v1';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `API error: ${res.status} ${res.statusText}`);
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  // Read
  health: () => apiFetch<HealthResponse>('/health'),
  dashboardSummary: () => apiFetch<DashboardSummary>('/dashboard/summary'),
  tradingMode: () => apiFetch<TradingModeResponse>('/config/trading-mode'),
  strategyConfig: () => apiFetch<StrategyConfig>('/config/strategy'),
  riskConfig: () => apiFetch<RiskConfig>('/config/risk'),

  // Config mutations
  updateTradingMode: (body: TradingModeUpdate) =>
    apiFetch<TradingModeResponse>('/config/trading-mode', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  updateStrategy: (body: StrategyConfigUpdate) =>
    apiFetch<StrategyConfig>('/config/strategy', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),
  updateRisk: (body: RiskConfigUpdate) =>
    apiFetch<RiskConfig>('/config/risk', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  // Exchanges
  listExchanges: () => apiFetch<ExchangeInfo[]>('/exchanges/'),
  availableExchanges: () => apiFetch<AvailableExchange[]>('/exchanges/available'),
  addExchange: (body: ExchangeAddRequest) =>
    apiFetch<ExchangeInfo>('/exchanges/', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteExchange: (id: string) =>
    apiFetch<void>(`/exchanges/${id}`, { method: 'DELETE' }),
  testExchange: (id: string) =>
    apiFetch<ExchangeTestResult>(`/exchanges/${id}/test`, { method: 'POST' }),
};
