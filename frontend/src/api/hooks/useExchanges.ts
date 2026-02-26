import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ExchangeAddRequest, ExchangeUpdateRequest } from '../types';

/** Invalidate queries that depend on exchange configuration. */
function invalidateExchangeDeps(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['exchanges'] });
  // Available pairs (and watched pairs) depend on exchange quote currencies
  // and active status — refresh them immediately when config changes.
  qc.invalidateQueries({ queryKey: ['trading', 'available-pairs'] });
  qc.invalidateQueries({ queryKey: ['trading', 'pairs'] });
}

export function useExchanges() {
  return useQuery({
    queryKey: ['exchanges'],
    queryFn: api.listExchanges,
  });
}

export function useAvailableExchanges() {
  return useQuery({
    queryKey: ['exchanges', 'available'],
    queryFn: api.availableExchanges,
  });
}

export function useAddExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ExchangeAddRequest) => api.addExchange(body),
    onSuccess: () => invalidateExchangeDeps(qc),
  });
}

export function useUpdateExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: ExchangeUpdateRequest & { id: string }) =>
      api.updateExchange(id, body),
    onSuccess: () => invalidateExchangeDeps(qc),
  });
}

export function useDeleteExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteExchange(id),
    onSuccess: () => invalidateExchangeDeps(qc),
  });
}

export function useToggleExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.toggleExchange(id),
    onSuccess: () => invalidateExchangeDeps(qc),
  });
}

export function useTestExchange() {
  return useMutation({
    mutationFn: (id: string) => api.testExchange(id),
  });
}
