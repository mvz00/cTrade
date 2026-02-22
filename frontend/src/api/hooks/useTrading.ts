import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';
import type { PlaceOrderRequest } from '../types';

export function usePairs() {
  return useQuery({ queryKey: ['trading', 'pairs'], queryFn: api.listPairs, refetchInterval: REFETCH_INTERVALS.TRADING });
}

export function useAvailablePairs() {
  return useQuery({ queryKey: ['trading', 'available-pairs'], queryFn: api.availablePairs });
}

export function useAddPair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.addPair(symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trading', 'pairs'] }),
  });
}

export function useAddPairsBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbols: string[]) => api.addPairsBatch(symbols),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trading', 'pairs'] }),
  });
}

export function useRemovePair() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (symbol: string) => api.removePair(symbol),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trading', 'pairs'] }),
  });
}

export function useOrders(status?: string) {
  return useQuery({
    queryKey: ['trading', 'orders', status],
    queryFn: () => api.listOrders(status),
    refetchInterval: REFETCH_INTERVALS.TRADING,
  });
}

export function usePlaceOrder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PlaceOrderRequest) => api.placeOrder(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trading'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function usePositions(status?: string) {
  return useQuery({
    queryKey: ['trading', 'positions', status],
    queryFn: () => api.listPositions(status),
    refetchInterval: REFETCH_INTERVALS.TRADING,
  });
}

export function useClosePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.closePosition(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trading'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function useCloseAllPositions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.closeAllPositions(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trading'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });
}

export function usePortfolio() {
  return useQuery({
    queryKey: ['trading', 'portfolio'],
    queryFn: api.portfolio,
    refetchInterval: REFETCH_INTERVALS.TRADING,
  });
}

export function useTicker(symbol: string) {
  return useQuery({
    queryKey: ['trading', 'ticker', symbol],
    queryFn: () => api.getTicker(symbol),
    refetchInterval: REFETCH_INTERVALS.TRADING,
    enabled: !!symbol,
  });
}

export function useEngineStatus() {
  return useQuery({
    queryKey: ['trading', 'engine'],
    queryFn: api.engineStatus,
    refetchInterval: REFETCH_INTERVALS.TRADING,
  });
}

export function useStartEngine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (interval?: number) => api.startEngine(interval),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trading', 'engine'] }),
  });
}

export function useStopEngine() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.stopEngine(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['trading', 'engine'] }),
  });
}

export function useActivityLog() {
  return useQuery({
    queryKey: ['trading', 'activity'],
    queryFn: api.activityLog,
    refetchInterval: REFETCH_INTERVALS.TRADING,
  });
}
