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
  Ticker,
  ActivityEntry,
  Signal,
  IndicatorData,
  BacktestRequest,
  BacktestResult,
  AlertConfig,
  CreateAlertRequest,
  AlertHistory,
  ScreenerResponse,
  CMCFeedStatus,
} from './types';

const API_BASE = '/api/v1';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    let msg = `API error: ${res.status} ${res.statusText}`;
    if (body?.detail) {
      if (typeof body.detail === 'string') {
        msg = body.detail;
      } else if (Array.isArray(body.detail)) {
        msg = body.detail.map((e: { msg?: string; loc?: string[] }) =>
          e.msg ? `${e.loc?.slice(-1)?.[0] ?? 'field'}: ${e.msg}` : JSON.stringify(e)
        ).join('; ');
      }
    }
    throw new Error(msg);
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
  addPairsBatch: (symbols: string[]) =>
    apiFetch<TradingPair[]>('/trading/pairs/batch', { method: 'POST', body: JSON.stringify({ symbols }) }),
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
  getTicker: (symbol: string) =>
    apiFetch<Ticker>(`/trading/ticker/${encodeURIComponent(symbol)}`),
  activityLog: () => apiFetch<ActivityEntry[]>('/trading/activity'),
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

  // ---- Market Screener ----
  screenerGainers: (limit = 20) =>
    apiFetch<ScreenerResponse>(`/screener/gainers?limit=${limit}`),
  screenerLosers: (limit = 20) =>
    apiFetch<ScreenerResponse>(`/screener/losers?limit=${limit}`),
  screenerSearch: (params?: {
    sort_by?: string; sort_dir?: string; limit?: number;
    min_market_cap?: number; min_volume?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.sort_by) qs.set('sort_by', params.sort_by);
    if (params?.sort_dir) qs.set('sort_dir', params.sort_dir);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.min_market_cap) qs.set('min_market_cap', String(params.min_market_cap));
    if (params?.min_volume) qs.set('min_volume', String(params.min_volume));
    const q = qs.toString();
    return apiFetch<ScreenerResponse>(`/screener/search${q ? `?${q}` : ''}`);
  },
  cmcFeedStatus: () => apiFetch<CMCFeedStatus>('/screener/status'),
};
