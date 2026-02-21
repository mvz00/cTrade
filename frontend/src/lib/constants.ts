export const ROUTES = {
  DASHBOARD: '/dashboard',
  TRADING: '/trading',
  CONFIGURATION: '/configuration',
  SIGNALS: '/signals',
  SCREENER: '/screener',
  BACKTESTING: '/backtesting',
  ALERTS: '/alerts',
} as const;

export const REFETCH_INTERVALS = {
  HEALTH: 10_000,
  DASHBOARD: 10_000,
  CONFIG: 30_000,
  TRADING: 5_000,
  SIGNALS: 10_000,
  SCREENER: 15_000,
} as const;
