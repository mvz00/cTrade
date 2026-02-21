import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useSentimentScore, useSentimentTimeline, useSentimentStatus } from '@/api/hooks/useSentiment';
import { useOnChainScore, useOnChainMetrics, useOnChainStatus } from '@/api/hooks/useOnChain';
import { usePairs } from '@/api/hooks/useTrading';
import { useIndicators } from '@/api/hooks/useSignals';
import { formatRelative, formatNumber } from '@/lib/formatters';
import { Brain, Activity, Link, TrendingUp, Gauge } from 'lucide-react';

function ScoreGauge({ label, score, icon: Icon }: { label: string; score: number | null | undefined; icon: typeof Brain }) {
  const val = score ?? 0.5;
  const pct = val * 100;
  const color = val > 0.6 ? 'text-ct-green' : val < 0.4 ? 'text-ct-red' : 'text-ct-yellow';
  const barColor = val > 0.6 ? 'bg-ct-green' : val < 0.4 ? 'bg-ct-red' : 'bg-ct-yellow';
  const signal = val > 0.6 ? 'Bullish' : val < 0.4 ? 'Bearish' : 'Neutral';

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <Icon size={16} className="text-ct-text-muted" />
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">{label}</h3>
      </div>
      <div className="flex items-end gap-3 mb-2">
        <span className={`text-3xl font-bold ${color}`}>{pct.toFixed(0)}%</span>
        <Badge variant={val > 0.6 ? 'success' : val < 0.4 ? 'danger' : 'default'}>{signal}</Badge>
      </div>
      <div className="w-full h-2.5 bg-ct-border rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      {score === null || score === undefined ? (
        <p className="text-xs text-ct-text-dim mt-2">Waiting for data...</p>
      ) : null}
    </Card>
  );
}

export function IntelligencePage() {
  const { data: pairs } = usePairs();
  const [selectedSymbol, setSelectedSymbol] = useState('BTC');

  // Derive base symbol from pair
  const baseSymbol = selectedSymbol.split('/')[0] || selectedSymbol;

  // Sentiment data
  const { data: sentimentScore } = useSentimentScore(baseSymbol);
  const { data: sentimentTimeline, isLoading: timelineLoading } = useSentimentTimeline(baseSymbol, 30);
  const { data: sentimentStatus } = useSentimentStatus();

  // On-chain data
  const { data: onchainScore } = useOnChainScore(baseSymbol);
  const { data: onchainMetrics, isLoading: metricsLoading } = useOnChainMetrics(baseSymbol, 20);
  const { data: onchainStatus } = useOnChainStatus();

  // Technical (via indicators endpoint)
  const pairSymbol = `${baseSymbol}/USDT`;
  const { data: indicatorData } = useIndicators(pairSymbol);

  // Compute tech score from indicators
  const techScore = indicatorData?.indicators
    ? Object.values(indicatorData.indicators).reduce(
        (acc: number, ind: any) => acc + (ind.score ?? 0.5),
        0,
      ) / Math.max(Object.keys(indicatorData.indicators).length, 1)
    : null;

  // Available symbols from pairs
  const symbols = [...new Set((pairs || []).map(p => p.symbol.split('/')[0]))];
  if (symbols.length === 0) symbols.push('BTC', 'ETH', 'SOL', 'BNB', 'XRP');

  return (
    <div>
      <PageHeader title="Intelligence" description="Multi-source signal analysis: Technical, Sentiment, and On-Chain" />

      {/* Symbol selector */}
      <div className="flex items-center gap-3 mb-6">
        <select
          value={selectedSymbol}
          onChange={e => setSelectedSymbol(e.target.value)}
          className="bg-ct-bg-card border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text"
        >
          {symbols.map(s => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        {/* Feed status indicators */}
        <div className="flex items-center gap-4 ml-auto text-xs text-ct-text-dim">
          <span className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${sentimentStatus?.healthy ? 'bg-ct-green' : 'bg-ct-text-dim'}`} />
            Sentiment {sentimentStatus?.enabled ? 'Active' : 'Inactive'}
          </span>
          <span className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${onchainStatus?.healthy ? 'bg-ct-green' : 'bg-ct-text-dim'}`} />
            On-Chain {onchainStatus?.enabled ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>

      {/* Score Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <ScoreGauge label="Technical" score={techScore} icon={TrendingUp} />
        <ScoreGauge label="Sentiment" score={sentimentScore?.score ?? null} icon={Brain} />
        <ScoreGauge label="On-Chain" score={onchainScore?.score ?? null} icon={Link} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sentiment Timeline */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <Brain size={14} className="inline mr-1.5" />
            Sentiment Timeline — {baseSymbol}
          </h3>
          {sentimentStatus && !sentimentStatus.enabled ? (
            <p className="text-sm text-ct-text-dim py-8 text-center">Sentiment feed is inactive. It will activate when data sources are available.</p>
          ) : timelineLoading ? (
            <Spinner />
          ) : !sentimentTimeline?.data_points?.length ? (
            <div className="flex flex-col items-center py-8 text-ct-text-dim">
              <Brain size={36} className="mb-2" />
              <p className="text-sm">No sentiment data for {baseSymbol} yet.</p>
              <p className="text-xs mt-1">Data will appear as news and social posts are classified.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {sentimentTimeline.data_points.map((dp, i) => (
                <div key={i} className="py-2 px-3 rounded-lg bg-ct-bg-hover">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={dp.label === 'positive' ? 'success' : dp.label === 'negative' ? 'danger' : 'default'}
                      >
                        {dp.label}
                      </Badge>
                      <span className="text-xs font-mono text-ct-text-muted">{dp.source}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${dp.score > 0.6 ? 'text-ct-green' : dp.score < 0.4 ? 'text-ct-red' : 'text-ct-text'}`}>
                        {(dp.score * 100).toFixed(0)}%
                      </span>
                      <span className="text-xs text-ct-text-dim">{formatRelative(dp.timestamp)}</span>
                    </div>
                  </div>
                  {dp.text && (
                    <p className="text-xs text-ct-text-dim line-clamp-2 mt-1">{dp.text}</p>
                  )}
                </div>
              ))}
            </div>
          )}
          {sentimentScore && (
            <div className="mt-3 pt-3 border-t border-ct-border/50 flex justify-between text-xs text-ct-text-dim">
              <span>{sentimentScore.data_points} data points</span>
              <span>Model: {sentimentStatus?.classifier_model ?? 'loading'}</span>
            </div>
          )}
        </Card>

        {/* On-Chain Metrics */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <Link size={14} className="inline mr-1.5" />
            On-Chain Metrics — {baseSymbol}
          </h3>
          {onchainStatus && !onchainStatus.enabled ? (
            <p className="text-sm text-ct-text-dim py-8 text-center">On-chain feed is inactive. It will activate when data sources are available.</p>
          ) : metricsLoading ? (
            <Spinner />
          ) : !onchainMetrics?.metrics?.length ? (
            <div className="flex flex-col items-center py-8 text-ct-text-dim">
              <Link size={36} className="mb-2" />
              <p className="text-sm">No on-chain data for {baseSymbol} yet.</p>
              <p className="text-xs mt-1">Metrics will appear after the next data fetch cycle.</p>
            </div>
          ) : (
            <div className="space-y-1">
              {onchainMetrics.metrics.map((m, i) => (
                <div key={i} className="flex items-center justify-between py-2 px-3 rounded-lg bg-ct-bg-hover">
                  <div>
                    <span className="text-sm text-ct-text capitalize">
                      {m.metric_name.replace(/_/g, ' ')}
                    </span>
                    <span className="text-xs text-ct-text-dim ml-2">({m.source})</span>
                  </div>
                  <div className="text-right">
                    <span className="text-sm font-mono text-ct-text">
                      {m.metric_value > 1e12
                        ? `${(m.metric_value / 1e12).toFixed(2)}T`
                        : m.metric_value > 1e9
                          ? `${(m.metric_value / 1e9).toFixed(2)}B`
                          : m.metric_value > 1e6
                            ? `${(m.metric_value / 1e6).toFixed(2)}M`
                            : m.metric_value < 1
                              ? `${(m.metric_value * 100).toFixed(1)}%`
                              : formatNumber(m.metric_value, 2)}
                    </span>
                    <span className="text-xs text-ct-text-dim ml-2">{formatRelative(m.timestamp)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {onchainScore && (
            <div className="mt-3 pt-3 border-t border-ct-border/50 flex justify-between text-xs text-ct-text-dim">
              <span>{onchainScore.metrics_count} metrics</span>
              <span>Score: {(onchainScore.score * 100).toFixed(0)}% ({onchainScore.signal})</span>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
