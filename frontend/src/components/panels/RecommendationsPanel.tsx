import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useRecommendations } from '@/api/hooks/useDashboard';
import { formatNumber } from '@/lib/formatters';
import { TrendingUp, Clock } from 'lucide-react';

function PctCell({ value }: { value: number }) {
  const color = value > 0 ? 'text-ct-green' : value < 0 ? 'text-ct-red' : 'text-ct-text-dim';
  const sign = value > 0 ? '+' : '';
  return <span className={color}>{sign}{value.toFixed(2)}%</span>;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.7 ? 'bg-ct-green' : score >= 0.6 ? 'bg-ct-yellow' : 'bg-ct-blue';
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 h-1.5 rounded-full bg-ct-border overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ct-text-muted">{pct}</span>
    </div>
  );
}

function formatMarketCap(value: number): string {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${formatNumber(value, 0)}`;
}

export function RecommendationsPanel() {
  const { data, isLoading } = useRecommendations();

  const modeLabel = data?.strategy_mode === 'quicktrade' ? 'Quicktrade' : 'Long';
  const modeBadgeVariant = data?.strategy_mode === 'quicktrade' ? 'warning' : 'info';

  return (
    <Card>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <TrendingUp size={16} className="text-ct-accent" />
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">
            Recommended Buys
          </h3>
        </div>
        {data && (
          <Badge variant={modeBadgeVariant as any}>{modeLabel}</Badge>
        )}
      </div>

      {isLoading ? (
        <div className="flex justify-center py-8"><Spinner /></div>
      ) : !data || data.source === 'unavailable' ? (
        <p className="text-sm text-ct-text-dim py-8 text-center">
          CMC feed not configured — enable CoinMarketCap on the Connections page
        </p>
      ) : data.recommendations.length === 0 ? (
        <p className="text-sm text-ct-text-dim py-8 text-center">
          No coins currently meet the entry threshold
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-ct-border text-ct-text-muted text-left">
                <th className="pb-2 w-8">#</th>
                <th className="pb-2">Coin</th>
                <th className="pb-2">Score</th>
                <th className="pb-2">1h</th>
                <th className="pb-2">24h</th>
                <th className="pb-2">7d</th>
                <th className="pb-2">Mkt Cap</th>
                <th className="pb-2">
                  <span className="flex items-center gap-1">
                    <Clock size={12} />
                    Est. Time
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.recommendations.map((rec) => (
                <tr key={rec.symbol} className="border-b border-ct-border/50">
                  <td className="py-2 text-ct-text-dim">{rec.rank}</td>
                  <td className="py-2">
                    <div>
                      <span className="font-mono font-medium text-ct-text">{rec.symbol}</span>
                      <span className="text-xs text-ct-text-dim ml-1.5">{rec.name}</span>
                    </div>
                  </td>
                  <td className="py-2"><ScoreBar score={rec.score} /></td>
                  <td className="py-2 text-xs"><PctCell value={rec.pct_change_1h} /></td>
                  <td className="py-2 text-xs"><PctCell value={rec.pct_change_24h} /></td>
                  <td className="py-2 text-xs"><PctCell value={rec.pct_change_7d} /></td>
                  <td className="py-2 text-xs text-ct-text-dim">{formatMarketCap(rec.market_cap)}</td>
                  <td className="py-2">
                    <Badge variant="default">{rec.est_trade_time}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
