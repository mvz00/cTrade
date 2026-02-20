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

export interface TradingModeResponse {
  mode: 'paper' | 'live';
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

export interface Signal {
  id: string;
  pair_symbol: string;
  action: 'BUY' | 'SELL' | 'HOLD';
  confidence: number;
  technical_score: number | null;
  sentiment_score: number | null;
  onchain_score: number | null;
  strategy_name: string;
  created_at: string;
}

export interface Position {
  id: string;
  pair_symbol: string;
  side: 'long' | 'short';
  status: 'open' | 'closed';
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  stop_loss: number | null;
  take_profit: number | null;
  realized_pnl: number | null;
  realized_pnl_pct: number | null;
  strategy_name: string;
  opened_at: string;
  closed_at: string | null;
}

export interface Order {
  id: string;
  pair_symbol: string;
  trading_mode: 'paper' | 'live';
  order_type: 'market' | 'limit' | 'stop_limit';
  side: 'buy' | 'sell';
  quantity: number;
  price: number | null;
  status: string;
  filled_quantity: number;
  avg_fill_price: number | null;
  created_at: string;
}

// ---- Mutation request types ----

export interface TradingModeUpdate {
  mode: 'paper' | 'live';
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
