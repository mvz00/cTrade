import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useOnChainScores() {
  return useQuery({
    queryKey: ['onchain', 'scores'],
    queryFn: () => api.onchainScores(),
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}

export function useOnChainScore(symbol: string) {
  return useQuery({
    queryKey: ['onchain', 'score', symbol],
    queryFn: () => api.onchainScore(symbol),
    enabled: !!symbol,
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}

export function useOnChainMetrics(symbol: string, limit = 20) {
  return useQuery({
    queryKey: ['onchain', 'metrics', symbol, limit],
    queryFn: () => api.onchainMetrics(symbol, limit),
    enabled: !!symbol,
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}

export function useOnChainStatus() {
  return useQuery({
    queryKey: ['onchain', 'status'],
    queryFn: () => api.onchainStatus(),
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}
