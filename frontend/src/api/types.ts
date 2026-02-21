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
  entry_confidence_threshold: number;
  exit_confidence_threshold: number;
}

export interface RiskConfig {
  max_position_pct: number;
  max_daily_loss_pct: number;
  max_drawdown_pct: number;
  default_stop_loss_pct: number;
  default_take_profit_pct: number;
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

export interface BacktestRequest {
  symbol: string;
  initial_capital: number;
  num_candles: number;
  timeframe: string;
  entry_threshold: number;
  exit_threshold: number;
}

export interface BacktestTrade {
  pair_symbol: string;
  side: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  pnl: number;
  pnl_pct: number;
  entry_time: string;
  exit_time: string;
}

export interface BacktestResult {
  id: string;
  symbol: string;
  initial_capital: number;
  final_value: number;
  total_return_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  equity_curve: { timestamp: string; value: number }[];
  trade_log: BacktestTrade[];
  created_at: string;
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
}

export interface StrategyConfigUpdate {
  active_strategy?: string;
  technical_weight?: number;
  sentiment_weight?: number;
  onchain_weight?: number;
  entry_confidence_threshold?: number;
  exit_confidence_threshold?: number;
}

export interface RiskConfigUpdate {
  max_position_pct?: number;
  max_daily_loss_pct?: number;
  max_drawdown_pct?: number;
  default_stop_loss_pct?: number;
  default_take_profit_pct?: number;
}

export interface ExchangeAddRequest {
  name: string;
  api_key: string;
  api_secret: string;
  passphrase?: string;
}

export interface ExchangeInfo {
  id: string;
  name: string;
  exchange_type: string;
  is_active: boolean;
  created_at: string;
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
