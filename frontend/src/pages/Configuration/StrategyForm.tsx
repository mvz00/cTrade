import { useStrategyConfig, useUpdateStrategy } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { NumberInput } from '@/components/ui/NumberInput';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { Sliders } from 'lucide-react';
import { useEffect, useState } from 'react';

export function StrategyForm() {
  const { data: strategy } = useStrategyConfig();
  const updateStrategy = useUpdateStrategy();
  const { toast } = useToast();

  const [tech, setTech] = useState(50);
  const [sent, setSent] = useState(30);
  const [onchain, setOnchain] = useState(20);
  const [entry, setEntry] = useState(70);
  const [exit, setExit] = useState(30);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (strategy) {
      setTech(Math.round(strategy.technical_weight * 100));
      setSent(Math.round(strategy.sentiment_weight * 100));
      setOnchain(Math.round(strategy.onchain_weight * 100));
      setEntry(Math.round(strategy.entry_confidence_threshold * 100));
      setExit(Math.round(strategy.exit_confidence_threshold * 100));
      setDirty(false);
    }
  }, [strategy]);

  const weightSum = tech + sent + onchain;
  const weightError = weightSum !== 100 ? `Weights sum to ${weightSum}%, must be 100%` : '';

  function handleSave() {
    if (weightError) return;
    updateStrategy.mutate(
      {
        technical_weight: tech / 100,
        sentiment_weight: sent / 100,
        onchain_weight: onchain / 100,
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
        <NumberInput
          label="Technical Weight"
          value={tech}
          onChange={setAndDirty(setTech)}
          min={0}
          max={100}
          step={5}
          suffix="%"
          error={weightError && tech > 0 ? '' : undefined}
        />
        <NumberInput
          label="Sentiment Weight"
          value={sent}
          onChange={setAndDirty(setSent)}
          min={0}
          max={100}
          step={5}
          suffix="%"
        />
        <NumberInput
          label="On-Chain Weight"
          value={onchain}
          onChange={setAndDirty(setOnchain)}
          min={0}
          max={100}
          step={5}
          suffix="%"
          error={weightError || undefined}
        />

        <div className="border-t border-ct-border pt-3 mt-3">
          <NumberInput
            label="Entry Confidence"
            value={entry}
            onChange={setAndDirty(setEntry)}
            min={0}
            max={100}
            step={5}
            suffix="%"
          />
        </div>
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
