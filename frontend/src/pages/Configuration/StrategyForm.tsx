import { useStrategyConfig, useUpdateStrategy } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { NumberInput } from '@/components/ui/NumberInput';
import { RangeSlider } from '@/components/ui/RangeSlider';
import { SourcePrioritySlider } from '@/components/ui/SourcePrioritySlider';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { Sliders, TrendingUp, Brain, Activity } from 'lucide-react';
import { useEffect, useState } from 'react';

const RISK_MARKERS = [
  { value: 1, label: '1' },
  { value: 3, label: '3' },
  { value: 5, label: '5' },
  { value: 7, label: '7' },
  { value: 10, label: '10' },
];

/** Derive entry/exit thresholds from risk appetite (mirrors backend formula). */
function deriveThresholds(appetite: number) {
  const halfZone = 0.10 - (appetite - 1) * 0.01;
  return {
    entry: +(0.50 + halfZone).toFixed(2),
    exit: +(0.50 - halfZone).toFixed(2),
  };
}

/** Compute percentage contribution for a category slider. */
function pct(value: number, total: number): number {
  return total > 0 ? (value / total) * 100 : 0;
}

export function StrategyForm() {
  const { data: strategy } = useStrategyConfig();
  const updateStrategy = useUpdateStrategy();
  const { toast } = useToast();

  const [screener, setScreener] = useState(50);
  const [intelligence, setIntelligence] = useState(50);
  const [signals, setSignals] = useState(50);
  const [strategyMode, setStrategyMode] = useState('long_only');
  const [shortMinChange, setShortMinChange] = useState(2.0);
  const [riskAppetite, setRiskAppetite] = useState(5);
  const [minHold, setMinHold] = useState(15);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (strategy) {
      setScreener(strategy.screener_priority ?? 50);
      setIntelligence(strategy.intelligence_priority ?? 50);
      setSignals(strategy.signals_priority ?? 50);
      setStrategyMode(strategy.strategy_mode || 'long_only');
      setShortMinChange(strategy.short_min_1h_change_pct ?? 2.0);
      setRiskAppetite(strategy.risk_appetite ?? 5);
      setMinHold(strategy.min_hold_minutes ?? 15);
      setDirty(false);
    }
  }, [strategy]);

  const total = screener + intelligence + signals;
  const thresholds = deriveThresholds(riskAppetite);

  function handleSave() {
    updateStrategy.mutate(
      {
        screener_priority: screener,
        intelligence_priority: intelligence,
        signals_priority: signals,
        strategy_mode: strategyMode,
        short_min_1h_change_pct: shortMinChange,
        risk_appetite: riskAppetite,
        min_hold_minutes: minHold,
      },
      {
        onSuccess: () => {
          toast('Strategy config saved', 'success');
          setDirty(false);
        },
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  function setAndDirty(setter: (v: number) => void) {
    return (v: number) => {
      setter(v);
      setDirty(true);
    };
  }

  return (
    <Card>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-ct-accent/10">
          <Sliders size={18} className="text-ct-accent" />
        </div>
        <CardTitle className="mb-0">Strategy Settings</CardTitle>
      </div>

      <div className="space-y-3">
        <Select
          label="Strategy Mode"
          value={strategyMode}
          onChange={(v) => { setStrategyMode(v); setDirty(true); }}
          options={[
            { value: 'long_only', label: 'Long Only (Buy & Hold)' },
            { value: 'short_only', label: 'Short Only (High Momentum)' },
            { value: 'both', label: 'Both (Long & Short)' },
          ]}
        />

        {(strategyMode === 'short_only' || strategyMode === 'both') && (
          <NumberInput
            label="Short Min 1h Change"
            value={shortMinChange}
            onChange={(v) => { setShortMinChange(v); setDirty(true); }}
            min={0.5}
            max={20}
            step={0.5}
            suffix="%"
          />
        )}

        <NumberInput
          label="Min Hold Period"
          value={minHold}
          onChange={(v) => { setMinHold(v); setDirty(true); }}
          min={0}
          max={120}
          step={1}
          suffix=" min"
        />

        <div className="border-t border-ct-border pt-3 mt-3">
          <p className="text-xs font-medium text-ct-text-dim mb-2">Risk Appetite</p>
        </div>

        <RangeSlider
          label="Risk Appetite"
          value={riskAppetite}
          onChange={setAndDirty(setRiskAppetite)}
          min={1}
          max={10}
          step={1}
          markers={RISK_MARKERS}
          info={`Entry threshold: ${(thresholds.entry * 100).toFixed(0)}% \u00b7 Exit threshold: ${(thresholds.exit * 100).toFixed(0)}%`}
        />

        <div className="border-t border-ct-border pt-3 mt-3">
          <p className="text-xs font-medium text-ct-text-dim mb-1">Source Priorities</p>
          <p className="text-xs text-ct-text-dim mb-3">
            Adjust how strongly each data source influences buy decisions.
            Higher values give that source more weight.
          </p>
        </div>

        <SourcePrioritySlider
          label="Screener"
          value={screener}
          onChange={setAndDirty(setScreener)}
          percentage={pct(screener, total)}
          icon={<TrendingUp size={14} />}
          description="Top movers &amp; momentum from CoinMarketCap"
        />

        <SourcePrioritySlider
          label="Intelligence"
          value={intelligence}
          onChange={setAndDirty(setIntelligence)}
          percentage={pct(intelligence, total)}
          icon={<Brain size={14} />}
          description="Sentiment, on-chain metrics, market sentiment, social velocity"
        />

        <SourcePrioritySlider
          label="Signals"
          value={signals}
          onChange={setAndDirty(setSignals)}
          percentage={pct(signals, total)}
          icon={<Activity size={14} />}
          description="Technical analysis, derivatives data, CVD"
        />
      </div>

      <div className="mt-4 flex gap-2">
        <Button
          onClick={handleSave}
          disabled={!dirty || updateStrategy.isPending}
        >
          {updateStrategy.isPending ? 'Saving...' : 'Save'}
        </Button>
        {dirty && (
          <Button
            variant="ghost"
            onClick={() => {
              if (strategy) {
                setScreener(strategy.screener_priority ?? 50);
                setIntelligence(strategy.intelligence_priority ?? 50);
                setSignals(strategy.signals_priority ?? 50);
                setStrategyMode(strategy.strategy_mode || 'long_only');
                setShortMinChange(strategy.short_min_1h_change_pct ?? 2.0);
                setRiskAppetite(strategy.risk_appetite ?? 5);
                setMinHold(strategy.min_hold_minutes ?? 15);
                setDirty(false);
              }
            }}
          >
            Reset
          </Button>
        )}
      </div>
    </Card>
  );
}
