import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';
import type { TradingModeUpdate, StrategyConfigUpdate, RiskConfigUpdate } from '../types';

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

export function useUpdateTradingMode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TradingModeUpdate) => api.updateTradingMode(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config', 'trading-mode'] });
    },
  });
}

export function useUpdateStrategy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: StrategyConfigUpdate) => api.updateStrategy(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config', 'strategy'] });
    },
  });
}

export function useUpdateRisk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RiskConfigUpdate) => api.updateRisk(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config', 'risk'] });
    },
  });
}
