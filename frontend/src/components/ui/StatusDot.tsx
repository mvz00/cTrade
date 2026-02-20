import { cn } from '@/lib/cn';

type Status = 'ok' | 'warning' | 'error' | 'loading';

const statusColors: Record<Status, string> = {
  ok: 'bg-ct-green',
  warning: 'bg-ct-yellow',
  error: 'bg-ct-red',
  loading: 'bg-ct-text-dim animate-pulse',
};

interface StatusDotProps {
  status: Status;
  className?: string;
  label?: string;
}

export function StatusDot({ status, className, label }: StatusDotProps) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span className={cn('w-2 h-2 rounded-full', statusColors[status])} />
      {label && <span className="text-xs text-ct-text-muted">{label}</span>}
    </span>
  );
}
