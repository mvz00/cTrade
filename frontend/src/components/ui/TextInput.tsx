import { cn } from '@/lib/cn';
import { InfoTooltip } from './InfoTooltip';
import type { InputHTMLAttributes } from 'react';

interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  tooltip?: string;
}

export function TextInput({ label, error, tooltip, className, id, ...props }: TextInputProps) {
  const inputId = id ?? label.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={inputId} className="block text-sm font-medium text-ct-text-muted">
        {label}{tooltip && <InfoTooltip text={tooltip} />}
      </label>
      <input
        id={inputId}
        className={cn(
          'w-full px-3 py-2 rounded-lg text-sm bg-ct-bg border text-ct-text placeholder-ct-text-dim',
          'focus:outline-none focus:ring-1 focus:ring-ct-accent focus:border-ct-accent transition-colors',
          error ? 'border-ct-red' : 'border-ct-border'
        )}
        {...props}
      />
      {error && <p className="text-xs text-ct-red">{error}</p>}
    </div>
  );
}
