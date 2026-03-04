import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useTradingMode } from '@/api/hooks/useConfig';
import { formatCurrency } from '@/lib/formatters';

interface CurrencyContextValue {
  /** The configured quote currency code, e.g. "AUD", "USDT" */
  quoteCurrency: string;
  /** Format a numeric value in the configured currency */
  formatMoney: (value: number) => string;
}

const CurrencyContext = createContext<CurrencyContextValue>({
  quoteCurrency: 'AUD',
  formatMoney: (v: number) => formatCurrency(v, 'AUD'),
});

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const { data: mode } = useTradingMode();
  const quoteCurrency = mode?.default_quote_currency ?? 'AUD';

  const value = useMemo<CurrencyContextValue>(
    () => ({
      quoteCurrency,
      formatMoney: (v: number) => formatCurrency(v, quoteCurrency),
    }),
    [quoteCurrency],
  );

  return (
    <CurrencyContext.Provider value={value}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency() {
  return useContext(CurrencyContext);
}
