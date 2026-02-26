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
  const [slDelay, setSlDelay] = useState(1);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (risk) {
      setMaxPos(Math.round(risk.max_position_pct * 100));
      setMaxDaily(Math.round(risk.max_daily_loss_pct * 100));
      setMaxDd(Math.round(risk.max_drawdown_pct * 100));
      setSl(Math.round(risk.default_stop_loss_pct * 100));
      setTp(Math.round(risk.default_take_profit_pct * 100));
      setSlDelay(risk.sl_rebuy_delay_hours ?? 1);
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
        sl_rebuy_delay_hours: slDelay,
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
      <div className="flex items-center gap-3 mb-1">
        <div className="p-2 rounded-lg bg-ct-red/10">
          <Shield size={18} className="text-ct-red" />
        </div>
        <CardTitle className="mb-0">Risk Management</CardTitle>
      </div>
      <p className="text-xs text-ct-text-dim mb-4 ml-12">
        Global defaults — can be overridden per exchange
      </p>

      <div className="space-y-3">
        <NumberInput
          label="Max Position Size"
          value={maxPos}
          onChange={setAndDirty(setMaxPos)}
          min={1}
          max={100}
          step={1}
          suffix="%"
          tooltip="Maximum percentage of your portfolio that can be allocated to a single trade."
        />
        <NumberInput
          label="Max Daily Loss"
          value={maxDaily}
          onChange={setAndDirty(setMaxDaily)}
          min={1}
          max={100}
          step={1}
          suffix="%"
          tooltip="Trading pauses for the day if total losses exceed this percentage of your portfolio."
        />
        <NumberInput
          label="Max Drawdown"
          value={maxDd}
          onChange={setAndDirty(setMaxDd)}
          min={1}
          max={100}
          step={1}
          suffix="%"
          tooltip="Trading halts completely if your portfolio drops this much from its peak value."
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
            tooltip="Automatically sell a position if it drops this percentage below your entry price."
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
          tooltip="Automatically sell a position once it gains this percentage above your entry price."
        />
        <NumberInput
          label="Re-buy Delay After SL"
          value={slDelay}
          onChange={(v) => { setSlDelay(v); setDirty(true); }}
          min={0}
          max={72}
          step={0.5}
          suffix=" hrs"
          tooltip="Wait this long after a stop loss is triggered before buying the same asset again."
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
                setSlDelay(risk.sl_rebuy_delay_hours ?? 1);
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
