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
  ExchangeUpdateRequest,
  ExchangeTestResult,
  AvailableExchange,
  TradingPair,
  Order,
  PlaceOrderRequest,
  QuickBuyRequest,
  QuickBuyResponse,
  Position,
  Portfolio,
  EngineStatus,
  Ticker,
  ActivityEntry,
  Signal,
  IndicatorData,
  EmailConfig,
  EmailConfigUpdate,
  AlertConfig,
  CreateAlertRequest,
  AlertHistory,
  ScreenerResponse,
  CMCFeedStatus,
  SentimentScore,
  SentimentAllScores,
  SentimentTimeline,
  SentimentFeedStatus,
  OnChainScore,
  OnChainAllScores,
  OnChainMetrics,
  OnChainFeedStatus,
  LoginRequest,
  TokenResponse,
  ChangePasswordRequest,
  ChangePasswordResponse,
  ConnectionsResponse,
  ConnectionTestResult,
  ConnectionCredentialsRequest,
  PortfolioHistorySeries,
  SymbolCandleSeries,
  RecommendationsResponse,
  LogHistoryResponse,
  LoggingConfig,
  LoggingConfigUpdate,
  PurgeLogsResponse,
} from './types';

const API_BASE = '/api/v1';
const TOKEN_KEY = 'ctrade_token';

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init?.headers as Record<string, string> | undefined),
  };

  // Inject Bearer token if available
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  // On 401 from a non-login endpoint, clear token and redirect to login
  if (res.status === 401 && !path.startsWith('/auth/login')) {
    localStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(new Event('ctrade:unauthorized'));
    throw new Error('Session expired — please log in again');
  }

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
  // ---- Auth ----
  login: (body: LoginRequest) =>
    apiFetch<TokenResponse>('/auth/login', { method: 'POST', body: JSON.stringify(body) }),
  changePassword: (body: ChangePasswordRequest) =>
    apiFetch<ChangePasswordResponse>('/auth/change-password', { method: 'POST', body: JSON.stringify(body) }),

  health: () => apiFetch<HealthResponse>('/health'),
  dashboardSummary: () => apiFetch<DashboardSummary>('/dashboard/summary'),
  systemStatus: () => apiFetch<SystemStatus>('/dashboard/status'),
  equityCurve: () => apiFetch<EquityPoint[]>('/dashboard/equity-curve'),
  portfolioHistory: (range: string = '7d') =>
    apiFetch<PortfolioHistorySeries[]>(`/dashboard/portfolio-history?range=${range}`),
  recentTrades: () => apiFetch<Position[]>('/dashboard/recent-trades'),
  recommendations: () => apiFetch<RecommendationsResponse>('/dashboard/recommendations'),

  tradingMode: () => apiFetch<TradingModeResponse>('/config/trading-mode'),
  strategyConfig: () => apiFetch<StrategyConfig>('/config/strategy'),
  riskConfig: () => apiFetch<RiskConfig>('/config/risk'),
  updateTradingMode: (body: TradingModeUpdate) =>
    apiFetch<TradingModeResponse>('/config/trading-mode', { method: 'PUT', body: JSON.stringify(body) }),
  updateStrategy: (body: StrategyConfigUpdate) =>
    apiFetch<StrategyConfig>('/config/strategy', { method: 'PUT', body: JSON.stringify(body) }),
  updateRisk: (body: RiskConfigUpdate) =>
    apiFetch<RiskConfig>('/config/risk', { method: 'PUT', body: JSON.stringify(body) }),
  emailConfig: () => apiFetch<EmailConfig>('/config/email'),
  updateEmailConfig: (body: EmailConfigUpdate) =>
    apiFetch<EmailConfig>('/config/email', { method: 'PUT', body: JSON.stringify(body) }),
  testEmail: () =>
    apiFetch<{ success: boolean; error: string }>('/config/email/test', { method: 'POST' }),

  listExchanges: () => apiFetch<ExchangeInfo[]>('/exchanges/'),
  availableExchanges: () => apiFetch<AvailableExchange[]>('/exchanges/available'),
  addExchange: (body: ExchangeAddRequest) =>
    apiFetch<ExchangeInfo>('/exchanges/', { method: 'POST', body: JSON.stringify(body) }),
  updateExchange: (id: string, body: ExchangeUpdateRequest) =>
    apiFetch<ExchangeInfo>(`/exchanges/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteExchange: (id: string) => apiFetch<void>(`/exchanges/${id}`, { method: 'DELETE' }),
  toggleExchange: (id: string) =>
    apiFetch<ExchangeInfo>(`/exchanges/${id}/toggle`, { method: 'PATCH' }),
  testExchange: (id: string) => apiFetch<ExchangeTestResult>(`/exchanges/${id}/test`, { method: 'POST' }),

  listPairs: () => apiFetch<TradingPair[]>('/trading/pairs'),
  availablePairs: () => apiFetch<string[]>('/trading/available-pairs'),
  addPair: (symbol: string) =>
    apiFetch<TradingPair>('/trading/pairs', { method: 'POST', body: JSON.stringify({ symbol }) }),
  addPairsBatch: (symbols: string[]) =>
    apiFetch<TradingPair[]>('/trading/pairs/batch', { method: 'POST', body: JSON.stringify({ symbols }) }),
  removePair: (symbol: string) =>
    apiFetch<void>(`/trading/pairs/${encodeURIComponent(symbol)}`, { method: 'DELETE' }),
  removeAllPairs: () =>
    apiFetch<{ removed: number }>('/trading/pairs', { method: 'DELETE' }),
  listOrders: (status?: string) =>
    apiFetch<Order[]>(`/trading/orders${status ? `?status=${status}` : ''}`),
  placeOrder: (body: PlaceOrderRequest) =>
    apiFetch<Order>('/trading/orders', { method: 'POST', body: JSON.stringify(body) }),
  quickBuy: (body: QuickBuyRequest) =>
    apiFetch<QuickBuyResponse>('/trading/quick-buy', { method: 'POST', body: JSON.stringify(body) }),
  listPositions: (status?: string) =>
    apiFetch<Position[]>(`/trading/positions${status ? `?status=${status}` : ''}`),
  closePosition: (id: string) =>
    apiFetch<Order>(`/trading/positions/${id}/close`, { method: 'POST' }),
  closeAllPositions: () =>
    apiFetch<{ closed: number; failed: number; errors: string[] }>('/trading/positions/close-all', { method: 'POST' }),
  portfolio: () => apiFetch<Portfolio>('/trading/portfolio'),
  getTicker: (symbol: string) =>
    apiFetch<Ticker>(`/trading/ticker/${encodeURIComponent(symbol)}`),
  activityLog: () => apiFetch<ActivityEntry[]>('/trading/activity'),
  clearActivity: () => apiFetch<{ cleared: number }>('/trading/activity/clear', { method: 'POST' }),
  engineStatus: () => apiFetch<EngineStatus>('/trading/engine/status'),
  startEngine: (interval?: number) =>
    apiFetch<EngineStatus>('/trading/engine/start', { method: 'POST', body: interval ? JSON.stringify({ interval }) : '{}' }),
  stopEngine: () => apiFetch<EngineStatus>('/trading/engine/stop', { method: 'POST' }),
  resetPaperEngine: () =>
    apiFetch<{ success: boolean; balance: number; message: string }>('/trading/engine/reset', { method: 'POST' }),

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


  listAlerts: () => apiFetch<AlertConfig[]>('/alerts/'),
  createAlert: (body: CreateAlertRequest) =>
    apiFetch<AlertConfig>('/alerts/', { method: 'POST', body: JSON.stringify(body) }),
  deleteAlert: (id: string) => apiFetch<void>(`/alerts/${id}`, { method: 'DELETE' }),
  toggleAlert: (id: string) => apiFetch<AlertConfig>(`/alerts/${id}/toggle`, { method: 'PUT' }),
  alertHistory: () => apiFetch<AlertHistory[]>('/alerts/history'),

  // ---- Sentiment ----
  sentimentScores: () => apiFetch<SentimentAllScores>('/sentiment/scores'),
  sentimentScore: (symbol: string) => apiFetch<SentimentScore>(`/sentiment/${encodeURIComponent(symbol)}/score`),
  sentimentTimeline: (symbol: string, limit = 20) =>
    apiFetch<SentimentTimeline>(`/sentiment/${encodeURIComponent(symbol)}/timeline?limit=${limit}`),
  sentimentStatus: () => apiFetch<SentimentFeedStatus>('/sentiment/status'),

  // ---- On-Chain ----
  onchainScores: () => apiFetch<OnChainAllScores>('/onchain/scores'),
  onchainScore: (symbol: string) => apiFetch<OnChainScore>(`/onchain/${encodeURIComponent(symbol)}/score`),
  onchainMetrics: (symbol: string, limit = 20) =>
    apiFetch<OnChainMetrics>(`/onchain/${encodeURIComponent(symbol)}/metrics?limit=${limit}`),
  onchainStatus: () => apiFetch<OnChainFeedStatus>('/onchain/status'),

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

  // ---- Position Candles ----
  getCandles: (symbols: string[], timeframe: string, limit: number) =>
    apiFetch<SymbolCandleSeries[]>(
      `/trading/candles?symbols=${encodeURIComponent(symbols.join(','))}&timeframe=${timeframe}&limit=${limit}`,
    ),

  // ---- Connections ----
  connections: () => apiFetch<ConnectionsResponse>('/connections'),
  testConnection: (name: string) =>
    apiFetch<ConnectionTestResult>(`/connections/${encodeURIComponent(name)}/test`, { method: 'POST' }),
  updateConnectionCredentials: (name: string, body: ConnectionCredentialsRequest) =>
    apiFetch<{ message: string }>(`/connections/${encodeURIComponent(name)}/credentials`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  // ---- Logging ----
  logHistory: (params?: { level?: string; search?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.level) qs.set('level', params.level);
    if (params?.search) qs.set('search', params.search);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return apiFetch<LogHistoryResponse>(`/logging/history${q ? `?${q}` : ''}`);
  },
  loggingConfig: () => apiFetch<LoggingConfig>('/logging/config'),
  updateLoggingConfig: (body: LoggingConfigUpdate) =>
    apiFetch<LoggingConfig>('/logging/config', { method: 'PUT', body: JSON.stringify(body) }),
  purgeLogs: () =>
    apiFetch<PurgeLogsResponse>('/logging/purge', { method: 'POST' }),
};
