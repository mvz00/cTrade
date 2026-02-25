import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi, LineStyle } from 'lightweight-charts';
import type { EquityPoint, PortfolioHistorySeries } from '@/api/types';

// Distinct colors for per-exchange lines
const EXCHANGE_COLORS = [
  '#00d4aa', // teal
  '#ff6b6b', // red
  '#4ecdc4', // cyan
  '#ffa726', // orange
  '#ab47bc', // purple
  '#42a5f5', // blue
  '#66bb6a', // green
  '#ef5350', // bright red
];

const TOTAL_COLOR = '#ffffff';

// ---- Legacy single-series props (backward compatible) ----
interface LegacyChartProps {
  data: EquityPoint[];
  series?: never;
}

// ---- Multi-series props (per-exchange) ----
interface MultiSeriesChartProps {
  data?: never;
  series: PortfolioHistorySeries[];
  tradingMode?: string;
}

type EquityCurveChartProps = LegacyChartProps | MultiSeriesChartProps;

export function EquityCurveChart(props: EquityCurveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<ISeriesApi<'Line'>[]>([]);

  const isMultiSeries = 'series' in props && props.series !== undefined;
  const legacyData = !isMultiSeries ? (props as LegacyChartProps).data : undefined;
  const rawMultiSeries = isMultiSeries ? (props as MultiSeriesChartProps).series : undefined;
  const tradingMode = isMultiSeries ? (props as MultiSeriesChartProps).tradingMode : undefined;

  // Filter series based on trading mode:
  // Paper mode → only paper/unknown lines; Live mode → only real exchange lines
  const multiSeries = rawMultiSeries?.filter((s) => {
    const name = s.exchange_name.toLowerCase();
    if (tradingMode === 'paper') {
      return name === 'unknown' || name === 'paper';
    }
    if (tradingMode === 'live') {
      return name !== 'unknown' && name !== 'paper';
    }
    return true; // no mode info → show all
  });

  /** Display-friendly name: rename "unknown" → "Paper Trade" */
  const displayName = (name: string) =>
    name.toLowerCase() === 'unknown' ? 'Paper Trade' : name;

  // Determine if we have data to show
  const hasData = isMultiSeries
    ? (multiSeries && multiSeries.length > 0 && multiSeries.some(s => s.points.length > 0))
    : (legacyData && legacyData.length > 0);

  // Build legend entries for multi-series
  const legendEntries = multiSeries
    ? multiSeries.map((s, i) => ({
        name: displayName(s.exchange_name),
        color: EXCHANGE_COLORS[i % EXCHANGE_COLORS.length],
      }))
    : [];

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current || !hasData) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#161b22' },
        textColor: '#8b949e',
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      },
      grid: {
        vertLines: { color: '#30363d' },
        horzLines: { color: '#30363d' },
      },
      rightPriceScale: {
        borderColor: '#30363d',
      },
      timeScale: {
        borderColor: '#30363d',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: { color: '#8b949e', width: 1, style: 3 },
        horzLine: { color: '#8b949e', width: 1, style: 3 },
      },
      handleScroll: true,
      handleScale: true,
    });

    chartRef.current = chart;
    seriesRefs.current = [];

    if (isMultiSeries && multiSeries) {
      // --- Multi-series mode: one line per exchange + total ---
      const allTimestamps = new Set<number>();

      // Create a line series for each exchange
      multiSeries.forEach((s, i) => {
        const color = EXCHANGE_COLORS[i % EXCHANGE_COLORS.length];
        const series = chart.addLineSeries({
          color,
          lineWidth: 2,
          priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
          title: displayName(s.exchange_name),
        });

        const chartData = s.points
          .map((p) => {
            const t = new Date(p.timestamp).getTime() / 1000;
            allTimestamps.add(t);
            return { time: t as any, value: p.total_value_usd };
          })
          .sort((a, b) => a.time - b.time);

        series.setData(chartData);
        seriesRefs.current.push(series);
      });

      // Add "Total" dashed line if there are 2+ exchanges
      if (multiSeries.length >= 2) {
        // Build total from all series data aligned by timestamp
        const totalByTime = new Map<number, number>();
        for (const s of multiSeries) {
          for (const p of s.points) {
            const t = Math.floor(new Date(p.timestamp).getTime() / 1000);
            totalByTime.set(t, (totalByTime.get(t) ?? 0) + p.total_value_usd);
          }
        }

        const totalData = Array.from(totalByTime.entries())
          .map(([t, v]) => ({ time: t as any, value: v }))
          .sort((a, b) => a.time - b.time);

        if (totalData.length > 0) {
          const totalSeries = chart.addLineSeries({
            color: TOTAL_COLOR,
            lineWidth: 2,
            lineStyle: LineStyle.Dashed,
            priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
            title: 'Total',
          });
          totalSeries.setData(totalData);
          seriesRefs.current.push(totalSeries);
        }
      }
    } else if (legacyData) {
      // --- Legacy single-series mode ---
      const series = chart.addLineSeries({
        color: '#00d4aa',
        lineWidth: 2,
        priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
      });

      const chartData = legacyData
        .map((point) => ({
          time: (new Date(point.timestamp).getTime() / 1000) as any,
          value: point.total_value,
        }))
        .sort((a, b) => a.time - b.time);

      series.setData(chartData);
      seriesRefs.current.push(series);
    }

    chart.timeScale().fitContent();

    // ResizeObserver for responsive chart
    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        chart.applyOptions({ width, height });
      }
    });
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRefs.current = [];
    };
    // Re-create chart when data changes
  }, [hasData, isMultiSeries, multiSeries, legacyData, tradingMode]);

  if (!hasData) {
    return (
      <div className="flex items-center justify-center h-64 text-ct-text-dim">
        <div className="text-center">
          <div className="text-3xl mb-2 opacity-30">📈</div>
          <p className="text-sm">No portfolio history yet</p>
          <p className="text-xs text-ct-text-dim mt-1">
            Snapshots are recorded every 5 minutes when exchanges are configured
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Legend for multi-series */}
      {isMultiSeries && legendEntries.length > 0 && (
        <div className="flex flex-wrap gap-4 mb-2">
          {legendEntries.map((entry) => (
            <div key={entry.name} className="flex items-center gap-1.5 text-xs text-ct-text-muted">
              <span
                className="inline-block w-3 h-0.5 rounded"
                style={{ backgroundColor: entry.color }}
              />
              {entry.name}
            </div>
          ))}
          {multiSeries && multiSeries.length >= 2 && (
            <div className="flex items-center gap-1.5 text-xs text-ct-text-muted">
              <span
                className="inline-block w-3 h-0.5 rounded"
                style={{ backgroundColor: TOTAL_COLOR, opacity: 0.7 }}
              />
              Total (dashed)
            </div>
          )}
        </div>
      )}
      <div ref={containerRef} className="w-full h-64" />
    </div>
  );
}
