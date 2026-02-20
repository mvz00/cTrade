import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useTradingMode() {
  return useQuery({
    queryKey: ['config', 'trading-mode'],
    queryFn: api.tradingMode,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}

export function useStrategyConfig() {
  return useQuery({
    queryKey: ['config', 'strategy'],
    queryFn: api.strategyConfig,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}

export function useRiskConfig() {
  return useQuery({
    queryKey: ['config', 'risk'],
    queryFn: api.riskConfig,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}
