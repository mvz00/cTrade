import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Spinner } from '@/components/ui/Spinner';
import { useTopGainers, useTopLosers, useCMCFeedStatus } from '@/api/hooks/useScreener';
import { useAddPair } from '@/api/hooks/useTrading';
import { useToast } from '@/components/ui/Toast';
import { formatNumber } from '@/lib/formatters';
import { TrendingUp, TrendingDown, Flame, Plus, Wifi, WifiOff } from 'lucide-react';
import type { ScreenerCoin } from '@/api/types';

function formatLargeNumber(n: number): string {
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

function PctBadge({ value }: { value: number }) {
  const positive = value >= 0;
  return (
    <span className={`font-mono text-xs font-medium ${positive ? 'text-ct-green' : 'text-ct-red'}`}>
      {positive ? '+' : ''}{value.toFixed(2)}%
    </span>
  );
}

function MomentumBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-xs text-ct-text-dim">—</span>;
  const pct = score * 100;
  const color = score > 0.6 ? 'bg-ct-green' : score < 0.4 ? 'bg-ct-red' : 'bg-ct-yellow';
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-14 h-1.5 bg-ct-border rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-ct-text-muted w-8 text-right">{pct.toFixed(0)}%</span>
    </div>
  );
}

function CoinRow({ coin, onAdd }: { coin: ScreenerCoin; onAdd: (symbol: string) => void }) {
  return (
    <tr className="border-b border-ct-border/30 hover:bg-ct-bg-hover/50">
      <td className="py-2 px-3 text-xs text-ct-text-dim">{coin.cmc_rank}</td>
      <td className="py-2 px-3">
        <div>
          <span className="font-mono text-sm font-medium text-ct-text">{coin.symbol}</span>
          <span className="text-xs text-ct-text-dim ml-1.5">{coin.name}</span>
        </div>
      </td>
      <td className="py-2 px-3 text-right"><PctBadge value={coin.pct_change_1h} /></td>
      <td className="py-2 px-3 text-right"><PctBadge value={coin.pct_change_24h} /></td>
      <td className="py-2 px-3 text-right"><PctBadge value={coin.pct_change_7d} /></td>
      <td className="py-2 px-3 text-right text-xs text-ct-text-muted">{formatLargeNumber(coin.volume_24h)}</td>
      <td className="py-2 px-3 text-right text-xs text-ct-text-muted">{formatLargeNumber(coin.market_cap)}</td>
      <td className="py-2 px-3"><MomentumBar score={coin.momentum_score} /></td>
      <td className="py-2 px-1">
        <button
          onClick={() => onAdd(`${coin.symbol}/USDT`)}
          className="p-1 rounded hover:bg-ct-accent/20 text-ct-text-dim hover:text-ct-accent transition-colors"
          title="Add to watchlist"
        >
          <Plus size={14} />
        </button>
      </td>
    </tr>
  );
}

function CoinTable({ coins, onAdd, emptyMessage }: { coins: ScreenerCoin[]; onAdd: (s: string) => void; emptyMessage: string }) {
  if (coins.length === 0) {
    return <p className="text-sm text-ct-text-dim py-6 text-center">{emptyMessage}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-ct-border text-xs text-ct-text-dim uppercase tracking-wider">
            <th className="py-2 px-3 w-10">#</th>
            <th className="py-2 px-3">Coin</th>
            <th className="py-2 px-3 text-right">1h</th>
            <th className="py-2 px-3 text-right">24h</th>
            <th className="py-2 px-3 text-right">7d</th>
            <th className="py-2 px-3 text-right">Vol 24h</th>
            <th className="py-2 px-3 text-right">MCap</th>
            <th className="py-2 px-3">Momentum</th>
            <th className="py-2 px-1 w-8"></th>
          </tr>
        </thead>
        <tbody>
          {coins.map(c => <CoinRow key={c.symbol} coin={c} onAdd={onAdd} />)}
        </tbody>
      </table>
    </div>
  );
}

export function ScreenerPage() {
  const [gainersLimit] = useState(15);
  const [losersLimit] = useState(10);
  const { data: gainersData, isLoading: loadingGainers } = useTopGainers(gainersLimit);
  const { data: losersData, isLoading: loadingLosers } = useTopLosers(losersLimit);
  const { data: feedStatus } = useCMCFeedStatus();
  const addPair = useAddPair();
  const { toast } = useToast();

  const handleAddPair = (symbol: string) => {
    addPair.mutate(symbol, {
      onSuccess: () => toast(`Added ${symbol} to watchlist`, 'success'),
      onError: (err: Error) => toast(err.message, 'error'),
    });
  };

  const isDisabled = feedStatus && !feedStatus.enabled;

  return (
    <div>
      <PageHeader title="Market Screener" description="CoinMarketCap momentum data — top gainers, losers & momentum scores" />

      {/* Feed Status */}
      <div className="flex items-center gap-3 mb-6">
        {feedStatus && (
          <div className="flex items-center gap-2 text-xs">
            {feedStatus.enabled ? (
              <>
                {feedStatus.healthy ? (
                  <Wifi size={14} className="text-ct-green" />
                ) : (
                  <WifiOff size={14} className="text-ct-red" />
                )}
                <span className="text-ct-text-muted">
                  CMC Feed: {feedStatus.healthy ? 'Connected' : 'Error'} — {feedStatus.listings_count} coins
                </span>
              </>
            ) : (
              <>
                <WifiOff size={14} className="text-ct-text-dim" />
                <span className="text-ct-text-dim">
                  CMC Feed disabled — set <code className="bg-ct-bg-hover px-1 rounded text-ct-accent">CTRADE_FEEDS__COINMARKETCAP_API_KEY</code> to enable
                </span>
              </>
            )}
          </div>
        )}
      </div>

      {isDisabled ? (
        <Card>
          <div className="flex flex-col items-center py-16 text-ct-text-dim">
            <Flame size={48} className="mb-4 opacity-30" />
            <h3 className="text-lg font-medium text-ct-text mb-2">CoinMarketCap Feed Not Configured</h3>
            <p className="text-sm text-center max-w-md mb-4">
              Add your free CoinMarketCap API key to enable the market screener and momentum-boosted trading signals.
            </p>
            <div className="bg-ct-bg-hover border border-ct-border rounded-lg px-4 py-3 font-mono text-xs text-ct-accent">
              set CTRADE_FEEDS__COINMARKETCAP_API_KEY=your-key-here
            </div>
            <p className="text-xs text-ct-text-dim mt-3">
              Get a free API key at coinmarketcap.com/api
            </p>
          </div>
        </Card>
      ) : (
        <div className="space-y-6">
          {/* Top Gainers */}
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={16} className="text-ct-green" />
              <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Top Gainers (24h)</h3>
            </div>
            {loadingGainers ? <Spinner /> : (
              <CoinTable
                coins={gainersData?.coins ?? []}
                onAdd={handleAddPair}
                emptyMessage="No data available yet"
              />
            )}
          </Card>

          {/* Top Losers */}
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <TrendingDown size={16} className="text-ct-red" />
              <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Top Losers (24h)</h3>
            </div>
            {loadingLosers ? <Spinner /> : (
              <CoinTable
                coins={losersData?.coins ?? []}
                onAdd={handleAddPair}
                emptyMessage="No data available yet"
              />
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
