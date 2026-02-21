import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';
import type { CreateAlertRequest } from '../types';

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: api.listAlerts,
    refetchInterval: REFETCH_INTERVALS.CONFIG,
  });
}

export function useCreateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateAlertRequest) => api.createAlert(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useDeleteAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useToggleAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.toggleAlert(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  });
}

export function useAlertHistory() {
  return useQuery({
    queryKey: ['alerts', 'history'],
    queryFn: api.alertHistory,
    refetchInterval: REFETCH_INTERVALS.SIGNALS,
  });
}
