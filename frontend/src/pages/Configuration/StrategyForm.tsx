import { useStrategyConfig, useUpdateStrategy } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { NumberInput } from '@/components/ui/NumberInput';
import { Select } from '@/components/ui/Select';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { Sliders } from 'lucide-react';
import { useEffect, useState } from 'react';

export function StrategyForm() {
  const { data: strategy } = useStrategyConfig();
  const updateStrategy = useUpdateStrategy();
  const { toast } = useToast();

  const [tech, setTech] = useState(30);
  const [sent, setSent] = useState(10);
  const [onchain, setOnchain] = useState(8);
  const [deriv, setDeriv] = useState(17);
  const [mktSent, setMktSent] = useState(17);
  const [cvd, setCvd] = useState(10);
  const [social, setSocial] = useState(8);
  const [strategyMode, setStrategyMode] = useState('long_only');
  const [shortMinChange, setShortMinChange] = useState(2.0);
  const [entry, setEntry] = useState(55);
  const [exit, setExit] = useState(45);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (strategy) {
      setTech(Math.round(strategy.technical_weight * 100));
      setSent(Math.round(strategy.sentiment_weight * 100));
      setOnchain(Math.round(strategy.onchain_weight * 100));
      setDeriv(Math.round(strategy.derivatives_weight * 100));
      setMktSent(Math.round(strategy.market_sentiment_weight * 100));
      setCvd(Math.round(strategy.cvd_weight * 100));
      setSocial(Math.round(strategy.social_velocity_weight * 100));
      setStrategyMode(strategy.strategy_mode || 'long_only');
      setShortMinChange(strategy.short_min_1h_change_pct ?? 2.0);
      setEntry(Math.round(strategy.entry_confidence_threshold * 100));
      setExit(Math.round(strategy.exit_confidence_threshold * 100));
      setDirty(false);
    }
  }, [strategy]);

  const weightSum = tech + sent + onchain + deriv + mktSent + cvd + social;
  const weightError = weightSum !== 100 ? `Weights sum to ${weightSum}%, must be 100%` : '';

  function handleSave() {
    if (weightError) return;
    updateStrategy.mutate(
      {
        technical_weight: tech / 100,
        sentiment_weight: sent / 100,
        onchain_weight: onchain / 100,
        derivatives_weight: deriv / 100,
        market_sentiment_weight: mktSent / 100,
        cvd_weight: cvd / 100,
        social_velocity_weight: social / 100,
        strategy_mode: strategyMode,
        short_min_1h_change_pct: shortMinChange,
        entry_confidence_threshold: entry / 100,
        exit_confidence_threshold: exit / 100,
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

        <div className="border-t border-ct-border pt-3 mt-3">
          <p className="text-xs font-medium text-ct-text-dim mb-2">Signal Weights</p>
        </div>

        <NumberInput
          label="Technical Weight"
          value={tech}
          onChange={setAndDirty(setTech)}
          min={0}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="Sentiment Weight"
          value={sent}
          onChange={setAndDirty(setSent)}
          min={0}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="On-Chain Weight"
          value={onchain}
          onChange={setAndDirty(setOnchain)}
          min={0}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="Derivatives Weight"
          value={deriv}
          onChange={setAndDirty(setDeriv)}
          min={0}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="Market Sentiment Weight"
          value={mktSent}
          onChange={setAndDirty(setMktSent)}
          min={0}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="CVD Weight"
          value={cvd}
          onChange={setAndDirty(setCvd)}
          min={0}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="Social Velocity Weight"
          value={social}
          onChange={setAndDirty(setSocial)}
          min={0}
          max={100}
          step={1}
          suffix="%"
          error={weightError || undefined}
        />

        <div className="border-t border-ct-border pt-3 mt-3">
          <p className="text-xs font-medium text-ct-text-dim mb-2">Confidence Thresholds</p>
        </div>

        <NumberInput
          label="Entry Confidence"
          value={entry}
          onChange={setAndDirty(setEntry)}
          min={0}
          max={100}
          step={5}
          suffix="%"
        />
        <NumberInput
          label="Exit Confidence"
          value={exit}
          onChange={setAndDirty(setExit)}
          min={0}
          max={100}
          step={5}
          suffix="%"
        />
      </div>

      <div className="mt-4 flex gap-2">
        <Button
          onClick={handleSave}
          disabled={!!weightError || !dirty || updateStrategy.isPending}
        >
          {updateStrategy.isPending ? 'Saving...' : 'Save'}
        </Button>
        {dirty && (
          <Button
            variant="ghost"
            onClick={() => {
              if (strategy) {
                setTech(Math.round(strategy.technical_weight * 100));
                setSent(Math.round(strategy.sentiment_weight * 100));
                setOnchain(Math.round(strategy.onchain_weight * 100));
                setDeriv(Math.round(strategy.derivatives_weight * 100));
                setMktSent(Math.round(strategy.market_sentiment_weight * 100));
                setCvd(Math.round(strategy.cvd_weight * 100));
                setSocial(Math.round(strategy.social_velocity_weight * 100));
                setStrategyMode(strategy.strategy_mode || 'long_only');
                setShortMinChange(strategy.short_min_1h_change_pct ?? 2.0);
                setEntry(Math.round(strategy.entry_confidence_threshold * 100));
                setExit(Math.round(strategy.exit_confidence_threshold * 100));
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
