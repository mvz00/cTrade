import { useState } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { NumberInput } from '@/components/ui/NumberInput';
import { useToast } from '@/components/ui/Toast';
import { useTradingMode, useRiskConfig, useUpdateTradingMode, useUpdateRisk } from '@/api/hooks/useConfig';
import {
  usePairs, useAvailablePairs, useAddPair, useRemovePair,
  usePositions, useClosePosition,
  usePortfolio, useEngineStatus, useStartEngine, useStopEngine,
  useActivityLog,
} from '@/api/hooks/useTrading';
import { formatUSD, formatAUD, formatNumber, formatTime } from '@/lib/formatters';
import {
  Play, Square, Plus, X, Zap, Activity,
  TrendingUp, TrendingDown, DollarSign, ShieldAlert,
} from 'lucide-react';

const USDT_TO_AUD = 1.55;

const ACTIVITY_COLORS: Record<string, string> = {
  buy: 'text-ct-green',
  sell: 'text-ct-red',
  sl: 'text-ct-red',
  tp: 'text-ct-green',
  signal: 'text-ct-blue',
  info: 'text-ct-text-muted',
};

const ACTIVITY_ICONS: Record<string, string> = {
  buy: '🟢',
  sell: '🔴',
  sl: '🛑',
  tp: '🎯',
  signal: '📡',
  info: 'ℹ️',
};

export function TradingPage() {
  // --- Local form state ---
  const [newPair, setNewPair] = useState('');

  // Auto-trading form state (initialised from server once loaded)
  const [maxBuy, setMaxBuy] = useState<number | null>(null);
  const [stopLoss, setStopLoss] = useState<number | null>(null);
  const [takeProfit, setTakeProfit] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // --- Data hooks ---
  const { data: mode } = useTradingMode();
  const { data: riskCfg } = useRiskConfig();
  const { data: pairs } = usePairs();
  const { data: availPairs } = useAvailablePairs();
  const { data: positions } = usePositions('open');
  const { data: closedPositions } = usePositions('closed');
  const { data: portfolio, isLoading } = usePortfolio();
  const { data: engine } = useEngineStatus();
  const { data: activityData } = useActivityLog();

  // --- Mutations ---
  const addPair = useAddPair();
  const removePair = useRemovePair();
  const closePos = useClosePosition();
  const startEngine = useStartEngine();
  const stopEngine = useStopEngine();
  const updateTrading = useUpdateTradingMode();
  const updateRisk = useUpdateRisk();
  const { toast } = useToast();

  // Initialise form values from server config (once)
  const effectiveMaxBuy = maxBuy ?? mode?.max_order_usdt ?? 100;
  const effectiveSL = stopLoss ?? (riskCfg ? riskCfg.default_stop_loss_pct * 100 : 3);
  const effectiveTP = takeProfit ?? (riskCfg ? riskCfg.default_take_profit_pct * 100 : 6);

  if (isLoading) return <Spinner />;

  const unwatchedPairs = (availPairs || []).filter(
    p => !(pairs || []).some(wp => wp.symbol === p)
  );

  const isRunning = engine?.running ?? false;
  const isLive = mode?.mode === 'live';

  // --- Start Auto-Trading: save settings then start engine ---
  async function handleStartAutoTrading() {
    setIsSaving(true);
    try {
      // Save max_order_usdt
      await updateTrading.mutateAsync({ max_order_usdt: effectiveMaxBuy });
      // Save SL/TP
      await updateRisk.mutateAsync({
        default_stop_loss_pct: effectiveSL / 100,
        default_take_profit_pct: effectiveTP / 100,
      });
      // Start engine
      await startEngine.mutateAsync(undefined);
      toast('Auto-trading started', 'success');
    } catch (e: any) {
      toast(e.message || 'Failed to start', 'error');
    } finally {
      setIsSaving(false);
    }
  }

  async function handleStopAutoTrading() {
    try {
      await stopEngine.mutateAsync(undefined);
      toast('Auto-trading stopped', 'success');
    } catch (e: any) {
      toast(e.message || 'Failed to stop', 'error');
    }
  }

  return (
    <div>
      <PageHeader
        title="Trading"
        description={isLive ? 'Live trading — real exchange balances' : 'Paper trading — $10K virtual balance'}
        actions={
          <Badge variant={isLive ? 'danger' : 'warning'}>
            {isLive ? 'Live' : 'Paper'} Trading
          </Badge>
        }
      />

      {/* ── Auto-Trading Control Panel ── */}
      <Card className="mb-6 border-ct-accent/20">
        <div className="flex items-center gap-2 mb-4">
          <Zap size={18} className="text-ct-accent" />
          <h2 className="text-base font-semibold text-ct-text">Auto-Trading</h2>
          {isRunning && (
            <Badge variant="success">
              Running — Tick #{engine?.tick_count ?? 0}
            </Badge>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-4">
          <NumberInput
            label="Max Buy Amount"
            value={effectiveMaxBuy}
            onChange={v => setMaxBuy(v)}
            min={1}
            max={100000}
            step={10}
            suffix="USDT"
          />
          <NumberInput
            label="Stop Loss"
            value={effectiveSL}
            onChange={v => setStopLoss(v)}
            min={0.5}
            max={50}
            step={0.5}
            suffix="%"
          />
          <NumberInput
            label="Take Profit"
            value={effectiveTP}
            onChange={v => setTakeProfit(v)}
            min={0.5}
            max={100}
            step={0.5}
            suffix="%"
          />
        </div>

        <div className="flex items-center gap-3">
          {isRunning ? (
            <Button
              variant="danger"
              onClick={handleStopAutoTrading}
              disabled={stopEngine.isPending}
            >
              <Square size={14} /> Stop Auto-Trading
            </Button>
          ) : (
            <Button
              onClick={handleStartAutoTrading}
              disabled={isSaving || startEngine.isPending}
            >
              <Play size={14} /> Start Auto-Trading
            </Button>
          )}
          <span className="text-xs text-ct-text-dim">
            {isRunning
              ? `Analyzing ${(pairs || []).length} pairs every 30s`
              : 'Settings are saved when you click Start'}
          </span>
        </div>
      </Card>

      {/* ── Portfolio Summary ── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <Card>
          <div className="flex items-center gap-1.5 mb-1">
            <DollarSign size={13} className="text-ct-text-dim" />
            <span className="text-xs text-ct-text-muted uppercase">Portfolio</span>
          </div>
          <div className="text-lg font-semibold text-ct-text">
            {formatUSD(portfolio?.total_value_usd ?? 0)}
          </div>
          <div className="text-xs text-ct-text-dim">
            {formatAUD((portfolio?.total_value_usd ?? 0) * USDT_TO_AUD)}
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-1.5 mb-1">
            {(portfolio?.daily_pnl ?? 0) >= 0
              ? <TrendingUp size={13} className="text-ct-green" />
              : <TrendingDown size={13} className="text-ct-red" />}
            <span className="text-xs text-ct-text-muted uppercase">Daily P&L</span>
          </div>
          <div className={`text-lg font-semibold ${(portfolio?.daily_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}`}>
            {formatUSD(portfolio?.daily_pnl ?? 0)}
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-1.5 mb-1">
            <Activity size={13} className="text-ct-text-dim" />
            <span className="text-xs text-ct-text-muted uppercase">Open</span>
          </div>
          <div className="text-lg font-semibold text-ct-text">
            {portfolio?.open_positions ?? 0}
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-1.5 mb-1">
            <DollarSign size={13} className="text-ct-text-dim" />
            <span className="text-xs text-ct-text-muted uppercase">Cash</span>
          </div>
          <div className="text-lg font-semibold text-ct-text">
            {formatUSD(portfolio?.cash_balance?.USDT ?? 0)}
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-1.5 mb-1">
            <ShieldAlert size={13} className="text-ct-text-dim" />
            <span className="text-xs text-ct-text-muted uppercase">Engine</span>
          </div>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-ct-green animate-pulse' : 'bg-ct-text-dim'}`} />
            <span className="text-sm text-ct-text">
              {isRunning ? `Tick ${engine?.tick_count}` : 'Stopped'}
            </span>
          </div>
        </Card>
      </div>

      {/* ── Watched Pairs + Open Positions ── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Watched Pairs */}
        <Card>
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Watched Pairs</h3>
          <div className="space-y-2 mb-4">
            {(pairs || []).length === 0 && (
              <p className="text-sm text-ct-text-dim">
                Pairs will auto-populate when the engine starts.
              </p>
            )}
            {(pairs || []).map(p => (
              <div key={p.symbol} className="flex items-center justify-between py-1.5 px-2 rounded bg-ct-bg-hover">
                <span className="text-sm font-mono text-ct-text">{p.symbol}</span>
                <button
                  onClick={() => removePair.mutate(p.symbol)}
                  className="text-ct-text-dim hover:text-ct-red"
                >
                  <X size={14} />
                </button>
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <select
              value={newPair}
              onChange={e => setNewPair(e.target.value)}
              className="flex-1 bg-ct-bg border border-ct-border rounded-lg px-2 py-1.5 text-sm text-ct-text"
            >
              <option value="">Add pair...</option>
              {unwatchedPairs.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <Button
              onClick={() => {
                if (newPair) addPair.mutate(newPair, {
                  onSuccess: () => { toast(`Added ${newPair}`, 'success'); setNewPair(''); },
                  onError: (e) => toast(e.message, 'error'),
                });
              }}
              disabled={!newPair}
            >
              <Plus size={14} />
            </Button>
          </div>
        </Card>

        {/* Open Positions */}
        <Card className="lg:col-span-3">
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Open Positions</h3>
          {(positions || []).length === 0 ? (
            <p className="text-sm text-ct-text-dim py-8 text-center">No open positions</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ct-border text-ct-text-muted text-left">
                    <th className="pb-2">Pair</th>
                    <th className="pb-2">Side</th>
                    <th className="pb-2">Qty</th>
                    <th className="pb-2">Entry</th>
                    <th className="pb-2">SL / TP</th>
                    <th className="pb-2">P&L</th>
                    <th className="pb-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {(positions || []).map(p => (
                    <tr key={p.id} className="border-b border-ct-border/50">
                      <td className="py-2 font-mono">{p.pair_symbol}</td>
                      <td>
                        <Badge variant={p.side === 'long' ? 'success' : 'danger'}>{p.side}</Badge>
                      </td>
                      <td>{formatNumber(p.quantity, 6)}</td>
                      <td>{formatUSD(p.entry_price)}</td>
                      <td className="text-xs text-ct-text-dim">
                        {p.stop_loss ? formatUSD(p.stop_loss) : '—'}
                        {' / '}
                        {p.take_profit ? formatUSD(p.take_profit) : '—'}
                      </td>
                      <td className={(p.unrealized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>
                        {formatUSD(p.unrealized_pnl ?? 0)}
                      </td>
                      <td>
                        <button
                          onClick={() => closePos.mutate(p.id, {
                            onSuccess: () => toast('Position closed', 'success'),
                            onError: (e) => toast(e.message, 'error'),
                          })}
                          className="text-ct-text-dim hover:text-ct-red"
                        >
                          <X size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* ── Live Activity Log ── */}
      <Card className="mt-6">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={16} className="text-ct-accent" />
          <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Live Activity</h3>
          {isRunning && (
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ct-green opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-ct-green" />
            </span>
          )}
        </div>
        {(!activityData || activityData.length === 0) ? (
          <p className="text-sm text-ct-text-dim py-6 text-center">
            {isRunning ? 'Waiting for first tick…' : 'Start auto-trading to see live activity'}
          </p>
        ) : (
          <div className="space-y-1 max-h-72 overflow-y-auto font-mono text-xs">
            {activityData.map((entry, i) => (
              <div key={`${entry.time}-${i}`} className="flex items-start gap-2 py-1 px-2 rounded hover:bg-ct-bg-hover">
                <span className="text-ct-text-dim whitespace-nowrap">
                  {formatTime(entry.time)}
                </span>
                <span className="w-4 text-center flex-shrink-0">
                  {ACTIVITY_ICONS[entry.type] ?? '•'}
                </span>
                <span className={`uppercase text-[10px] font-bold w-10 flex-shrink-0 ${ACTIVITY_COLORS[entry.type] ?? 'text-ct-text-muted'}`}>
                  {entry.type}
                </span>
                <span className="text-ct-text-muted flex-shrink-0 w-20">
                  {entry.pair || '—'}
                </span>
                <span className={ACTIVITY_COLORS[entry.type] ?? 'text-ct-text'}>
                  {entry.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── Trade History ── */}
      <Card className="mt-6">
        <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider mb-3">Trade History</h3>
        {(closedPositions || []).length === 0 ? (
          <p className="text-sm text-ct-text-dim py-4 text-center">No closed trades</p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {(closedPositions || []).slice(0, 30).map(p => (
              <div key={p.id} className="flex items-center justify-between py-1.5 px-2 rounded bg-ct-bg-hover text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-mono">{p.pair_symbol}</span>
                  <Badge variant={p.side === 'long' ? 'success' : 'danger'}>{p.side}</Badge>
                </div>
                <span className={(p.realized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>
                  {formatUSD(p.realized_pnl ?? 0)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
