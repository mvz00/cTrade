import { cn } from '@/lib/cn';
import type { ReactNode } from 'react';

type Variant = 'default' | 'success' | 'warning' | 'danger' | 'info';

const variantStyles: Record<Variant, string> = {
  default: 'bg-ct-border text-ct-text-muted',
  success: 'bg-ct-green/15 text-ct-green',
  warning: 'bg-ct-yellow/15 text-ct-yellow',
  danger: 'bg-ct-red/15 text-ct-red',
  info: 'bg-ct-blue/15 text-ct-blue',
};

interface BadgeProps {
  children: ReactNode;
  variant?: Variant;
  className?: string;
}

export function Badge({ children, variant = 'default', className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
