import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import type { SymbolCandleSeries } from '@/api/types';

// Reuse same color palette as EquityCurveChart
const POSITION_COLORS = [
  '#00d4aa', // teal
  '#ff6b6b', // red
  '#4ecdc4', // cyan
  '#ffa726', // orange
  '#ab47bc', // purple
  '#42a5f5', // blue
  '#66bb6a', // green
  '#ef5350', // bright red
];

interface PositionPriceChartProps {
  series: SymbolCandleSeries[];
}

export function PositionPriceChart({ series }: PositionPriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRefs = useRef<ISeriesApi<'Line'>[]>([]);

  const hasData = series.length > 0 && series.some((s) => s.candles.length > 0);

  // Build legend entries
  const legendEntries = series
    .filter((s) => s.candles.length > 0)
    .map((s, i) => ({
      name: s.symbol,
      color: POSITION_COLORS[i % POSITION_COLORS.length],
    }));

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
      localization: {
        priceFormatter: (price: number) =>
          price >= 0 ? `+${price.toFixed(2)}%` : `${price.toFixed(2)}%`,
      },
    });

    chartRef.current = chart;
    seriesRefs.current = [];

    let colorIndex = 0;
    for (const s of series) {
      if (s.candles.length === 0) continue;

      const color = POSITION_COLORS[colorIndex % POSITION_COLORS.length];
      colorIndex++;

      const lineSeries = chart.addLineSeries({
        color,
        lineWidth: 2,
        priceFormat: {
          type: 'custom',
          formatter: (price: number) =>
            price >= 0 ? `+${price.toFixed(2)}%` : `${price.toFixed(2)}%`,
        },
        title: s.symbol,
      });

      // Transform absolute close prices -> % change from first candle
      const firstClose = s.candles[0].close;
      const chartData = s.candles
        .map((c) => ({
          time: (new Date(c.time).getTime() / 1000) as any,
          value: firstClose !== 0 ? ((c.close - firstClose) / firstClose) * 100 : 0,
        }))
        .sort((a, b) => a.time - b.time);

      lineSeries.setData(chartData);
      seriesRefs.current.push(lineSeries);
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
  }, [hasData, series]);

  if (!hasData) {
    return (
      <div className="flex items-center justify-center h-64 text-ct-text-dim">
        <div className="text-center">
          <div className="text-3xl mb-2 opacity-30">📊</div>
          <p className="text-sm">No open positions to chart</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Legend */}
      {legendEntries.length > 0 && (
        <div className="flex flex-wrap gap-4 mb-2">
          {legendEntries.map((entry) => (
            <div
              key={entry.name}
              className="flex items-center gap-1.5 text-xs text-ct-text-muted"
            >
              <span
                className="inline-block w-3 h-0.5 rounded"
                style={{ backgroundColor: entry.color }}
              />
              {entry.name}
            </div>
          ))}
        </div>
      )}
      <div ref={containerRef} className="w-full h-64" />
    </div>
  );
}
