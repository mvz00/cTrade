import { cn } from '@/lib/cn';
import { InfoTooltip } from './InfoTooltip';

interface ToggleProps {
  label: string;
  description?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  activeLabel?: string;
  inactiveLabel?: string;
  tooltip?: string;
}

export function Toggle({
  label,
  description,
  checked,
  onChange,
  activeLabel,
  inactiveLabel,
  tooltip,
}: ToggleProps) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm font-medium text-ct-text">{label}{tooltip && <InfoTooltip text={tooltip} />}</p>
        {description && <p className="text-xs text-ct-text-dim mt-0.5">{description}</p>}
      </div>
      <div className="flex items-center gap-2">
        {inactiveLabel && (
          <span className={cn('text-xs font-medium', !checked ? 'text-ct-text' : 'text-ct-text-dim')}>
            {inactiveLabel}
          </span>
        )}
        <button
          type="button"
          role="switch"
          aria-checked={checked}
          onClick={() => onChange(!checked)}
          className={cn(
            'relative inline-flex h-7 w-12 md:h-6 md:w-11 items-center rounded-full transition-colors',
            checked ? 'bg-ct-accent' : 'bg-ct-border'
          )}
        >
          <span
            className={cn(
              'inline-block h-5 w-5 md:h-4 md:w-4 rounded-full bg-white transition-transform',
              checked ? 'translate-x-6' : 'translate-x-1'
            )}
          />
        </button>
        {activeLabel && (
          <span className={cn('text-xs font-medium', checked ? 'text-ct-text' : 'text-ct-text-dim')}>
            {activeLabel}
          </span>
        )}
      </div>
    </div>
  );
}
