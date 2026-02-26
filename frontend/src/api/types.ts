// ---- Auth ----

export interface LoginRequest {
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in_minutes: number;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
}

export interface ChangePasswordResponse {
  message: string;
  new_password_hash: string;
}

// ---- Core ----

export interface HealthResponse {
  status: 'ok' | 'error';
  service: string;
  timestamp: string;
}

export interface DashboardSummary {
  total_value_usd: number;
  daily_pnl: number;
  open_positions: number;
  active_feeds: number;
  trading_mode: 'paper' | 'live';
}

export interface SystemStatus {
  api_server: { status: string; label: string };
  database: { status: string; label: string };
  exchange: { status: string; label: string };
  trading_engine: { status: string; label: string };
  event_bus: { status: string; label: string };
  watched_pairs: number;
}

export interface EquityPoint {
  timestamp: string;
  total_value: number;
  cash: number;
  positions_value: number;
}

export interface TradingModeResponse {
  mode: 'paper' | 'live';
  max_order_usdt?: number;
  max_open_positions?: number;
  default_quote_currency?: string;
  order_timeout_seconds?: number;
}

export interface ActivityEntry {
  time: string;
  type: 'signal' | 'buy' | 'sell' | 'sl' | 'tp' | 'info';
  pair: string;
  message: string;
  details: Record<string, any>;
}

export interface StrategyConfig {
  active_strategy: string;
  technical_weight: number;
  sentiment_weight: number;
  onchain_weight: number;
  derivatives_weight: number;
  market_sentiment_weight: number;
  cvd_weight: number;
  social_velocity_weight: number;
  screener_weight: number;
  screener_priority: number;
  intelligence_priority: number;
  signals_priority: number;
  strategy_mode: string;
  quicktrade_min_1h_change_pct: number;
  risk_appetite: number;
  entry_confidence_threshold: number;
  exit_confidence_threshold: number;
  min_hold_minutes: number;
}

export interface RiskConfig {
  max_position_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  default_stop_loss_pct: number;
  default_take_profit_pct: number;
  sl_rebuy_delay_hours: number;
}

export interface TradingPair {
  symbol: string;
  is_active: boolean;
}

export interface Order {
  id: string;
  signal_id: string | null;
  pair_symbol: string;
  trading_mode: string;
  order_type: string;
  side: string;
  quantity: number;
  price: number | null;
  status: string;
  filled_quantity: number;
  avg_fill_price: number | null;
  fee: number;
  fee_currency: string;
  error_message: string | null;
  created_at: string;
  filled_at: string | null;
}

export interface Position {
  id: string;
  pair_symbol: string;
  exchange_name?: string;
  side: string;
  status: string;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  stop_loss: number | null;
  take_profit: number | null;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  current_price?: number | null;
  fees_total: number;
  strategy_name: string;
  opened_at: string;
  closed_at: string | null;
  justification?: string;
  outlook_1h?: number | null;
  outlook_24h?: number | null;
  outlook_7d?: number | null;
}

export interface Portfolio {
  cash_balance: Record<string, number>;
  total_value_usd: number;
  positions_value: number;
  unrealized_pnl: number;
  realized_pnl: number;
  daily_pnl: number;
  open_positions: number;
  closed_positions: number;
  total_orders: number;
}

export interface EngineStatus {
  running: boolean;
  tick_count: number;
  last_tick: string | null;
  interval_seconds: number;
}

export interface Ticker {
  symbol: string;
  last_price: number;
  bid: number;
  ask: number;
  high_24h: number;
  low_24h: number;
  volume_24h: number;
  change_pct_24h: number;
}

export interface PlaceOrderRequest {
  symbol: string;
  side: 'buy' | 'sell';
  order_type: 'market' | 'limit';
  quantity: number;
  price?: number;
}

export interface QuickBuyRequest {
  symbol: string;
  amount_usdt?: number;
}

export interface QuickBuyResponse {
  success: boolean;
  order_id: string | null;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  amount_usdt: number;
  stop_loss: number | null;
  take_profit: number | null;
  status: string;
  error: string | null;
}

export interface Signal {
  id: string;
  pair_symbol: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  technical_score: number | null;
  sentiment_score: number | null;
  onchain_score: number | null;
  strategy_name: string;
  contributing_factors: Record<string, any>;
  created_at: string;
}

export interface IndicatorData {
  symbol: string;
  indicators: Record<string, any>;
  timestamp: string;
}


export interface EmailConfig {
  enabled: boolean;
  api_key: string;  // masked as "••••••" when set
  from_address: string;
  to_address: string;
  notify_on_buy: boolean;
  notify_on_sell: boolean;
}

export interface EmailConfigUpdate {
  enabled?: boolean;
  api_key?: string;
  from_address?: string;
  to_address?: string;
  notify_on_buy?: boolean;
  notify_on_sell?: boolean;
}

export interface AlertConfig {
  id: string;
  alert_type: string;
  symbol: string;
  value: number;
  message: string | null;
  is_active: boolean;
  created_at: string;
}

export interface CreateAlertRequest {
  alert_type: string;
  symbol: string;
  value: number;
  message?: string;
}

export interface AlertHistory {
  id: string;
  alert_id: string;
  alert_type: string;
  symbol: string;
  message: string;
  triggered_value: number;
  triggered_at: string;
}

export interface TradingModeUpdate {
  mode?: 'paper' | 'live';
  max_order_usdt?: number;
  max_open_positions?: number;
  default_quote_currency?: string;
  order_timeout_seconds?: number;
}

export interface StrategyConfigUpdate {
  active_strategy?: string;
  technical_weight?: number;
  sentiment_weight?: number;
  onchain_weight?: number;
  derivatives_weight?: number;
  market_sentiment_weight?: number;
  cvd_weight?: number;
  social_velocity_weight?: number;
  screener_weight?: number;
  screener_priority?: number;
  intelligence_priority?: number;
  signals_priority?: number;
  strategy_mode?: string;
  quicktrade_min_1h_change_pct?: number;
  risk_appetite?: number;
  entry_confidence_threshold?: number;
  exit_confidence_threshold?: number;
  min_hold_minutes?: number;
}

export interface RiskConfigUpdate {
  max_position_pct?: number;
  max_daily_loss_pct?: number;
  max_drawdown_pct?: number;
  default_stop_loss_pct?: number;
  default_take_profit_pct?: number;
  sl_rebuy_delay_hours?: number;
}

export interface ExchangeAddRequest {
  name: string;
  api_key: string;
  api_secret: string;
  passphrase?: string;
  quote_currencies?: string[];
  max_portfolio_pct?: number;
  risk_overrides?: Partial<RiskConfig>;
}

export interface ExchangeUpdateRequest {
  api_key?: string;
  api_secret?: string;
  passphrase?: string;
  quote_currencies?: string[];
  max_portfolio_pct?: number;
  risk_overrides?: Partial<RiskConfig>;
}

export interface ExchangeInfo {
  id: string;
  name: string;
  exchange_type: string;
  is_active: boolean;
  created_at: string;
  quote_currencies: string[];
  max_portfolio_pct: number;
  risk_overrides: Partial<RiskConfig>;
}

export interface ExchangeTestResult {
  success: boolean;
  message: string;
}

export interface AvailableExchange {
  name: string;
  exchange_type: string;
  default_fee_pct: number;
  supports_websocket: boolean;
}

// ---- Sentiment ----

export interface SentimentScore {
  symbol: string;
  score: number;
  signal: string;
  data_points: number;
}

export interface SentimentAllScores {
  scores: Record<string, number>;
  assets_tracked: number;
}

export interface SentimentDataPoint {
  source: string;
  text: string;
  label: string;
  score: number;
  model: string;
  timestamp: string;
}

export interface SentimentTimeline {
  symbol: string;
  data_points: SentimentDataPoint[];
}

export interface SentimentFeedStatus {
  enabled: boolean;
  healthy: boolean;
  last_fetch: string | null;
  data_points: number;
  assets_tracked: number;
  classifier_model: string;
  using_fallback: boolean;
}

// ---- On-Chain ----

export interface OnChainScore {
  symbol: string;
  score: number;
  signal: string;
  metrics_count: number;
}

export interface OnChainAllScores {
  scores: Record<string, number>;
  assets_tracked: number;
}

export interface OnChainMetric {
  metric_name: string;
  metric_value: number;
  source: string;
  timestamp: string;
}

export interface OnChainMetrics {
  symbol: string;
  metrics: OnChainMetric[];
}

export interface OnChainFeedStatus {
  enabled: boolean;
  healthy: boolean;
  last_fetch: string | null;
  metrics_count: number;
  assets_tracked: number;
}

// ---- Market Screener (CoinMarketCap) ----

export interface ScreenerCoin {
  symbol: string;
  name: string;
  cmc_rank: number;
  market_cap: number;
  volume_24h: number;
  pct_change_1h: number;
  pct_change_24h: number;
  pct_change_7d: number;
  volume_change_24h: number;
  momentum_score: number | null;
}

export interface ScreenerResponse {
  coins: ScreenerCoin[];
  last_updated: string | null;
  source: string;
}

export interface CMCFeedStatus {
  enabled: boolean;
  healthy: boolean;
  last_fetch: string | null;
  listings_count: number;
}

// ---- Connections ----

export interface CredentialFieldDef {
  key: string;
  label: string;
  is_secret: boolean;
}

export interface ConnectionInfo {
  name: string;
  feed_name: string;
  base_urls: string[];
  requires_key: boolean;
  key_configured: boolean;
  feed_enabled: boolean;
  feed_healthy: boolean;
  status: 'untested' | 'ok' | 'error' | 'disabled';
  last_checked: string | null;
  error_message: string | null;
  description: string;
  credential_fields: CredentialFieldDef[];
}

export interface ConnectionsResponse {
  connections: ConnectionInfo[];
}

export interface ConnectionTestResult {
  name: string;
  success: boolean;
  latency_ms: number;
  message: string;
  tested_at: string;
}

export interface ConnectionCredentialsRequest {
  credentials: Record<string, string>;
}

// ---- Position Candles (price chart) ----

export interface CandlePoint {
  time: string;
  close: number;
}

export interface SymbolCandleSeries {
  symbol: string;
  candles: CandlePoint[];
}

// ---- Portfolio History (per-exchange equity curve) ----

export interface PortfolioHistoryPoint {
  timestamp: string;
  total_value_usd: number;
}

export interface PortfolioHistorySeries {
  exchange_id: string;
  exchange_name: string;
  points: PortfolioHistoryPoint[];
}
