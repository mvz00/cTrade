import { cn } from '@/lib/cn';
import type { ReactNode } from 'react';

interface SourcePrioritySliderProps {
  label: string;
  value: number;
  onChange: (value: number) => void;
  /** Computed percentage contribution (0-100). */
  percentage: number;
  /** Icon element displayed beside the label. */
  icon?: ReactNode;
  /** Short description of what this category includes. */
  description?: string;
  className?: string;
}

export function SourcePrioritySlider({
  label,
  value,
  onChange,
  percentage,
  icon,
  description,
  className,
}: SourcePrioritySliderProps) {
  const inputId = `source-${label.toLowerCase().replace(/\s+/g, '-')}`;
  const pct = value; // 0-100

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon && <span className="text-ct-accent">{icon}</span>}
          <label htmlFor={inputId} className="block text-sm font-medium text-ct-text-muted">
            {label}
          </label>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-ct-accent tabular-nums">
            {Math.round(percentage)}%
          </span>
          <span className="text-xs text-ct-text-dim tabular-nums w-8 text-right">
            {value}
          </span>
        </div>
      </div>

      {/* Track + thumb */}
      <div className="relative pt-1">
        <input
          id={inputId}
          type="range"
          min={0}
          max={100}
          step={1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="source-slider w-full h-2 rounded-lg appearance-none cursor-pointer"
          style={{
            background: `linear-gradient(to right, #00d4aa ${pct}%, #30363d ${pct}%)`,
          }}
        />
      </div>

      {description && (
        <p className="text-xs text-ct-text-dim">{description}</p>
      )}

      {/* Custom slider styles */}
      <style>{`
        .source-slider {
          -webkit-appearance: none;
          appearance: none;
          outline: none;
        }
        .source-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #00d4aa;
          border: 2px solid #0a0e17;
          box-shadow: 0 0 0 2px #00d4aa40;
          cursor: pointer;
          margin-top: -4px;
          transition: box-shadow 0.15s;
        }
        .source-slider::-webkit-slider-thumb:hover {
          box-shadow: 0 0 0 4px #00d4aa40;
        }
        .source-slider::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: #00d4aa;
          border: 2px solid #0a0e17;
          box-shadow: 0 0 0 2px #00d4aa40;
          cursor: pointer;
        }
        .source-slider::-webkit-slider-runnable-track {
          height: 8px;
          border-radius: 4px;
        }
        .source-slider::-moz-range-track {
          height: 8px;
          border-radius: 4px;
        }
      `}</style>
    </div>
  );
}
