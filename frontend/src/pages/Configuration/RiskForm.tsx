import { useRiskConfig, useUpdateRisk } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { NumberInput } from '@/components/ui/NumberInput';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/Toast';
import { Shield } from 'lucide-react';
import { useEffect, useState } from 'react';

export function RiskForm() {
  const { data: risk } = useRiskConfig();
  const updateRisk = useUpdateRisk();
  const { toast } = useToast();

  const [maxPos, setMaxPos] = useState(10);
  const [maxDaily, setMaxDaily] = useState(5);
  const [maxDd, setMaxDd] = useState(15);
  const [sl, setSl] = useState(3);
  const [tp, setTp] = useState(6);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (risk) {
      setMaxPos(Math.round(risk.max_position_pct * 100));
      setMaxDaily(Math.round(risk.max_daily_loss_pct * 100));
      setMaxDd(Math.round(risk.max_drawdown_pct * 100));
      setSl(Math.round(risk.default_stop_loss_pct * 100));
      setTp(Math.round(risk.default_take_profit_pct * 100));
      setDirty(false);
    }
  }, [risk]);

  function handleSave() {
    updateRisk.mutate(
      {
        max_position_pct: maxPos / 100,
        max_daily_loss_pct: maxDaily / 100,
        max_drawdown_pct: maxDd / 100,
        default_stop_loss_pct: sl / 100,
        default_take_profit_pct: tp / 100,
      },
      {
        onSuccess: () => {
          toast('Risk config saved', 'success');
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
        <div className="p-2 rounded-lg bg-ct-red/10">
          <Shield size={18} className="text-ct-red" />
        </div>
        <CardTitle className="mb-0">Risk Management</CardTitle>
      </div>

      <div className="space-y-3">
        <NumberInput
          label="Max Position Size"
          value={maxPos}
          onChange={setAndDirty(setMaxPos)}
          min={1}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="Max Daily Loss"
          value={maxDaily}
          onChange={setAndDirty(setMaxDaily)}
          min={1}
          max={100}
          step={1}
          suffix="%"
        />
        <NumberInput
          label="Max Drawdown"
          value={maxDd}
          onChange={setAndDirty(setMaxDd)}
          min={1}
          max={100}
          step={1}
          suffix="%"
        />
        <div className="border-t border-ct-border pt-3 mt-3">
          <NumberInput
            label="Default Stop Loss"
            value={sl}
            onChange={setAndDirty(setSl)}
            min={1}
            max={50}
            step={1}
            suffix="%"
          />
        </div>
        <NumberInput
          label="Default Take Profit"
          value={tp}
          onChange={setAndDirty(setTp)}
          min={1}
          max={100}
          step={1}
          suffix="%"
        />
      </div>

      <div className="mt-4 flex gap-2">
        <Button
          onClick={handleSave}
          disabled={!dirty || updateRisk.isPending}
        >
          {updateRisk.isPending ? 'Saving...' : 'Save'}
        </Button>
        {dirty && (
          <Button
            variant="ghost"
            onClick={() => {
              if (risk) {
                setMaxPos(Math.round(risk.max_position_pct * 100));
                setMaxDaily(Math.round(risk.max_daily_loss_pct * 100));
                setMaxDd(Math.round(risk.max_drawdown_pct * 100));
                setSl(Math.round(risk.default_stop_loss_pct * 100));
                setTp(Math.round(risk.default_take_profit_pct * 100));
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
