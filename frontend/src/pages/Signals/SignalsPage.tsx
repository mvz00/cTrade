import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useSignals, useIndicators } from '@/api/hooks/useSignals';
import { usePairs } from '@/api/hooks/useTrading';
import { formatRelative, formatNumber } from '@/lib/formatters';
import { Activity, TrendingUp } from 'lucide-react';

export function SignalsPage() {
  const [filterSymbol, setFilterSymbol] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const { data: signals, isLoading } = useSignals({ symbol: filterSymbol || undefined, action: filterAction || undefined, limit: 100 });
  const { data: pairs } = usePairs();
  const selectedSymbol = filterSymbol || (pairs && pairs.length > 0 ? pairs[0].symbol : 'BTC/USDT');
  const { data: indicatorData } = useIndicators(selectedSymbol);

  return (
    <div>
      <PageHeader title="Signals" description="Trading signals from multi-source intelligence fusion" />

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <select value={filterSymbol} onChange={e => setFilterSymbol(e.target.value)} className="bg-ct-bg-card border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text">
          <option value="">All Pairs</option>
          {(pairs || []).map(p => <option key={p.symbol} value={p.symbol}>{p.symbol}</option>)}
        </select>
        <select value={filterAction} onChange={e => setFilterAction(e.target.value)} className="bg-ct-bg-card border border-ct-border rounded-lg px-3 py-2 text-sm text-ct-text">
          <option value="">All Actions</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
          <option value="HOLD">HOLD</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Signal Stream */}
        <Card className="lg:col-span-2">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">Signal Stream</h3>
          {isLoading ? <Spinner /> : (signals || []).length === 0 ? (
            <div className="flex flex-col items-center py-12 text-ct-text-dim">
              <Activity size={40} className="mb-3" />
              <p className="text-sm">No signals yet. Add trading pairs and start the engine.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-[500px] overflow-y-auto">
              {(signals || []).map(s => (
                <div key={s.id} className="flex items-center justify-between py-2 px-3 rounded-lg bg-ct-bg-hover">
                  <div className="flex items-center gap-3">
                    <Badge variant={s.action === 'BUY' ? 'success' : s.action === 'SELL' ? 'danger' : 'default'}>{s.action}</Badge>
                    <span className="font-mono text-sm text-ct-text">{s.pair_symbol}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="text-xs text-ct-text-muted">Confidence</div>
                      <div className="flex items-center gap-1">
                        <div className="w-16 h-1.5 bg-ct-border rounded-full overflow-hidden">
                          <div className="h-full bg-ct-accent rounded-full" style={{ width: `${(s.confidence ?? 0) * 100}%` }} />
                        </div>
                        <span className="text-xs text-ct-text-muted">{((s.confidence ?? 0) * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                    {s.technical_score !== null && (
                      <div className="text-right">
                        <div className="text-xs text-ct-text-muted">Tech</div>
                        <span className="text-sm text-ct-text">{(s.technical_score * 100).toFixed(1)}%</span>
                      </div>
                    )}
                    {s.sentiment_score !== null && (
                      <div className="text-right">
                        <div className="text-xs text-ct-text-muted">Sentiment</div>
                        <span className={`text-sm ${s.sentiment_score > 0.6 ? 'text-ct-green' : s.sentiment_score < 0.4 ? 'text-ct-red' : 'text-ct-text'}`}>
                          {(s.sentiment_score * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    {s.onchain_score !== null && (
                      <div className="text-right">
                        <div className="text-xs text-ct-text-muted">On-Chain</div>
                        <span className={`text-sm ${s.onchain_score > 0.6 ? 'text-ct-green' : s.onchain_score < 0.4 ? 'text-ct-red' : 'text-ct-text'}`}>
                          {(s.onchain_score * 100).toFixed(1)}%
                        </span>
                      </div>
                    )}
                    <span className="text-xs text-ct-text-dim">{formatRelative(s.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Technical Indicators Panel */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-4">
            <TrendingUp size={14} className="inline mr-1" />
            Indicators — {selectedSymbol}
          </h3>
          {!indicatorData ? (
            <p className="text-sm text-ct-text-dim py-8 text-center">No indicator data. Start engine to generate.</p>
          ) : (
            <div className="space-y-4">
              {Object.entries(indicatorData.indicators).map(([name, ind]: [string, any]) => (
                <div key={name} className="border-b border-ct-border/50 pb-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-ct-text capitalize">{name.replace('_', ' ')}</span>
                    <Badge variant={ind.score > 0.6 ? 'success' : ind.score < 0.4 ? 'danger' : 'default'}>
                      {ind.signal}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-ct-border rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${ind.score > 0.6 ? 'bg-ct-green' : ind.score < 0.4 ? 'bg-ct-red' : 'bg-ct-yellow'}`}
                        style={{ width: `${ind.score * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-ct-text-muted w-10 text-right">{(ind.score * 100).toFixed(0)}%</span>
                  </div>
                  {ind.value !== undefined && (
                    <span className="text-xs text-ct-text-dim">Value: {formatNumber(ind.value, 2)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
