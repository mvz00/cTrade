import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useTopGainers(limit = 20) {
  return useQuery({
    queryKey: ['screener', 'gainers', limit],
    queryFn: () => api.screenerGainers(limit),
    refetchInterval: REFETCH_INTERVALS.SCREENER,
  });
}

export function useTopLosers(limit = 20) {
  return useQuery({
    queryKey: ['screener', 'losers', limit],
    queryFn: () => api.screenerLosers(limit),
    refetchInterval: REFETCH_INTERVALS.SCREENER,
  });
}

export function useScreenerSearch(params?: {
  sort_by?: string;
  sort_dir?: string;
  limit?: number;
  min_market_cap?: number;
  min_volume?: number;
}) {
  return useQuery({
    queryKey: ['screener', 'search', params],
    queryFn: () => api.screenerSearch(params),
    refetchInterval: REFETCH_INTERVALS.SCREENER,
  });
}

export function useCMCFeedStatus() {
  return useQuery({
    queryKey: ['screener', 'status'],
    queryFn: api.cmcFeedStatus,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}
