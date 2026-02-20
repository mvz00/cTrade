import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { REFETCH_INTERVALS } from '@/lib/constants';

export function useDashboardSummary() {
  return useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: api.dashboardSummary,
    refetchInterval: REFETCH_INTERVALS.DASHBOARD,
  });
}
