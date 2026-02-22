import { useEffect, useRef } from 'react';
import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts';
import type { EquityPoint } from '@/api/types';

interface EquityCurveChartProps {
  data: EquityPoint[];
}

export function EquityCurveChart({ data }: EquityCurveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null);

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

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

    const series = chart.addAreaSeries({
      lineColor: '#00d4aa',
      topColor: 'rgba(0, 212, 170, 0.2)',
      bottomColor: 'rgba(0, 212, 170, 0)',
      lineWidth: 2,
      priceFormat: {
        type: 'price',
        precision: 2,
        minMove: 0.01,
      },
    });

    chartRef.current = chart;
    seriesRef.current = series;

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
      seriesRef.current = null;
    };
  }, []);

  // Update data when it changes
  useEffect(() => {
    if (!seriesRef.current || !data || data.length === 0) return;

    const chartData = data
      .map((point) => ({
        time: (new Date(point.timestamp).getTime() / 1000) as any,
        value: point.total_value,
      }))
      .sort((a, b) => a.time - b.time);

    seriesRef.current.setData(chartData);

    // Fit content to view
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [data]);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-ct-text-dim">
        <div className="text-center">
          <div className="text-3xl mb-2 opacity-30">📈</div>
          <p className="text-sm">No equity data yet</p>
          <p className="text-xs text-ct-text-dim mt-1">Start the trading engine to track your portfolio value</p>
        </div>
      </div>
    );
  }

  return <div ref={containerRef} className="w-full h-64" />;
}
