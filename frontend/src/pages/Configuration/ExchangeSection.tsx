import {
  useExchanges,
  useAvailableExchanges,
  useAddExchange,
  useUpdateExchange,
  useDeleteExchange,
  useTestExchange,
} from '@/api/hooks/useExchanges';
import { Card, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { TextInput } from '@/components/ui/TextInput';
import { Select } from '@/components/ui/Select';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { useToast } from '@/components/ui/Toast';
import { Plug, Plus, Trash2, Wifi, Pencil, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

export function ExchangeSection() {
  const { data: exchanges = [] } = useExchanges();
  const { data: available = [] } = useAvailableExchanges();
  const addExchange = useAddExchange();
  const updateExchange = useUpdateExchange();
  const deleteExchange = useDeleteExchange();
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
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [passphrase, setPassphrase] = useState('');
  const [testingId, setTestingId] = useState<string | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editApiKey, setEditApiKey] = useState('');
  const [editApiSecret, setEditApiSecret] = useState('');
  const [editPassphrase, setEditPassphrase] = useState('');

  const exchangeOptions = available.map((ex) => ({
    value: ex.name,
    label: `${ex.name.charAt(0).toUpperCase() + ex.name.slice(1)} (${ex.exchange_type})`,
  }));

  function resetForm() {
    setName('');
    setApiKey('');
    setApiSecret('');
    setPassphrase('');
    setShowForm(false);
  }

  function resetEditForm() {
    setEditingId(null);
    setEditApiKey('');
    setEditApiSecret('');
    setEditPassphrase('');
  }

  function handleAdd() {
    if (!name || !apiKey || !apiSecret) return;
    addExchange.mutate(
      { name, api_key: apiKey, api_secret: apiSecret, passphrase: passphrase || undefined },
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
      setEditingId(id);
      setEditApiKey('');
      setEditApiSecret('');
      setEditPassphrase('');
    }
  }

  function handleSaveEdit(id: string, exchangeName: string) {
    const body: Record<string, string> = {};
    if (editApiKey.trim()) body.api_key = editApiKey.trim();
    if (editApiSecret.trim()) body.api_secret = editApiSecret.trim();
    if (editPassphrase.trim()) body.passphrase = editPassphrase.trim();

    if (Object.keys(body).length === 0) return;

    updateExchange.mutate(
      { id, ...body },
      {
        onSuccess: () => {
          toast(`${exchangeName} credentials updated`, 'success');
          resetEditForm();
          // Auto-test after saving
          handleTest(id);
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

  const hasEditValues = editApiKey.trim() || editApiSecret.trim() || editPassphrase.trim();

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
                className="flex items-center justify-between py-3 px-4 rounded-lg bg-ct-bg border border-ct-border"
              >
                <div className="flex items-center gap-3">
                  <StatusDot status={ex.is_active ? 'ok' : 'warning'} />
                  <span className="text-sm font-medium text-ct-text capitalize">{ex.name}</span>
                  <Badge variant="info">{ex.exchange_type}</Badge>
                </div>
                <div className="flex items-center gap-2">
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
                <div className="border border-ct-border border-t-0 rounded-b-lg px-4 py-4 bg-ct-bg space-y-3">
                  <p className="text-sm font-medium text-ct-text-muted">
                    Update {ex.name} Credentials
                  </p>
                  <TextInput
                    label="API Key"
                    type="password"
                    value={editApiKey}
                    onChange={(e) => setEditApiKey(e.target.value)}
                    placeholder="Enter new API key to replace existing"
                  />
                  <TextInput
                    label="API Secret"
                    type="password"
                    value={editApiSecret}
                    onChange={(e) => setEditApiSecret(e.target.value)}
                    placeholder="Enter new API secret to replace existing"
                  />
                  <TextInput
                    label="Passphrase (optional)"
                    type="password"
                    value={editPassphrase}
                    onChange={(e) => setEditPassphrase(e.target.value)}
                    placeholder="Enter new passphrase (leave empty to keep current)"
                  />
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
        <div className="border border-ct-border rounded-lg p-4 bg-ct-bg space-y-3">
          <h4 className="text-sm font-medium text-ct-text mb-2">Add Exchange</h4>

          {exchangeOptions.length > 0 ? (
            <Select
              label="Exchange"
              value={name}
              onChange={setName}
              options={[{ value: '', label: 'Select an exchange...' }, ...exchangeOptions]}
            />
          ) : (
            <p className="text-sm text-ct-text-dim">Loading available exchanges...</p>
          )}

          <TextInput
            label="API Key"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="Enter your API key"
          />
          <TextInput
            label="API Secret"
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            placeholder="Enter your API secret"
          />
          <TextInput
            label="Passphrase (optional)"
            type="password"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            placeholder="Required for some exchanges (e.g., KuCoin)"
          />

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
