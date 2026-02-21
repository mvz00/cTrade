import type {
  HealthResponse,
  DashboardSummary,
  SystemStatus,
  EquityPoint,
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
  TradingPair,
  Order,
  PlaceOrderRequest,
  Position,
  Portfolio,
  EngineStatus,
  Signal,
  IndicatorData,
  BacktestRequest,
  BacktestResult,
  AlertConfig,
  CreateAlertRequest,
  AlertHistory,
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
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  health: () => apiFetch<HealthResponse>('/health'),
  dashboardSummary: () => apiFetch<DashboardSummary>('/dashboard/summary'),
  systemStatus: () => apiFetch<SystemStatus>('/dashboard/status'),
  equityCurve: () => apiFetch<EquityPoint[]>('/dashboard/equity-curve'),
  recentTrades: () => apiFetch<Position[]>('/dashboard/recent-trades'),

  tradingMode: () => apiFetch<TradingModeResponse>('/config/trading-mode'),
  strategyConfig: () => apiFetch<StrategyConfig>('/config/strategy'),
  riskConfig: () => apiFetch<RiskConfig>('/config/risk'),
  updateTradingMode: (body: TradingModeUpdate) =>
    apiFetch<TradingModeResponse>('/config/trading-mode', { method: 'PUT', body: JSON.stringify(body) }),
  updateStrategy: (body: StrategyConfigUpdate) =>
    apiFetch<StrategyConfig>('/config/strategy', { method: 'PUT', body: JSON.stringify(body) }),
  updateRisk: (body: RiskConfigUpdate) =>
    apiFetch<RiskConfig>('/config/risk', { method: 'PUT', body: JSON.stringify(body) }),

  listExchanges: () => apiFetch<ExchangeInfo[]>('/exchanges/'),
  availableExchanges: () => apiFetch<AvailableExchange[]>('/exchanges/available'),
  addExchange: (body: ExchangeAddRequest) =>
    apiFetch<ExchangeInfo>('/exchanges/', { method: 'POST', body: JSON.stringify(body) }),
  deleteExchange: (id: string) => apiFetch<void>(`/exchanges/${id}`, { method: 'DELETE' }),
  testExchange: (id: string) => apiFetch<ExchangeTestResult>(`/exchanges/${id}/test`, { method: 'POST' }),

  listPairs: () => apiFetch<TradingPair[]>('/trading/pairs'),
  availablePairs: () => apiFetch<string[]>('/trading/available-pairs'),
  addPair: (symbol: string) =>
    apiFetch<TradingPair>('/trading/pairs', { method: 'POST', body: JSON.stringify({ symbol }) }),
  removePair: (symbol: string) =>
    apiFetch<void>(`/trading/pairs/${encodeURIComponent(symbol)}`, { method: 'DELETE' }),
  listOrders: (status?: string) =>
    apiFetch<Order[]>(`/trading/orders${status ? `?status=${status}` : ''}`),
  placeOrder: (body: PlaceOrderRequest) =>
    apiFetch<Order>('/trading/orders', { method: 'POST', body: JSON.stringify(body) }),
  listPositions: (status?: string) =>
    apiFetch<Position[]>(`/trading/positions${status ? `?status=${status}` : ''}`),
  closePosition: (id: string) =>
    apiFetch<Order>(`/trading/positions/${id}/close`, { method: 'POST' }),
  portfolio: () => apiFetch<Portfolio>('/trading/portfolio'),
  engineStatus: () => apiFetch<EngineStatus>('/trading/engine/status'),
  startEngine: (interval?: number) =>
    apiFetch<EngineStatus>('/trading/engine/start', { method: 'POST', body: interval ? JSON.stringify({ interval }) : '{}' }),
  stopEngine: () => apiFetch<EngineStatus>('/trading/engine/stop', { method: 'POST' }),

  listSignals: (params?: { symbol?: string; action?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.symbol) qs.set('symbol', params.symbol);
    if (params?.action) qs.set('action', params.action);
    if (params?.limit) qs.set('limit', String(params.limit));
    const q = qs.toString();
    return apiFetch<Signal[]>(`/signals/${q ? `?${q}` : ''}`);
  },
  latestSignal: (symbol: string) => apiFetch<Signal | null>(`/signals/${encodeURIComponent(symbol)}/latest`),
  indicators: (symbol: string) => apiFetch<IndicatorData | null>(`/signals/${encodeURIComponent(symbol)}/indicators`),

  runBacktest: (body: BacktestRequest) =>
    apiFetch<BacktestResult>('/backtest/run', { method: 'POST', body: JSON.stringify(body) }),
  backtestResults: () => apiFetch<BacktestResult[]>('/backtest/results'),

  listAlerts: () => apiFetch<AlertConfig[]>('/alerts/'),
  createAlert: (body: CreateAlertRequest) =>
    apiFetch<AlertConfig>('/alerts/', { method: 'POST', body: JSON.stringify(body) }),
  deleteAlert: (id: string) => apiFetch<void>(`/alerts/${id}`, { method: 'DELETE' }),
  toggleAlert: (id: string) => apiFetch<AlertConfig>(`/alerts/${id}/toggle`, { method: 'PUT' }),
  alertHistory: () => apiFetch<AlertHistory[]>('/alerts/history'),
};
