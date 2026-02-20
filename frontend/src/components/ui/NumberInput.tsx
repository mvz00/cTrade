import { cn } from '@/lib/cn';

interface NumberInputProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  suffix?: string;
  error?: string;
  className?: string;
}

export function NumberInput({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
  error,
  className,
}: NumberInputProps) {
  const inputId = label.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={inputId} className="block text-sm font-medium text-ct-text-muted">
        {label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type="number"
          value={value}
          onChange={(e) => onChange(parseFloat(e.target.value) || 0)}
          min={min}
          max={max}
          step={step}
          className={cn(
            'w-full px-3 py-2 rounded-lg text-sm bg-ct-bg border text-ct-text',
            'focus:outline-none focus:ring-1 focus:ring-ct-accent focus:border-ct-accent transition-colors',
            '[appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none',
            suffix ? 'pr-8' : '',
            error ? 'border-ct-red' : 'border-ct-border'
          )}
        />
        {suffix && (
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-sm text-ct-text-dim">
            {suffix}
          </span>
        )}
      </div>
      {error && <p className="text-xs text-ct-red">{error}</p>}
    </div>
  );
}
