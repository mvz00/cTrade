import { Fragment, useState, useCallback } from 'react';
import { PageHeader } from '@/components/ui/PageHeader';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Spinner } from '@/components/ui/Spinner';
import { NumberInput } from '@/components/ui/NumberInput';
import { useToast } from '@/components/ui/Toast';
import { useTradingMode, useRiskConfig, useUpdateTradingMode, useUpdateRisk } from '@/api/hooks/useConfig';
import {
  usePairs, useAvailablePairs, useAddPairsBatch, useRemovePair,
  usePositions, useClosePosition, useCloseAllPositions,
  usePortfolio, useEngineStatus, useStartEngine, useStopEngine,
  useActivityLog,
} from '@/api/hooks/useTrading';
import { formatUSD, formatAUD, formatNumber, formatTime } from '@/lib/formatters';
import { useQueryClient } from '@tanstack/react-query';
import { useWebSocket } from '@/api/hooks/useWebSocket';
import {
  Play, Square, Plus, X, Zap, Activity, Search,
  TrendingUp, TrendingDown, DollarSign, ShieldAlert,
  Download, ChevronDown, ChevronUp, History,
} from 'lucide-react';

const USDT_TO_AUD = 1.55;
const API_BASE = '/api/v1';

const ACTIVITY_COLORS: Record<string, string> = {
  buy: 'text-ct-green',
  sell: 'text-ct-red',
  sl: 'text-ct-red',
  tp: 'text-ct-green',
  signal: 'text-ct-blue',
  info: 'text-ct-text-muted',
  error: 'text-orange-400',
};

const ACTIVITY_ICONS: Record<string, string> = {
  buy: '🟢',
  sell: '🔴',
  sl: '🛑',
  tp: '🎯',
  signal: '📡',
  info: 'ℹ️',
  error: '⚠️',
};

// Events that should trigger Trading page cache invalidation
const TRADING_WS_EVENTS = [
  'order.created',
  'order.filled',
  'order.cancelled',
  'position.opened',
  'position.closed',
  'risk.stop_loss_hit',
  'risk.take_profit_hit',
];

export function TradingPage() {
  // --- WebSocket for live updates ---
  const queryClient = useQueryClient();

  const handleWsMessage = useCallback(
    (msg: { type: string }) => {
      if (TRADING_WS_EVENTS.includes(msg.type)) {
        queryClient.invalidateQueries({ queryKey: ['trading'] });
      }
    },
    [queryClient],
  );

  useWebSocket({
    subscriptions: TRADING_WS_EVENTS,
    onMessage: handleWsMessage,
  });

  // --- Local form state ---
  const [pairSearch, setPairSearch] = useState('');
  const [selectedNewPairs, setSelectedNewPairs] = useState<Set<string>>(new Set());
  const [showPairPicker, setShowPairPicker] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Auto-trading form state
  const [maxBuy, setMaxBuy] = useState<number | null>(null);
  const [maxConcurrentTrades, setMaxConcurrentTrades] = useState<number | null>(null);
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
  const addPairsBatch = useAddPairsBatch();
  const removePair = useRemovePair();
  const closePos = useClosePosition();
  const closeAllPos = useCloseAllPositions();
  const startEngine = useStartEngine();
  const stopEngine = useStopEngine();
  const updateTrading = useUpdateTradingMode();
  const updateRisk = useUpdateRisk();
  const { toast } = useToast();

  // Initialise form values from server config (once)
  const effectiveMaxBuy = maxBuy ?? mode?.max_order_usdt ?? 100;
  const effectiveMaxTrades = maxConcurrentTrades ?? mode?.max_open_positions ?? 5;
  const effectiveSL = stopLoss ?? (riskCfg ? riskCfg.default_stop_loss_pct * 100 : 3);
  const effectiveTP = takeProfit ?? (riskCfg ? riskCfg.default_take_profit_pct * 100 : 6);

  if (isLoading) return <Spinner />;

  const watchedSymbols = new Set((pairs || []).map(p => p.symbol));
  const unwatchedPairs = (availPairs || []).filter(p => !watchedSymbols.has(p));
  const filteredUnwatched = pairSearch
    ? unwatchedPairs.filter(p => p.toLowerCase().includes(pairSearch.toLowerCase()))
    : unwatchedPairs;

  const isRunning = engine?.running ?? false;
  const isLive = mode?.mode === 'live';

  // --- Handlers ---
  async function handleStartAutoTrading() {
    setIsSaving(true);
    try {
      await updateTrading.mutateAsync({
        max_order_usdt: effectiveMaxBuy,
        max_open_positions: effectiveMaxTrades,
      });
      await updateRisk.mutateAsync({
        default_stop_loss_pct: effectiveSL / 100,
        default_take_profit_pct: effectiveTP / 100,
      });
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

  function togglePairSelection(symbol: string) {
    setSelectedNewPairs(prev => {
      const next = new Set(prev);
      if (next.has(symbol)) next.delete(symbol);
      else next.add(symbol);
      return next;
    });
  }

  // Select All: operates on the currently visible (filtered + sliced) pairs
  const visiblePairs = filteredUnwatched.slice(0, 200);
  const allVisibleSelected = visiblePairs.length > 0 && visiblePairs.every(p => selectedNewPairs.has(p));
  const someVisibleSelected = visiblePairs.some(p => selectedNewPairs.has(p));

  function handleSelectAll() {
    setSelectedNewPairs(prev => {
      const next = new Set(prev);
      if (allVisibleSelected) {
        // Deselect all visible
        for (const p of visiblePairs) next.delete(p);
      } else {
        // Select all visible
        for (const p of visiblePairs) next.add(p);
      }
      return next;
    });
  }

  function handleAddSelectedPairs() {
    if (selectedNewPairs.size === 0) return;
    addPairsBatch.mutate([...selectedNewPairs], {
      onSuccess: () => {
        toast(`Added ${selectedNewPairs.size} pairs`, 'success');
        setSelectedNewPairs(new Set());
        setShowPairPicker(false);
        setPairSearch('');
      },
      onError: (e) => toast(e.message, 'error'),
    });
  }

  function handleDownloadCSV() {
    const link = document.createElement('a');
    link.href = `${API_BASE}/trading/history/export`;
    link.download = 'trade_history.csv';
    link.click();
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

      {/* ── Live Activity Log (top, scrolling) ── */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-ct-accent" />
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Live Activity</h3>
            {isRunning && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-ct-green opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-ct-green" />
              </span>
            )}
          </div>
          {isRunning && (
            <span className="text-xs text-ct-text-dim">Tick #{engine?.tick_count ?? 0}</span>
          )}
        </div>
        {(!activityData || activityData.length === 0) ? (
          <p className="text-sm text-ct-text-dim py-3 text-center">
            {isRunning ? 'Waiting for first tick…' : 'Start auto-trading to see live activity'}
          </p>
        ) : (
          <div className="space-y-0.5 max-h-40 overflow-y-auto font-mono text-xs">
            {activityData.map((entry, i) => (
              <div key={`${entry.time}-${i}`} className="flex items-start gap-2 py-0.5 px-2 rounded hover:bg-ct-bg-hover">
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

      {/* ── Auto-Trading Control Panel ── */}
      <Card className="mb-6 border-ct-accent/20">
        <div className="flex items-center gap-2 mb-4">
          <Zap size={18} className="text-ct-accent" />
          <h2 className="text-base font-semibold text-ct-text">Auto-Trading</h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
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
            label="Max Concurrent Trades"
            value={effectiveMaxTrades}
            onChange={v => setMaxConcurrentTrades(v)}
            min={1}
            max={50}
            step={1}
            suffix=""
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
            {formatUSD(Object.values(portfolio?.cash_balance ?? {}).reduce((s, v) => s + v, 0))}
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

      {/* ── Watched Pairs (compact) + Open Positions ── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-6">
        {/* Watched Pairs — compact inline chips + multi-select picker */}
        <Card>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">
              Watched ({(pairs || []).length})
            </h3>
            <button
              onClick={() => setShowPairPicker(!showPairPicker)}
              className="text-ct-accent hover:text-ct-accent/80 text-xs flex items-center gap-1"
            >
              <Plus size={12} /> Add
              {showPairPicker ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          </div>

          {/* Current pairs as compact chips */}
          <div className="flex flex-wrap gap-1.5 mb-3">
            {(pairs || []).length === 0 && (
              <p className="text-xs text-ct-text-dim">Auto-populated on start</p>
            )}
            {(pairs || []).map(p => (
              <span key={p.symbol} className="inline-flex items-center gap-1 bg-ct-bg-hover rounded px-2 py-0.5 text-xs font-mono text-ct-text">
                {p.symbol}
                <button
                  onClick={() => removePair.mutate(p.symbol)}
                  className="text-ct-text-dim hover:text-ct-red"
                >
                  <X size={10} />
                </button>
              </span>
            ))}
          </div>

          {/* Multi-select pair picker */}
          {showPairPicker && (
            <div className="border border-ct-border rounded-lg overflow-hidden">
              <div className="flex items-center gap-2 px-2 py-1.5 border-b border-ct-border bg-ct-bg">
                <Search size={12} className="text-ct-text-dim" />
                <input
                  type="text"
                  value={pairSearch}
                  onChange={e => setPairSearch(e.target.value)}
                  placeholder="Search pairs..."
                  className="flex-1 bg-transparent text-xs text-ct-text outline-none placeholder:text-ct-text-dim"
                />
              </div>
              <div className="max-h-36 overflow-y-auto">
                {filteredUnwatched.length === 0 ? (
                  <p className="text-xs text-ct-text-dim py-2 text-center">No matches</p>
                ) : (
                  <>
                  {/* Select All */}
                  <label className="flex items-center gap-2 px-2 py-1 hover:bg-ct-bg-hover cursor-pointer text-xs border-b border-ct-border sticky top-0 bg-ct-bg z-10">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      ref={el => { if (el) el.indeterminate = someVisibleSelected && !allVisibleSelected; }}
                      onChange={handleSelectAll}
                      className="rounded border-ct-border text-ct-accent"
                    />
                    <span className="font-medium text-ct-text-muted">
                      Select All ({visiblePairs.length})
                    </span>
                  </label>
                  {visiblePairs.map(p => (
                    <label
                      key={p}
                      className="flex items-center gap-2 px-2 py-1 hover:bg-ct-bg-hover cursor-pointer text-xs"
                    >
                      <input
                        type="checkbox"
                        checked={selectedNewPairs.has(p)}
                        onChange={() => togglePairSelection(p)}
                        className="rounded border-ct-border text-ct-accent"
                      />
                      <span className="font-mono text-ct-text">{p}</span>
                    </label>
                  ))}
                  </>
                )}
              </div>
              {selectedNewPairs.size > 0 && (
                <div className="px-2 py-1.5 border-t border-ct-border bg-ct-bg flex items-center justify-between">
                  <span className="text-xs text-ct-text-muted">{selectedNewPairs.size} selected</span>
                  <Button
                    onClick={handleAddSelectedPairs}
                    disabled={addPairsBatch.isPending}
                  >
                    <Plus size={12} /> Add
                  </Button>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* Open Positions */}
        <Card className="lg:col-span-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">
              Open Positions ({(positions || []).length})
            </h3>
            {(positions || []).length > 0 && (
              <Button
                variant="danger"
                onClick={() => closeAllPos.mutate(undefined, {
                  onSuccess: (data) => {
                    const msg = data.failed > 0
                      ? `Closed ${data.closed}, ${data.failed} failed`
                      : `Closed ${data.closed} positions`;
                    toast(msg, data.failed > 0 ? 'error' : 'success');
                  },
                  onError: (e) => toast(e.message, 'error'),
                })}
                disabled={closeAllPos.isPending}
              >
                <X size={12} /> Close All
              </Button>
            )}
          </div>
          {(positions || []).length === 0 ? (
            <p className="text-sm text-ct-text-dim py-8 text-center">No open positions</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-ct-border text-ct-text-muted text-left">
                    <th className="pb-2">Pair</th>
                    <th className="pb-2">Exchange</th>
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
                    <Fragment key={p.id}>
                      <tr className="border-b border-ct-border/50">
                        <td className="py-2 font-mono">{p.pair_symbol}</td>
                        <td className="text-xs text-ct-text-dim capitalize">{p.exchange_name || '—'}</td>
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
                          <span className="text-xs text-ct-text-dim ml-1">
                            ({(p.unrealized_pnl_pct ?? 0).toFixed(2)}%)
                          </span>
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
                      {p.justification && (
                        <tr>
                          <td colSpan={8} className="pb-2 px-1">
                            <p className="text-xs text-ct-text-dim italic leading-relaxed">
                              {p.justification}
                            </p>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* ── Trade History (collapsible + download) ── */}
      <Card>
        <div className="flex items-center justify-between mb-2">
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex items-center gap-2 text-sm font-medium text-ct-text-muted uppercase tracking-wider hover:text-ct-text"
          >
            <History size={14} />
            Trade History ({(closedPositions || []).length})
            {showHistory ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
          {(closedPositions || []).length > 0 && (
            <button
              onClick={handleDownloadCSV}
              className="flex items-center gap-1 text-xs text-ct-accent hover:text-ct-accent/80"
            >
              <Download size={12} /> Export CSV
            </button>
          )}
        </div>
        {showHistory && (
          <>
            {(closedPositions || []).length === 0 ? (
              <p className="text-sm text-ct-text-dim py-4 text-center">No closed trades</p>
            ) : (
              <div className="overflow-x-auto max-h-72 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-ct-card">
                    <tr className="border-b border-ct-border text-ct-text-muted text-left">
                      <th className="pb-2">Pair</th>
                      <th className="pb-2">Exchange</th>
                      <th className="pb-2">Side</th>
                      <th className="pb-2">Entry</th>
                      <th className="pb-2">Exit</th>
                      <th className="pb-2">Qty</th>
                      <th className="pb-2">P&L</th>
                      <th className="pb-2">P&L %</th>
                      <th className="pb-2">Closed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(closedPositions || []).map(p => (
                      <tr key={p.id} className="border-b border-ct-border/50">
                        <td className="py-1.5 font-mono">{p.pair_symbol}</td>
                        <td className="text-xs text-ct-text-dim capitalize">{p.exchange_name || '—'}</td>
                        <td>
                          <Badge variant={p.side === 'long' ? 'success' : 'danger'}>{p.side}</Badge>
                        </td>
                        <td>{formatUSD(p.entry_price)}</td>
                        <td>{p.exit_price ? formatUSD(p.exit_price) : '—'}</td>
                        <td>{formatNumber(p.quantity, 6)}</td>
                        <td className={(p.realized_pnl ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>
                          {formatUSD(p.realized_pnl ?? 0)}
                        </td>
                        <td className={(p.realized_pnl_pct ?? 0) >= 0 ? 'text-ct-green' : 'text-ct-red'}>
                          {(p.realized_pnl_pct ?? 0).toFixed(2)}%
                        </td>
                        <td className="text-xs text-ct-text-dim">
                          {p.closed_at ? formatTime(p.closed_at) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>
    </div>
  );
}
