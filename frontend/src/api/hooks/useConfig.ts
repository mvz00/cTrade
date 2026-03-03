import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';
import type { TradingModeUpdate, StrategyConfigUpdate, RiskConfigUpdate, EmailConfigUpdate, LoggingConfigUpdate } from '../types';

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
      // Invalidate everything that depends on trading mode
      qc.invalidateQueries({ queryKey: ['config', 'trading-mode'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      qc.invalidateQueries({ queryKey: ['trading'] });
      qc.invalidateQueries({ queryKey: ['signals'] });
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

export function useEmailConfig() {
  return useQuery({
    queryKey: ['config', 'email'],
    queryFn: api.emailConfig,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}

export function useUpdateEmailConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EmailConfigUpdate) => api.updateEmailConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config', 'email'] });
    },
  });
}

export function useTestEmail() {
  return useMutation({
    mutationFn: () => api.testEmail(),
  });
}

export function useLoggingConfig() {
  return useQuery({
    queryKey: ['config', 'logging'],
    queryFn: api.loggingConfig,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}

export function useUpdateLoggingConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: LoggingConfigUpdate) => api.updateLoggingConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config', 'logging'] });
    },
  });
}

export function usePurgeAllData() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.purgeAllData(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config', 'logging'] });
    },
  });
}
