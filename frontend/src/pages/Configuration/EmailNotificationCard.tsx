import { useEmailConfig, useUpdateEmailConfig } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { TextInput } from '@/components/ui/TextInput';
import { NumberInput } from '@/components/ui/NumberInput';
import { Toggle } from '@/components/ui/Toggle';
import { useToast } from '@/components/ui/Toast';
import { Mail } from 'lucide-react';
import { useEffect, useState } from 'react';

export function EmailNotificationCard() {
  const { data: config } = useEmailConfig();
  const updateConfig = useUpdateEmailConfig();
  const { toast } = useToast();

  const [form, setForm] = useState({
    enabled: false,
    smtp_host: '',
    smtp_port: 587,
    username: '',
    password: '',
    from_address: '',
    to_address: '',
    use_tls: true,
  });

  // Sync form with server data
  useEffect(() => {
    if (config) {
      setForm({
        enabled: config.enabled,
        smtp_host: config.smtp_host,
        smtp_port: config.smtp_port,
        username: config.username,
        password: config.password,
        from_address: config.from_address,
        to_address: config.to_address,
        use_tls: config.use_tls,
      });
    }
  }, [config]);

  function handleSave() {
    updateConfig.mutate(form, {
      onSuccess: () => toast('Email settings saved', 'success'),
      onError: (err) => toast(err.message, 'error'),
    });
  }

  return (
    <Card>
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-ct-blue/10">
          <Mail size={18} className="text-ct-blue" />
        </div>
        <CardTitle className="mb-0">Email Notifications</CardTitle>
      </div>

      <p className="text-xs text-ct-text-muted mb-4">
        Receive email alerts when buy or sell orders are filled. Configure your SMTP server below.
      </p>

      <Toggle
        label="Enable Email"
        description="Send email notifications for order fills"
        checked={form.enabled}
        onChange={(checked) => setForm((f) => ({ ...f, enabled: checked }))}
      />

      <div className="mt-4 space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="SMTP Host"
            placeholder="smtp.gmail.com"
            value={form.smtp_host}
            onChange={(e) => setForm((f) => ({ ...f, smtp_host: e.target.value }))}
          />
          <NumberInput
            label="SMTP Port"
            value={form.smtp_port}
            onChange={(v) => setForm((f) => ({ ...f, smtp_port: v }))}
            min={1}
            max={65535}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="Username"
            placeholder="user@gmail.com"
            value={form.username}
            onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
          />
          <TextInput
            label="Password"
            type="password"
            placeholder="App password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="From Address"
            placeholder="alerts@example.com"
            value={form.from_address}
            onChange={(e) => setForm((f) => ({ ...f, from_address: e.target.value }))}
          />
          <TextInput
            label="To Address"
            placeholder="you@example.com"
            value={form.to_address}
            onChange={(e) => setForm((f) => ({ ...f, to_address: e.target.value }))}
          />
        </div>

        <Toggle
          label="Use TLS"
          description="Enable STARTTLS encryption (recommended)"
          checked={form.use_tls}
          onChange={(checked) => setForm((f) => ({ ...f, use_tls: checked }))}
        />
      </div>

      <div className="mt-4 flex gap-2">
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-ct-accent text-ct-bg hover:bg-ct-accent/90 disabled:opacity-50 transition-colors"
        >
          {updateConfig.isPending ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </Card>
  );
}
