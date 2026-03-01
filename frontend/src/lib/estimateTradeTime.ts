import type { Position } from '@/api/types';

/**
 * Estimate remaining trade time for an open position based on outlook scores
 * and strategy mode. Returns a human-readable string like "~30m", "~2h", "~1d".
 */
export function estimateTradeTime(
  position: Position,
  strategyMode: string,
  takeProfitPct: number,
): string {
  const now = Date.now();
  const openedAt = new Date(position.opened_at).getTime();
  const elapsedHours = (now - openedAt) / (1000 * 60 * 60);

  // Use outlook scores to gauge expected hold duration
  const outlook1h = position.outlook_1h ?? null;
  const outlook24h = position.outlook_24h ?? null;
  const outlook7d = position.outlook_7d ?? null;

  let estimatedTotalHours: number;

  if (strategyMode === 'quicktrade') {
    // Quicktrade: short duration, influenced by 1h outlook strength
    if (outlook1h !== null) {
      // Higher outlook = stronger momentum = faster to TP
      const strength = Math.max(Math.abs(outlook1h - 0.5) * 2, 0.1);
      estimatedTotalHours = Math.max(0.25, Math.min(4.0, 1.0 / strength));
    } else {
      estimatedTotalHours = 1.0; // default ~1h for quicktrade
    }
  } else {
    // Long mode: longer duration, influenced by 7d/24h outlook
    const outlook = outlook7d ?? outlook24h ?? outlook1h;
    if (outlook !== null) {
      const strength = Math.max(Math.abs(outlook - 0.5) * 2, 0.05);
      estimatedTotalHours = Math.max(1.0, Math.min(168.0, 24.0 / strength));
    } else {
      estimatedTotalHours = 24.0; // default ~24h for long
    }
  }

  // Remaining time = estimated total - elapsed
  const remainingHours = Math.max(0, estimatedTotalHours - elapsedHours);

  if (remainingHours <= 0) {
    return 'due';
  }

  return formatHours(remainingHours);
}

function formatHours(hours: number): string {
  if (hours < 1.0) {
    const minutes = Math.round(hours * 60);
    return `~${Math.max(1, minutes)}m`;
  } else if (hours < 24.0) {
    return `~${Math.round(hours)}h`;
  } else {
    const days = Math.round(hours / 24.0);
    return `~${days}d`;
  }
}
