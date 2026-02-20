import { cn } from '@/lib/cn';
import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
}

export function Card({ children, className, hover = false }: CardProps) {
  return (
    <div
      className={cn(
        'bg-ct-bg-card border border-ct-border rounded-xl p-5',
        hover && 'transition-colors hover:border-ct-border-hover',
        className
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({ children, className }: { children: ReactNode; className?: string }) {
  return <h3 className={cn('text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-1', className)}>{children}</h3>;
}

export function CardValue({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('text-2xl font-semibold text-ct-text', className)}>{children}</div>;
}
