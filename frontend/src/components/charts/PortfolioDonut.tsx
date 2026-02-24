import { formatUSD } from '@/lib/formatters';
import type { Portfolio } from '@/api/types';

interface PortfolioDonutProps {
  portfolio: Portfolio;
}

interface Segment {
  label: string;
  value: number;
  color: string;
}

export function PortfolioDonut({ portfolio }: PortfolioDonutProps) {
  const positionsValue = portfolio.positions_value ?? 0;
  const unrealizedPnl = portfolio.unrealized_pnl ?? 0;
  const total = portfolio.total_value_usd ?? 0;
  // Derive cash from total minus positions (accurate across all currencies)
  const cash = Math.max(0, total - positionsValue);

  // Build segments — skip zero-value ones
  const segments: Segment[] = [];

  if (cash > 0) {
    segments.push({ label: 'Cash', value: cash, color: '#0099ff' });
  }
  if (positionsValue > 0) {
    segments.push({ label: 'Positions', value: positionsValue, color: '#00d4aa' });
  }
  if (unrealizedPnl !== 0) {
    segments.push({
      label: 'Unrealized P&L',
      value: Math.abs(unrealizedPnl),
      color: unrealizedPnl > 0 ? '#f0b429' : '#f85149',
    });
  }

  // If no data at all, show a placeholder ring
  if (segments.length === 0) {
    segments.push({ label: 'Cash', value: 1, color: '#0099ff' });
  }

  const segmentTotal = segments.reduce((sum, s) => sum + s.value, 0);

  // SVG donut params
  const size = 160;
  const strokeWidth = 24;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;

  // Calculate arcs
  let cumulativeOffset = 0;
  const arcs = segments.map((segment) => {
    const pct = segmentTotal > 0 ? segment.value / segmentTotal : 0;
    const dashLength = pct * circumference;
    const dashGap = circumference - dashLength;
    const offset = -cumulativeOffset;
    cumulativeOffset += dashLength;

    return {
      ...segment,
      pct,
      dasharray: `${dashLength} ${dashGap}`,
      offset,
    };
  });

  return (
    <div className="flex flex-col items-center">
      {/* SVG Donut */}
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Background ring */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="#30363d"
            strokeWidth={strokeWidth}
          />
          {/* Segments */}
          {arcs.map((arc, i) => (
            <circle
              key={i}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={arc.color}
              strokeWidth={strokeWidth}
              strokeDasharray={arc.dasharray}
              strokeDashoffset={arc.offset}
              strokeLinecap="butt"
              transform={`rotate(-90 ${center} ${center})`}
              className="transition-all duration-500"
            />
          ))}
        </svg>

        {/* Center text */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xs text-ct-text-dim">Total</span>
          <span className="text-lg font-semibold text-ct-text">{formatUSD(total)}</span>
        </div>
      </div>

      {/* Legend */}
      <div className="mt-4 space-y-2 w-full">
        {arcs.map((arc, i) => (
          <div key={i} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                style={{ backgroundColor: arc.color }}
              />
              <span className="text-ct-text-muted">{arc.label}</span>
            </div>
            <div className="flex items-center gap-3">
              <span className="text-ct-text font-medium">
                {arc.label === 'Unrealized P&L'
                  ? (unrealizedPnl >= 0 ? '+' : '-') + formatUSD(arc.value)
                  : formatUSD(arc.value)}
              </span>
              <span className="text-ct-text-dim text-xs w-10 text-right">
                {(arc.pct * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
