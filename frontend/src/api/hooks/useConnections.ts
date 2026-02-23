import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useConnections() {
  return useQuery({
    queryKey: ['connections'],
    queryFn: api.connections,
    refetchInterval: REFETCH_INTERVALS.CONNECTIONS,
    select: (data) => data.connections,
  });
}

export function useTestConnection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.testConnection(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['connections'] });
    },
  });
}
