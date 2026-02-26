import { cn } from '@/lib/cn';
import { InfoTooltip } from './InfoTooltip';

interface RangeSliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  markers?: { value: number; label: string }[];
  /** Additional info shown below the slider */
  info?: string;
  tooltip?: string;
  className?: string;
}

const RISK_COLORS: Record<string, string> = {
  low: 'text-ct-green',
  mid: 'text-ct-accent',
  high: 'text-ct-red',
};

function getRiskLevel(value: number, max: number): { label: string; color: string } {
  const pct = value / max;
  if (pct <= 0.3) return { label: 'Conservative', color: RISK_COLORS.low };
  if (pct <= 0.6) return { label: 'Moderate', color: RISK_COLORS.mid };
  return { label: 'Aggressive', color: RISK_COLORS.high };
}

export function RangeSlider({
  label,
  value,
  onChange,
  min = 1,
  max = 10,
  step = 1,
  markers,
  info,
  tooltip,
  className,
}: RangeSliderProps) {
  const inputId = label.toLowerCase().replace(/\s+/g, '-');
  const pct = ((value - min) / (max - min)) * 100;
  const risk = getRiskLevel(value, max);

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <label htmlFor={inputId} className="block text-sm font-medium text-ct-text-muted">
          {label}{tooltip && <InfoTooltip text={tooltip} />}
        </label>
        <span className={cn('text-sm font-semibold', risk.color)}>
          {value} &mdash; {risk.label}
        </span>
      </div>

      {/* Track + thumb */}
      <div className="relative pt-1">
        <input
          id={inputId}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="range-slider w-full h-2 rounded-lg appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, #22c55e ${0}%, #eab308 ${50}%, #ef4444 ${100}%)`,
          }}
        />
        {/* Fill overlay to show position */}
        <div
          className="absolute top-1 left-0 h-2 rounded-l-lg pointer-events-none"
          style={{
            width: `${pct}%`,
            background: 'linear-gradient(to right, #22c55e, #eab308, #ef4444)',
            backgroundSize: `${(100 / pct) * 100}% 100%`,
          }}
        />
      </div>

      {/* Tick markers */}
      {markers && markers.length > 0 && (
        <div className="relative flex justify-between px-0.5">
          {markers.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => onChange(m.value)}
              className={cn(
                'text-[10px] transition-colors cursor-pointer',
                value === m.value ? 'text-ct-text font-medium' : 'text-ct-text-dim hover:text-ct-text-muted'
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}

      {info && (
        <p className="text-xs text-ct-text-dim">{info}</p>
      )}

      {/* Custom slider styles */}
      <style>{`
        .range-slider {
          -webkit-appearance: none;
          appearance: none;
          outline: none;
        }
        .range-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: white;
          border: 2px solid #f59e0b;
          box-shadow: 0 1px 3px rgba(0,0,0,0.3);
          cursor: pointer;
          margin-top: -4px;
        }
        .range-slider::-moz-range-thumb {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: white;
          border: 2px solid #f59e0b;
          box-shadow: 0 1px 3px rgba(0,0,0,0.3);
          cursor: pointer;
        }
        .range-slider::-webkit-slider-runnable-track {
          height: 8px;
          border-radius: 4px;
        }
        .range-slider::-moz-range-track {
          height: 8px;
          border-radius: 4px;
        }
      `}</style>
    </div>
  );
}
