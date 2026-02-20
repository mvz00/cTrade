import { cn } from '@/lib/cn';

interface SelectProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  className?: string;
}

export function Select({ label, value, onChange, options, className }: SelectProps) {
  const selectId = label.toLowerCase().replace(/\s+/g, '-');
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={selectId} className="block text-sm font-medium text-ct-text-muted">
        {label}
      </label>
      <select
        id={selectId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={cn(
          'w-full px-3 py-2 rounded-lg text-sm bg-ct-bg border border-ct-border text-ct-text',
          'focus:outline-none focus:ring-1 focus:ring-ct-accent focus:border-ct-accent transition-colors'
        )}
      >
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </div>
  );
}
