import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useSignals(params?: { symbol?: string; action?: string; limit?: number }) {
  return useQuery({
    queryKey: ['signals', params],
    queryFn: () => api.listSignals(params),
    refetchInterval: REFETCH_INTERVALS.SIGNALS,
  });
}

export function useLatestSignal(symbol: string) {
  return useQuery({
    queryKey: ['signals', 'latest', symbol],
    queryFn: () => api.latestSignal(symbol),
    enabled: !!symbol,
    refetchInterval: REFETCH_INTERVALS.SIGNALS,
  });
}

export function useIndicators(symbol: string) {
  return useQuery({
    queryKey: ['signals', 'indicators', symbol],
    queryFn: () => api.indicators(symbol),
    enabled: !!symbol,
    refetchInterval: REFETCH_INTERVALS.SIGNALS,
  });
}
