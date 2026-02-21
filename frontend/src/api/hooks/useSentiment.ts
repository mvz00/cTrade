import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useSentimentScores() {
  return useQuery({
    queryKey: ['sentiment', 'scores'],
    queryFn: () => api.sentimentScores(),
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}

export function useSentimentScore(symbol: string) {
  return useQuery({
    queryKey: ['sentiment', 'score', symbol],
    queryFn: () => api.sentimentScore(symbol),
    enabled: !!symbol,
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}

export function useSentimentTimeline(symbol: string, limit = 20) {
  return useQuery({
    queryKey: ['sentiment', 'timeline', symbol, limit],
    queryFn: () => api.sentimentTimeline(symbol, limit),
    enabled: !!symbol,
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}

export function useSentimentStatus() {
  return useQuery({
    queryKey: ['sentiment', 'status'],
    queryFn: () => api.sentimentStatus(),
    refetchInterval: REFETCH_INTERVALS.INTELLIGENCE,
  });
}
