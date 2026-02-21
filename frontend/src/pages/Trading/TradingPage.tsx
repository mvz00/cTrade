import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { Select } from '@/components/ui/Select';
import { NumberInput } from '@/components/ui/NumberInput';
import { useToast } from '@/components/ui/Toast';
import { useTradingMode } from '@/api/hooks/useConfig';
import {
  usePairs, useAvailablePairs, useAddPair, useRemovePair,
  useOrders, usePlaceOrder, usePositions, useClosePosition,
  usePortfolio, useEngineStatus, useStartEngine, useStopEngine,
} from '@/api/hooks/useTrading';
import { formatUSD, formatNumber } from '@/lib/formatters';
import { Play, Square, Plus, X, ArrowUpDown } from 'lucide-react';

export function TradingPage() {
  const { data: mode } = useTradingMode();
  const { data: pairs } = usePairs();
  const { data: availPairs } = useAvailablePairs();
  const { data: orders } = useOrders();
  const { data: positions } = usePositions('open');
  const { data: closedPositions } = usePositions('closed');
  const { data: portfolio, isLoading } = usePortfolio();
  const { data: engine } = useEngineStatus();
  const addPair = useAddPair();
  const removePair = useRemovePair();
  const placeOrder = usePlaceOrder();
  const closePos = useClosePosition();
  const startEngine = useStartEngine();
  const stopEngine = useStopEngine();
  const { toast } = useToast();

  const [selectedPair, setSelectedPair] = useState('BTC/USDT');
  const [orderSide, setOrderSide] = useState<'buy' | 'sell'>('buy');
  const [orderQty, setOrderQty] = useState(0.01);
  const [newPair, setNewPair] = useState('');

  if (isLoading) return <Spinner />;

  const unwatchedPairs = (availPairs || []).filter(
    p => !(pairs || []).some(wp => wp.symbol === p)
  );

  return (
    <div>
      <PageHeader
        title="Trading"
        description="Paper trading engine and order management"
        actions={
          <div className="flex items-center gap-3">
            <Badge variant={mode?.mode === 'live' ? 'danger' : 'warning'}>
              {mode?.mode === 'live' ? 'Live' : 'Paper'} Trading
            </Badge>
            {engine?.running ? (
              <Button variant="danger" onClick={() => stopEngine.mutate(undefined, {
                onSuccess: () => toast('Engine stopped', 'success'),
                onError: (e) => toast(e.message, 'error'),
              })}>
                <Square size={14} /> Stop Engine
              </Button>
            ) : (
              <Button onClick={() => startEngine.mutate(undefined, {
                onSuccess: () => toast('Engine started', 'success'),
                onError: (e) => toast(e.message, 'error'),
              })}>
                <Play size={14} /> Start Engine
              </Button>
            )}
          </div>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-5 gap-4 mb-6">
        <Card><div className="text-xs text-ct-text-muted uppercase mb-1">Portfolio Value</div><div className="text-xl font-semibold text-ct-text">{formatUSD(portfolio?.total_value_usd ?? 10000)}</div></Card>
        <Card><div className="text-xs text-ct-text-muted uppercase mb-1">Daily P&L</div><div className={`text-xl font-semibold ${(portfolio?.daily_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}`}>{formatUSD(portfolio?.daily_pnl ?? 0)}</div></Card>
        <Card><div className="text-xs text-ct-text-muted uppercase mb-1">Open Positions</div><div className="text-xl font-semibold text-ct-text">{portfolio?.open_positions ?? 0}</div></Card>
        <Card><div className="text-xs text-ct-text-muted uppercase mb-1">Cash (USDT)</div><div className="text-xl font-semibold text-ct-text">{formatUSD(portfolio?.cash_balance?.USDT ?? 10000)}</div></Card>
        <Card><div className="text-xs text-ct-text-muted uppercase mb-1">Engine</div><div className="flex items-center gap-2"><div className={`w-2 h-2 rounded-full ${engine?.running ? 'bg-ct-green' : 'bg-ct-text-dim'}`} /><span className="text-sm text-ct-text">{engine?.running ? `Tick ${engine.tick_count}` : 'Stopped'}</span></div></Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Watched Pairs</h3>
          <div className="space-y-2 mb-4">
            {(pairs || []).length === 0 && <p className="text-sm text-ct-text-dim">No pairs. Add one below.</p>}
            {(pairs || []).map(p => (
              <div key={p.symbol} className="flex items-center justify-between py-1.5 px-2 rounded bg-ct-bg-hover">
                <span className="text-sm font-mono text-ct-text">{p.symbol}</span>
                <button onClick={() => removePair.mutate(p.symbol)} className="text-ct-text-dim hover:text-ct-red"><X size={14} /></button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <select value={newPair} onChange={e => setNewPair(e.target.value)} className="flex-1 bg-ct-bg border border-ct-border rounded-lg px-2 py-1.5 text-sm text-ct-text">
              <option value="">Select pair...</option>
              {unwatchedPairs.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <Button onClick={() => { if (newPair) addPair.mutate(newPair, { onSuccess: () => { toast(`Added ${newPair}`, 'success'); setNewPair(''); }, onError: (e) => toast(e.message, 'error') }); }} disabled={!newPair}><Plus size={14} /></Button>
          </div>
        </Card>

        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Place Order</h3>
          <div className="space-y-3">
            <Select label="Pair" value={selectedPair} onChange={v => setSelectedPair(v)}
              options={[...(pairs || []).map(p => ({ value: p.symbol, label: p.symbol })), ...unwatchedPairs.map(p => ({ value: p, label: p }))]} />
            <div className="flex gap-2">
              <button onClick={() => setOrderSide('buy')} className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${orderSide === 'buy' ? 'bg-ct-green text-white' : 'bg-ct-bg-hover text-ct-text-muted'}`}>Buy</button>
              <button onClick={() => setOrderSide('sell')} className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${orderSide === 'sell' ? 'bg-ct-red text-white' : 'bg-ct-bg-hover text-ct-text-muted'}`}>Sell</button>
            </div>
            <NumberInput label="Quantity" value={orderQty} onChange={v => setOrderQty(v)} min={0.0001} step={0.001} />
            <Button className="w-full" variant={orderSide === 'buy' ? 'primary' : 'danger'}
              onClick={() => placeOrder.mutate({ symbol: selectedPair, side: orderSide, order_type: 'market', quantity: orderQty }, { onSuccess: (o) => toast(`${orderSide.toUpperCase()} ${o.status}`, 'success'), onError: (e) => toast(e.message, 'error') })}
              disabled={placeOrder.isPending}>
              <ArrowUpDown size={14} /> {orderSide === 'buy' ? 'Buy' : 'Sell'} {selectedPair}
            </Button>
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Open Positions</h3>
          {(positions || []).length === 0 ? (
            <p className="text-sm text-ct-text-dim py-8 text-center">No open positions</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-ct-border text-ct-text-muted text-left"><th className="pb-2">Pair</th><th className="pb-2">Side</th><th className="pb-2">Qty</th><th className="pb-2">Entry</th><th className="pb-2">P&L</th><th className="pb-2"></th></tr></thead>
                <tbody>
                  {(positions || []).map(p => (
                    <tr key={p.id} className="border-b border-ct-border/50">
                      <td className="py-2 font-mono">{p.pair_symbol}</td>
                      <td><Badge variant={p.side === 'long' ? 'success' : 'danger'}>{p.side}</Badge></td>
                      <td>{formatNumber(p.quantity, 6)}</td>
                      <td>{formatUSD(p.entry_price)}</td>
                      <td className={(p.unrealized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>{formatUSD(p.unrealized_pnl ?? 0)}</td>
                      <td><button onClick={() => closePos.mutate(p.id, { onSuccess: () => toast('Position closed', 'success'), onError: (e) => toast(e.message, 'error') })} className="text-ct-text-dim hover:text-ct-red"><X size={14} /></button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Recent Orders</h3>
          {(orders || []).length === 0 ? <p className="text-sm text-ct-text-dim py-4 text-center">No orders yet</p> : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(orders || []).slice(0, 20).map(o => (
                <div key={o.id} className="flex items-center justify-between py-1.5 px-2 rounded bg-ct-bg-hover text-sm">
                  <div className="flex items-center gap-2"><Badge variant={o.side === 'buy' ? 'success' : 'danger'}>{o.side}</Badge><span className="font-mono">{o.pair_symbol}</span></div>
                  <div className="flex items-center gap-3 text-ct-text-muted"><span>{formatNumber(o.quantity, 6)}</span><Badge variant={o.status === 'filled' ? 'success' : o.status === 'rejected' ? 'danger' : 'default'}>{o.status}</Badge></div>
                </div>
              ))}
            </div>
          )}
        </Card>
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Trade History</h3>
          {(closedPositions || []).length === 0 ? <p className="text-sm text-ct-text-dim py-4 text-center">No closed trades</p> : (
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {(closedPositions || []).slice(0, 20).map(p => (
                <div key={p.id} className="flex items-center justify-between py-1.5 px-2 rounded bg-ct-bg-hover text-sm">
                  <div className="flex items-center gap-2"><span className="font-mono">{p.pair_symbol}</span><Badge variant={p.side === 'long' ? 'success' : 'danger'}>{p.side}</Badge></div>
                  <span className={(p.realized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>{formatUSD(p.realized_pnl ?? 0)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
