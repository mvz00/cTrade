import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import type { ExchangeAddRequest, ExchangeUpdateRequest } from '../types';

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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['exchanges'] });
    },
  });
}

export function useUpdateExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: ExchangeUpdateRequest & { id: string }) =>
      api.updateExchange(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['exchanges'] });
    },
  });
}

export function useDeleteExchange() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteExchange(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['exchanges'] });
    },
  });
}

export function useTestExchange() {
  return useMutation({
    mutationFn: (id: string) => api.testExchange(id),
  });
}
