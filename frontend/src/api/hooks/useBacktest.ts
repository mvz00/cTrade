import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { BacktestRequest } from '../types';

export function useRunBacktest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BacktestRequest) => api.runBacktest(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['backtest', 'results'] }),
  });
}

export function useBacktestResults() {
  return useQuery({
    queryKey: ['backtest', 'results'],
    queryFn: api.backtestResults,
  });
}
