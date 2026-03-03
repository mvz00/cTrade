export const ROUTES = {
  LOGIN: '/login',
  DASHBOARD: '/dashboard',
  TRADING: '/trading',
  CONFIGURATION: '/configuration',
  CONNECTIONS: '/connections',
  SIGNALS: '/signals',
  INTELLIGENCE: '/intelligence',
  SCREENER: '/screener',
  ALERTS: '/alerts',
  LOGGING: '/logging',
  ACCOUNT: '/account',
} as const;

export const REFETCH_INTERVALS = {
  HEALTH: 10_000,
  DASHBOARD: 10_000,
  CONFIG: 30_000,
  CONNECTIONS: 30_000,
  TRADING: 5_000,
  SIGNALS: 10_000,
  INTELLIGENCE: 15_000,
  SCREENER: 15_000,
} as const;
