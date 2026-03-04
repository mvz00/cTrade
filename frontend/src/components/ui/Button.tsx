import { cn } from '@/lib/cn';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

const variantStyles: Record<Variant, string> = {
  primary: 'bg-ct-accent text-ct-bg hover:bg-ct-accent/90',
  secondary: 'bg-ct-bg-card border border-ct-border text-ct-text hover:bg-ct-bg-hover',
  danger: 'bg-ct-red text-white hover:bg-ct-red/90',
  ghost: 'text-ct-text-muted hover:text-ct-text hover:bg-ct-bg-hover',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({ variant = 'primary', className, children, ...props }: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center gap-2 px-4 py-2.5 md:py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed',
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
