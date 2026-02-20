import { cn } from '@/lib/cn';
import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon: ReactNode;
  title: string;
  description: string;
  phase?: number;
  className?: string;
}

export function EmptyState({ icon, title, description, phase, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-16 px-6 text-center', className)}>
      <div className="text-ct-text-dim mb-4">{icon}</div>
      <h3 className="text-lg font-medium text-ct-text mb-2">{title}</h3>
      <p className="text-ct-text-muted text-sm max-w-md">{description}</p>
      {phase && (
        <span className="mt-4 text-xs text-ct-text-dim bg-ct-bg-card border border-ct-border rounded-full px-3 py-1">
          Coming in Phase {phase}
        </span>
      )}
    </div>
  );
}
