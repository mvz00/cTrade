import { useEmailConfig, useUpdateEmailConfig, useTestEmail } from '@/api/hooks/useConfig';
import { Card, CardTitle } from '@/components/ui/Card';
import { TextInput } from '@/components/ui/TextInput';
import { Toggle } from '@/components/ui/Toggle';
import { useToast } from '@/components/ui/Toast';
import { Mail, SendHorizonal } from 'lucide-react';
import { useEffect, useState } from 'react';

export function EmailNotificationCard() {
  const { data: config } = useEmailConfig();
  const updateConfig = useUpdateEmailConfig();
  const testEmail = useTestEmail();
  const { toast } = useToast();

  const [form, setForm] = useState({
    enabled: false,
    api_key: '',
    from_address: '',
    to_address: '',
    notify_on_buy: true,
    notify_on_sell: true,
  });

  // Sync form with server data
  useEffect(() => {
    if (config) {
      setForm({
        enabled: config.enabled,
        api_key: config.api_key,
        from_address: config.from_address,
        to_address: config.to_address,
        notify_on_buy: config.notify_on_buy,
        notify_on_sell: config.notify_on_sell,
      });
    }
  }, [config]);

  function handleSave() {
    updateConfig.mutate(form, {
      onSuccess: () => toast('Email settings saved', 'success'),
      onError: (err) => toast(err.message, 'error'),
    });
  }

  function handleTestEmail() {
    testEmail.mutate(undefined, {
      onSuccess: (result) => {
        if (result.success) {
          toast('Test email sent! Check your inbox.', 'success');
        } else {
          toast(`Test email failed: ${result.error}`, 'error');
        }
      },
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
        Receive email alerts when orders are filled. Powered by MailerSend.
      </p>

      <Toggle
        label="Enable Email"
        description="Activate email notifications"
        checked={form.enabled}
        onChange={(checked) => setForm((f) => ({ ...f, enabled: checked }))}
        tooltip="Master switch for all email notifications. Requires a valid API key and addresses."
      />

      <div className="mt-4 space-y-3">
        <TextInput
          label="MailerSend API Key"
          type="password"
          placeholder="mlsn.abc123..."
          value={form.api_key}
          onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
          tooltip="Your MailerSend API key for sending transactional emails. Get one at mailersend.com."
        />

        <div className="grid grid-cols-2 gap-3">
          <TextInput
            label="From Address"
            placeholder="alerts@yourdomain.com"
            value={form.from_address}
            onChange={(e) => setForm((f) => ({ ...f, from_address: e.target.value }))}
            tooltip="The sender email address. Must be from a verified domain in your MailerSend account."
          />
          <TextInput
            label="To Address"
            placeholder="you@example.com"
            value={form.to_address}
            onChange={(e) => setForm((f) => ({ ...f, to_address: e.target.value }))}
            tooltip="The email address where trade notifications will be sent."
          />
        </div>

        <div className="pt-2 border-t border-ct-border">
          <p className="text-xs text-ct-text-muted mb-2 font-medium">Order Notifications</p>
          <div className="space-y-2">
            <Toggle
              label="Notify on Buy"
              description="Email when any coin is bought"
              checked={form.notify_on_buy}
              onChange={(checked) => setForm((f) => ({ ...f, notify_on_buy: checked }))}
            />
            <Toggle
              label="Notify on Sell"
              description="Email when any coin is sold"
              checked={form.notify_on_sell}
              onChange={(checked) => setForm((f) => ({ ...f, notify_on_sell: checked }))}
            />
          </div>
        </div>
      </div>

      <div className="mt-4 flex gap-2">
        <button
          onClick={handleSave}
          disabled={updateConfig.isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium bg-ct-accent text-ct-bg hover:bg-ct-accent/90 disabled:opacity-50 transition-colors"
        >
          {updateConfig.isPending ? 'Saving...' : 'Save Settings'}
        </button>
        <button
          onClick={handleTestEmail}
          disabled={testEmail.isPending || !form.enabled}
          className="px-4 py-2 rounded-lg text-sm font-medium border border-ct-border text-ct-text hover:bg-ct-bg-secondary disabled:opacity-50 transition-colors flex items-center gap-1.5"
        >
          <SendHorizonal size={14} />
          {testEmail.isPending ? 'Sending...' : 'Send Test Email'}
        </button>
      </div>
    </Card>
  );
}
