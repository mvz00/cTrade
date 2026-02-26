import {
  useExchanges,
  useAvailableExchanges,
  useAddExchange,
  useUpdateExchange,
  useDeleteExchange,
  useTestExchange,
  useToggleExchange,
} from '@/api/hooks/useExchanges';
import { Card, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { NumberInput } from '@/components/ui/NumberInput';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { useToast } from '@/components/ui/Toast';
import { InfoTooltip } from '@/components/ui/InfoTooltip';
import { Plug, Plus, Trash2, Wifi, Pencil, X, ChevronDown, ChevronRight, Power } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { RiskConfig } from '@/api/types';

const QUOTE_CURRENCY_OPTIONS = ['USDT', 'USDC', 'BTC', 'AUD', 'USD', 'EUR'];

function QuoteCurrencyPicker({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (currencies: string[]) => void;
}) {
  function toggle(currency: string) {
    if (selected.includes(currency)) {
      // Don't allow deselecting the last one
      if (selected.length > 1) {
        onChange(selected.filter((c) => c !== currency));
      }
    } else {
      onChange([...selected, currency]);
    }
  }

  return (
    <div className="space-y-1.5">
      <label className="block text-sm font-medium text-ct-text-muted">
        Quote Currencies<InfoTooltip text="Only trading pairs quoted in these currencies will be considered (e.g. BTC/USDT)." />
      </label>
      <div className="flex flex-wrap gap-2">
        {QUOTE_CURRENCY_OPTIONS.map((cur) => (
          <button
            key={cur}
            type="button"
            onClick={() => toggle(cur)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              selected.includes(cur)
                ? 'bg-ct-accent/15 border-ct-accent text-ct-accent'
                : 'bg-ct-bg border-ct-border text-ct-text-dim hover:text-ct-text-muted hover:border-ct-text-dim'
            }`}
          >
            {cur}
          </button>
        ))}
      </div>
      <p className="text-xs text-ct-text-dim">
        Trading pairs will be filtered to these quote currencies
      </p>
    </div>
  );
}

function RiskOverrideFields({
  overrides,
  onChange,
}: {
  overrides: Partial<RiskConfig>;
  onChange: (overrides: Partial<RiskConfig>) => void;
}) {
  const [expanded, setExpanded] = useState(Object.keys(overrides).length > 0);

  const fields: { key: keyof RiskConfig; label: string; min: number; max: number }[] = [
    { key: 'default_stop_loss_pct', label: 'Stop Loss', min: 1, max: 50 },
    { key: 'default_take_profit_pct', label: 'Take Profit', min: 1, max: 100 },
    { key: 'max_position_pct', label: 'Max Position Size', min: 1, max: 100 },
  ];

  function toggleField(key: keyof RiskConfig) {
    const next = { ...overrides };
    if (key in next) {
      delete next[key];
    } else {
      // Set sensible defaults when enabling
      const defaults: Record<string, number> = {
        default_stop_loss_pct: 3,
        default_take_profit_pct: 6,
        max_position_pct: 10,
      };
      next[key] = (defaults[key] ?? 5) / 100;
    }
    onChange(next);
  }

  function setFieldValue(key: keyof RiskConfig, pctValue: number) {
    onChange({ ...overrides, [key]: pctValue / 100 });
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-sm font-medium text-ct-text-muted hover:text-ct-text transition-colors"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Risk Overrides
        {Object.keys(overrides).length > 0 && (
          <Badge variant="info">{Object.keys(overrides).length}</Badge>
        )}
      </button>
      {expanded && (
        <div className="pl-1 space-y-2">
          <p className="text-xs text-ct-text-dim">
            Override global risk defaults for this exchange only
          </p>
          {fields.map(({ key, label, min, max }) => {
            const enabled = key in overrides;
            return (
              <div key={key} className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => toggleField(key)}
                  className={`flex-shrink-0 w-4 h-4 rounded border transition-colors ${
                    enabled
                      ? 'bg-ct-accent border-ct-accent'
                      : 'border-ct-border hover:border-ct-text-dim'
                  }`}
                >
                  {enabled && (
                    <svg viewBox="0 0 16 16" className="w-4 h-4 text-white">
                      <path
                        d="M4 8l3 3 5-5"
                        stroke="currentColor"
                        strokeWidth="2"
                        fill="none"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  )}
                </button>
                <div className="flex-1">
                  {enabled ? (
                    <NumberInput
                      label={label}
                      value={Math.round((overrides[key] ?? 0) * 100)}
                      onChange={(v) => setFieldValue(key, v)}
                      min={min}
                      max={max}
                      step={1}
                      suffix="%"
                    />
                  ) : (
                    <span className="text-sm text-ct-text-dim">{label} — using global default</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ExchangeSection() {
  const { data: exchanges = [] } = useExchanges();
  const { data: available = [] } = useAvailableExchanges();
  const addExchange = useAddExchange();
  const updateExchange = useUpdateExchange();
  const deleteExchange = useDeleteExchange();
  const toggleExchange = useToggleExchange();
  const testExchange = useTestExchange();
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();

  const [showForm, setShowForm] = useState(false);

  // Auto-open "Add Exchange" form when navigated from Connections page
  useEffect(() => {
    if (searchParams.get('addExchange') === 'true') {
      setShowForm(true);
      searchParams.delete('addExchange');
      setSearchParams(searchParams, { replace: true });
    }
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // Add form state
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [quoteCurrencies, setQuoteCurrencies] = useState<string[]>(['USDT']);
  const [maxPortfolioPct, setMaxPortfolioPct] = useState(100);
  const [riskOverrides, setRiskOverrides] = useState<Partial<RiskConfig>>({});
  const [testingId, setTestingId] = useState<string | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editApiKey, setEditApiKey] = useState('');
  const [editApiSecret, setEditApiSecret] = useState('');
  const [editPassphrase, setEditPassphrase] = useState('');
  const [editQuoteCurrencies, setEditQuoteCurrencies] = useState<string[]>(['USDT']);
  const [editMaxPortfolioPct, setEditMaxPortfolioPct] = useState(100);
  const [editRiskOverrides, setEditRiskOverrides] = useState<Partial<RiskConfig>>({});

  const exchangeOptions = available.map((ex) => ({
    value: ex.name,
    label: `${ex.name.charAt(0).toUpperCase() + ex.name.slice(1)} (${ex.exchange_type})`,
  }));

  function resetForm() {
    setName('');
    setApiKey('');
    setApiSecret('');
    setPassphrase('');
    setQuoteCurrencies(['USDT']);
    setMaxPortfolioPct(100);
    setRiskOverrides({});
    setShowForm(false);
  }

  function resetEditForm() {
    setEditingId(null);
    setEditApiKey('');
    setEditApiSecret('');
    setEditPassphrase('');
    setEditQuoteCurrencies(['USDT']);
    setEditMaxPortfolioPct(100);
    setEditRiskOverrides({});
  }

  function handleAdd() {
    if (!name || !apiKey || !apiSecret) return;
    addExchange.mutate(
      {
        name,
        api_key: apiKey,
        api_secret: apiSecret,
        passphrase: passphrase || undefined,
        quote_currencies: quoteCurrencies,
        max_portfolio_pct: maxPortfolioPct / 100,
        risk_overrides: Object.keys(riskOverrides).length > 0 ? riskOverrides : undefined,
      },
      {
        onSuccess: () => {
          toast(`${name} added successfully`, 'success');
          resetForm();
        },
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  function handleEdit(id: string) {
    if (editingId === id) {
      resetEditForm();
    } else {
      const ex = exchanges.find((e) => e.id === id);
      setEditingId(id);
      setEditApiKey('');
      setEditApiSecret('');
      setEditPassphrase('');
      setEditQuoteCurrencies(ex?.quote_currencies ?? ['USDT']);
      setEditMaxPortfolioPct(Math.round((ex?.max_portfolio_pct ?? 1) * 100));
      setEditRiskOverrides(ex?.risk_overrides ?? {});
    }
  }

  function handleSaveEdit(id: string, exchangeName: string) {
    const body: Record<string, any> = {};
    if (editApiKey.trim()) body.api_key = editApiKey.trim();
    if (editApiSecret.trim()) body.api_secret = editApiSecret.trim();
    if (editPassphrase.trim()) body.passphrase = editPassphrase.trim();

    // Always send settings fields so they can be updated independently of credentials
    const ex = exchanges.find((e) => e.id === id);
    const origQuote = ex?.quote_currencies ?? ['USDT'];
    const origMaxPct = Math.round((ex?.max_portfolio_pct ?? 1) * 100);
    const origOverrides = ex?.risk_overrides ?? {};

    const quotesChanged = JSON.stringify(editQuoteCurrencies.sort()) !== JSON.stringify([...origQuote].sort());
    const maxPctChanged = editMaxPortfolioPct !== origMaxPct;
    const overridesChanged = JSON.stringify(editRiskOverrides) !== JSON.stringify(origOverrides);

    if (quotesChanged) body.quote_currencies = editQuoteCurrencies;
    if (maxPctChanged) body.max_portfolio_pct = editMaxPortfolioPct / 100;
    if (overridesChanged) {
      body.risk_overrides = Object.keys(editRiskOverrides).length > 0 ? editRiskOverrides : {};
    }

    if (Object.keys(body).length === 0) {
      toast('No changes to save', 'info');
      return;
    }

    updateExchange.mutate(
      { id, ...body },
      {
        onSuccess: () => {
          toast(`${exchangeName} updated`, 'success');
          resetEditForm();
          // Auto-test after saving credentials
          if (body.api_key || body.api_secret) {
            handleTest(id);
          }
        },
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  function handleDelete(id: string, exchangeName: string) {
    deleteExchange.mutate(id, {
      onSuccess: () => toast(`${exchangeName} removed`, 'success'),
      onError: (err) => toast(err.message, 'error'),
    });
  }

  function handleTest(id: string) {
    setTestingId(id);
    testExchange.mutate(id, {
      onSuccess: (result) => {
        if (result.success) {
          toast(result.message, 'success');
        } else {
          toast(result.message, 'error');
        }
        setTestingId(null);
      },
      onError: (err) => {
        toast(err.message, 'error');
        setTestingId(null);
      },
    });
  }

  function handleToggle(id: string, exchangeName: string, currentlyActive: boolean) {
    toggleExchange.mutate(id, {
      onSuccess: () => {
        toast(`${exchangeName} ${currentlyActive ? 'disabled' : 'enabled'}`, 'success');
      },
      onError: (err) => toast(err.message, 'error'),
    });
  }

  const hasEditValues =
    editApiKey.trim() ||
    editApiSecret.trim() ||
    editPassphrase.trim() ||
    (() => {
      const ex = exchanges.find((e) => e.id === editingId);
      if (!ex) return false;
      const quotesChanged = JSON.stringify(editQuoteCurrencies.sort()) !== JSON.stringify([...(ex.quote_currencies ?? ['USDT'])].sort());
      const maxPctChanged = editMaxPortfolioPct !== Math.round((ex.max_portfolio_pct ?? 1) * 100);
      const overridesChanged = JSON.stringify(editRiskOverrides) !== JSON.stringify(ex.risk_overrides ?? {});
      return quotesChanged || maxPctChanged || overridesChanged;
    })();

  return (
    <Card className="lg:col-span-2">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-ct-blue/10">
            <Plug size={18} className="text-ct-blue" />
          </div>
          <CardTitle className="mb-0">Exchange Connections</CardTitle>
        </div>
        {!showForm && (
          <Button variant="secondary" onClick={() => setShowForm(true)}>
            <Plus size={14} /> Add Exchange
          </Button>
        )}
      </div>

      {/* Exchange list */}
      {exchanges.length > 0 && (
        <div className="space-y-2 mb-4">
          {exchanges.map((ex) => (
            <div key={ex.id}>
              <div
                className={`flex items-center justify-between py-3 px-4 rounded-lg bg-ct-bg border border-ct-border transition-opacity ${
                  !ex.is_active ? 'opacity-50' : ''
                }`}
              >
                <div className="flex items-center gap-3 flex-wrap">
                  <StatusDot status={ex.is_active ? 'ok' : 'warning'} label={ex.is_active ? undefined : 'Disabled'} />
                  <span className="text-sm font-medium text-ct-text capitalize">{ex.name}</span>
                  <Badge variant="info">{ex.exchange_type}</Badge>
                  {/* Quote currency badges */}
                  {(ex.quote_currencies ?? []).map((cur) => (
                    <Badge key={cur} variant="default">{cur}</Badge>
                  ))}
                  {/* Portfolio cap indicator */}
                  {ex.max_portfolio_pct < 1 && (
                    <span className="text-xs text-ct-text-dim">
                      Max: {Math.round(ex.max_portfolio_pct * 100)}%
                    </span>
                  )}
                  {/* Risk override indicator */}
                  {Object.keys(ex.risk_overrides ?? {}).length > 0 && (
                    <Badge variant="warning">Custom Risk</Badge>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleToggle(ex.id, ex.name, ex.is_active)}
                    disabled={toggleExchange.isPending}
                    className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      ex.is_active ? 'bg-ct-green' : 'bg-ct-bg-hover'
                    }`}
                    title={ex.is_active ? 'Disable exchange' : 'Enable exchange'}
                  >
                    <span
                      className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        ex.is_active ? 'translate-x-4' : 'translate-x-0'
                      }`}
                    />
                  </button>
                  <Button
                    variant="ghost"
                    onClick={() => handleEdit(ex.id)}
                  >
                    {editingId === ex.id ? <X size={14} /> : <Pencil size={14} />}
                    {editingId === ex.id ? 'Cancel' : 'Edit'}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => handleTest(ex.id)}
                    disabled={testingId === ex.id}
                  >
                    <Wifi size={14} />
                    {testingId === ex.id ? 'Testing...' : 'Test'}
                  </Button>
                  <Button
                    variant="ghost"
                    onClick={() => handleDelete(ex.id, ex.name)}
                    disabled={deleteExchange.isPending}
                  >
                    <Trash2 size={14} className="text-ct-red" />
                  </Button>
                </div>
              </div>

              {/* Inline edit form */}
              {editingId === ex.id && (
                <div className="border border-ct-border border-t-0 rounded-b-lg px-4 py-4 bg-ct-bg space-y-4">
                  <p className="text-sm font-medium text-ct-text-muted">
                    Update {ex.name} Settings
                  </p>

                  {/* Credentials section */}
                  <div className="space-y-3">
                    <p className="text-xs font-medium text-ct-text-dim uppercase tracking-wide">Credentials</p>
                    <TextInput
                      label="API Key"
                      type="password"
                      value={editApiKey}
                      onChange={(e) => setEditApiKey(e.target.value)}
                      placeholder="Enter new API key to replace existing"
                      tooltip="Your exchange API key. Create one in your exchange account settings with trading permissions enabled."
                    />
                    <TextInput
                      label="API Secret"
                      type="password"
                      value={editApiSecret}
                      onChange={(e) => setEditApiSecret(e.target.value)}
                      placeholder="Enter new API secret to replace existing"
                      tooltip="Your exchange API secret. This is shown only once when creating the key — store it securely."
                    />
                    <TextInput
                      label="Passphrase (optional)"
                      type="password"
                      value={editPassphrase}
                      onChange={(e) => setEditPassphrase(e.target.value)}
                      placeholder="Enter new passphrase (leave empty to keep current)"
                      tooltip="Some exchanges like KuCoin require a passphrase in addition to API key and secret."
                    />
                  </div>

                  {/* Trading settings section */}
                  <div className="border-t border-ct-border pt-4 space-y-3">
                    <p className="text-xs font-medium text-ct-text-dim uppercase tracking-wide">Trading Settings</p>
                    <QuoteCurrencyPicker
                      selected={editQuoteCurrencies}
                      onChange={setEditQuoteCurrencies}
                    />
                    <NumberInput
                      label="Max Portfolio Allocation"
                      value={editMaxPortfolioPct}
                      onChange={setEditMaxPortfolioPct}
                      min={1}
                      max={100}
                      step={5}
                      suffix="%"
                      tooltip="Maximum percentage of your total portfolio that can be used on this exchange."
                    />
                    <RiskOverrideFields
                      overrides={editRiskOverrides}
                      onChange={setEditRiskOverrides}
                    />
                  </div>

                  <div className="flex gap-2 pt-1">
                    <Button
                      onClick={() => handleSaveEdit(ex.id, ex.name)}
                      disabled={updateExchange.isPending || !hasEditValues}
                    >
                      {updateExchange.isPending ? 'Saving...' : 'Save'}
                    </Button>
                    <Button variant="ghost" onClick={resetEditForm}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {exchanges.length === 0 && !showForm && (
        <p className="text-sm text-ct-text-dim py-6 text-center">
          No exchanges configured. Click "Add Exchange" to connect one.
        </p>
      )}

      {/* Add exchange form */}
      {showForm && (
        <div className="border border-ct-border rounded-lg p-4 bg-ct-bg space-y-4">
          <h4 className="text-sm font-medium text-ct-text mb-2">Add Exchange</h4>

          {exchangeOptions.length > 0 ? (
            <Select
              label="Exchange"
              value={name}
              onChange={setName}
              options={[{ value: '', label: 'Select an exchange...' }, ...exchangeOptions]}
              tooltip="The exchange platform to connect. Each exchange must be added separately with its own API credentials."
            />
          ) : (
            <p className="text-sm text-ct-text-dim">Loading available exchanges...</p>
          )}

          <TextInput
            label="API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Enter your API key"
            tooltip="Your exchange API key. Create one in your exchange account settings with trading permissions enabled."
          />
          <TextInput
            label="API Secret"
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder="Enter your API secret"
            tooltip="Your exchange API secret. This is shown only once when creating the key — store it securely."
          />
          <TextInput
            label="Passphrase (optional)"
            type="password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="Required for some exchanges (e.g., KuCoin)"
            tooltip="Some exchanges like KuCoin require a passphrase in addition to API key and secret."
          />

          {/* Trading settings */}
          <div className="border-t border-ct-border pt-4 space-y-3">
            <p className="text-xs font-medium text-ct-text-dim uppercase tracking-wide">Trading Settings</p>
            <QuoteCurrencyPicker
              selected={quoteCurrencies}
              onChange={setQuoteCurrencies}
            />
            <NumberInput
              label="Max Portfolio Allocation"
              value={maxPortfolioPct}
              onChange={setMaxPortfolioPct}
              min={1}
              max={100}
              step={5}
              suffix="%"
              tooltip="Maximum percentage of your total portfolio that can be used on this exchange."
            />
            <RiskOverrideFields
              overrides={riskOverrides}
              onChange={setRiskOverrides}
            />
          </div>

          <div className="flex gap-2 pt-2">
            <Button
              onClick={handleAdd}
              disabled={!name || !apiKey || !apiSecret || addExchange.isPending}
            >
              {addExchange.isPending ? 'Adding...' : 'Save Exchange'}
            </Button>
            <Button variant="ghost" onClick={resetForm}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
