import { useConnections, useTestConnection, useUpdateConnectionCredentials } from '@/api/hooks/useConnections';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Badge } from '@/components/ui/Badge';
import { StatusDot } from '@/components/ui/StatusDot';
import { PageHeader } from '@/components/ui/PageHeader';
import { Spinner } from '@/components/ui/Spinner';
import { TextInput } from '@/components/ui/TextInput';
import { useToast } from '@/components/ui/Toast';
import { Cable, Wifi, ExternalLink, Pencil, X } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ROUTES } from '@/lib/constants';
import type { ConnectionInfo } from '@/api/types';

function statusToDot(status: ConnectionInfo['status']): 'ok' | 'warning' | 'error' | 'loading' {
  switch (status) {
    case 'ok': return 'ok';
    case 'error': return 'error';
    case 'disabled': return 'warning';
    case 'untested':
    default: return 'loading';
  }
}

function statusLabel(status: ConnectionInfo['status']): string {
  switch (status) {
    case 'ok': return 'Connected';
    case 'error': return 'Error';
    case 'disabled': return 'Disabled';
    case 'untested':
    default: return 'Untested';
  }
}

function formatTime(iso: string | null): string {
  if (!iso) return 'Never';
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  return `${diffHr}h ago`;
}

export function ConnectionsPage() {
  const { data: connections, isLoading } = useConnections();
  const testConnection = useTestConnection();
  const updateCredentials = useUpdateConnectionCredentials();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [testingName, setTestingName] = useState<string | null>(null);
  const [testingAll, setTestingAll] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({});

  function handleTest(name: string) {
    setTestingName(name);
    testConnection.mutate(name, {
      onSuccess: (result) => {
        if (result.success) {
          toast(`${name}: ${result.message}`, 'success');
        } else {
          toast(`${name}: ${result.message}`, 'error');
        }
        setTestingName(null);
      },
      onError: (err) => {
        toast(`${name}: ${err.message}`, 'error');
        setTestingName(null);
      },
    });
  }

  async function handleTestAll() {
    if (!connections) return;
    setTestingAll(true);
    const enabled = connections.filter((c) => c.status !== 'disabled');
    for (const conn of enabled) {
      setTestingName(conn.name);
      try {
        const result = await testConnection.mutateAsync(conn.name);
        if (!result.success) {
          toast(`${conn.name}: ${result.message}`, 'error');
        }
      } catch {
        // ignore — individual errors shown via toast
      }
    }
    setTestingName(null);
    setTestingAll(false);
    toast('All connection tests complete', 'success');
  }

  function handleEditToggle(conn: ConnectionInfo) {
    if (editingName === conn.name) {
      // Cancel editing
      setEditingName(null);
      setCredentialValues({});
    } else {
      // Start editing — initialize empty values for each field
      setEditingName(conn.name);
      const init: Record<string, string> = {};
      conn.credential_fields.forEach((f) => { init[f.key] = ''; });
      setCredentialValues(init);
    }
  }

  function handleSaveCredentials(name: string) {
    // Filter out empty values (empty means "keep current")
    const nonEmpty = Object.fromEntries(
      Object.entries(credentialValues).filter(([, v]) => v.trim())
    );
    if (Object.keys(nonEmpty).length === 0) return;

    updateCredentials.mutate(
      { name, credentials: nonEmpty },
      {
        onSuccess: () => {
          toast(`${name} credentials saved`, 'success');
          setEditingName(null);
          setCredentialValues({});
          // Auto-test after saving credentials
          handleTest(name);
        },
        onError: (err) => toast(err.message, 'error'),
      }
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="External Connections"
        description="Monitor, test, and configure all external API connections used by data feeds."
        actions={
          <Button
            variant="secondary"
            onClick={handleTestAll}
            disabled={testingAll || !connections?.length}
          >
            <Wifi size={14} />
            {testingAll ? 'Testing...' : 'Test All'}
          </Button>
        }
      />

      <div className="space-y-3">
        {connections?.map((conn) => {
          const isEditing = editingName === conn.name;
          const hasCredentialFields = conn.credential_fields.length > 0;
          const isExchange = conn.name === 'Exchange (ccxt)' || conn.name.startsWith('Exchange: ');
          const showEditButton = conn.requires_key && hasCredentialFields && !isExchange;
          const showManageButton = isExchange;
          const hasNonEmptyValues = Object.values(credentialValues).some((v) => v.trim());

          return (
            <Card key={conn.name} className="!p-0">
              <div className="flex items-center justify-between px-5 py-4">
                {/* Left side: status + info */}
                <div className="flex items-center gap-4 min-w-0">
                  <div className="p-2 rounded-lg bg-ct-blue/10 flex-shrink-0">
                    <Cable size={18} className="text-ct-blue" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <StatusDot status={statusToDot(conn.status)} />
                      <span className="text-sm font-semibold text-ct-text">{conn.name}</span>
                      <Badge
                        variant={
                          conn.status === 'ok' ? 'success'
                            : conn.status === 'error' ? 'danger'
                              : conn.status === 'disabled' ? 'warning'
                                : 'default'
                        }
                      >
                        {statusLabel(conn.status)}
                      </Badge>
                      {conn.requires_key && (
                        <Badge variant={conn.key_configured ? 'success' : 'danger'}>
                          {conn.key_configured ? 'Key Set' : 'Key Missing'}
                        </Badge>
                      )}
                      {!conn.requires_key && (
                        <Badge variant="info">No Key Needed</Badge>
                      )}
                    </div>
                    <p className="text-xs text-ct-text-dim mt-1">{conn.description}</p>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      {conn.base_urls.length > 0 && (
                        <span className="text-[11px] text-ct-text-dim flex items-center gap-1">
                          <ExternalLink size={10} />
                          {conn.base_urls[0]}
                        </span>
                      )}
                      <span className="text-[11px] text-ct-text-dim">
                        Feed: <span className="text-ct-text-muted">{conn.feed_name}</span>
                      </span>
                      <span className="text-[11px] text-ct-text-dim">
                        Last checked: <span className="text-ct-text-muted">{formatTime(conn.last_checked)}</span>
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right side: action buttons */}
                <div className="flex-shrink-0 ml-4 flex items-center gap-2">
                  {showManageButton && (
                    <Button
                      variant="ghost"
                      onClick={() => navigate(`${ROUTES.CONFIGURATION}?addExchange=true`)}
                    >
                      <ExternalLink size={14} />
                      Manage
                    </Button>
                  )}
                  {showEditButton && (
                    <Button
                      variant="ghost"
                      onClick={() => handleEditToggle(conn)}
                    >
                      {isEditing ? <X size={14} /> : <Pencil size={14} />}
                      {isEditing ? 'Cancel' : 'Edit'}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    onClick={() => handleTest(conn.name)}
                    disabled={testingName === conn.name || conn.status === 'disabled'}
                  >
                    <Wifi size={14} />
                    {testingName === conn.name ? 'Testing...' : 'Test'}
                  </Button>
                </div>
              </div>

              {/* Inline credential edit form */}
              {isEditing && (
                <div className="border-t border-ct-border px-5 py-4 bg-ct-bg space-y-3">
                  <p className="text-sm font-medium text-ct-text-muted">
                    Configure {conn.name} Credentials
                  </p>
                  {conn.credential_fields.map((field) => (
                    <TextInput
                      key={field.key}
                      label={field.label}
                      type={field.is_secret ? 'password' : 'text'}
                      value={credentialValues[field.key] || ''}
                      onChange={(e) =>
                        setCredentialValues((prev) => ({
                          ...prev,
                          [field.key]: e.target.value,
                        }))
                      }
                      placeholder={
                        conn.key_configured
                          ? 'Enter new value to replace existing key'
                          : `Enter ${field.label}`
                      }
                    />
                  ))}
                  <div className="flex gap-2 pt-1">
                    <Button
                      onClick={() => handleSaveCredentials(conn.name)}
                      disabled={updateCredentials.isPending || !hasNonEmptyValues}
                    >
                      {updateCredentials.isPending ? 'Saving...' : 'Save'}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setEditingName(null);
                        setCredentialValues({});
                      }}
                    >
                      Cancel
                    </Button>
                  </div>
                </div>
              )}
            </Card>
          );
        })}

        {(!connections || connections.length === 0) && (
          <Card>
            <p className="text-sm text-ct-text-dim text-center py-8">
              No external connections configured.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
