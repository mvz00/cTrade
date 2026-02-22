import { useState, type FormEvent } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/api/client';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { PageHeader } from '@/components/ui/PageHeader';
import { useToast } from '@/components/ui/Toast';
import { User, KeyRound, LogOut, Shield, Clock, Copy, Check } from 'lucide-react';

export function AccountPage() {
  const { username, logout } = useAuth();
  const { toast } = useToast();

  // Password change form state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [newHash, setNewHash] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handlePasswordChange(e: FormEvent) {
    e.preventDefault();
    setPasswordError(null);
    setNewHash(null);

    // Validation
    if (newPassword.length < 6) {
      setPasswordError('New password must be at least 6 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match');
      return;
    }

    setChangingPassword(true);
    try {
      const res = await api.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setNewHash(res.new_password_hash);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      toast(res.message, 'success');
    } catch (err: any) {
      setPasswordError(err.message || 'Failed to change password');
    } finally {
      setChangingPassword(false);
    }
  }

  async function handleCopyHash() {
    if (!newHash) return;
    await navigator.clipboard.writeText(newHash);
    setCopied(true);
    toast('Hash copied to clipboard', 'info');
    setTimeout(() => setCopied(false), 2000);
  }

  const inputClass =
    'w-full px-3 py-2.5 bg-ct-bg border border-ct-border rounded-lg text-ct-text text-sm outline-none focus:border-ct-accent/50 transition-colors';

  return (
    <div>
      <PageHeader title="Account" description="Manage your profile and security settings" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Profile Section */}
        <Card>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-lg bg-ct-accent/10">
              <User size={18} className="text-ct-accent" />
            </div>
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Profile</h3>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between py-3 border-b border-ct-border">
              <span className="text-sm text-ct-text-muted">Username</span>
              <span className="text-sm font-medium text-ct-text">{username || 'admin'}</span>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-ct-border">
              <span className="text-sm text-ct-text-muted">Authentication</span>
              <Badge variant="success">Active</Badge>
            </div>
            <div className="flex items-center justify-between py-3">
              <span className="text-sm text-ct-text-muted">Role</span>
              <div className="flex items-center gap-1.5">
                <Shield size={14} className="text-ct-accent" />
                <span className="text-sm font-medium text-ct-text">Administrator</span>
              </div>
            </div>
          </div>
        </Card>

        {/* Session Section */}
        <Card>
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-lg bg-ct-blue/10">
              <Clock size={18} className="text-ct-blue" />
            </div>
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Session</h3>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between py-3 border-b border-ct-border">
              <span className="text-sm text-ct-text-muted">Token type</span>
              <span className="text-sm font-medium text-ct-text">JWT Bearer</span>
            </div>
            <div className="flex items-center justify-between py-3 border-b border-ct-border">
              <span className="text-sm text-ct-text-muted">Session expires</span>
              <span className="text-sm font-medium text-ct-text">60 minutes</span>
            </div>
          </div>

          <button
            onClick={logout}
            className="mt-6 w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-ct-red/10 border border-ct-red/20 text-ct-red text-sm font-medium hover:bg-ct-red/20 transition-colors"
          >
            <LogOut size={16} />
            Sign Out
          </button>
        </Card>

        {/* Change Password Section — full width */}
        <Card className="lg:col-span-2">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 rounded-lg bg-ct-yellow/10">
              <KeyRound size={18} className="text-ct-yellow" />
            </div>
            <h3 className="text-sm font-medium text-ct-text-muted uppercase tracking-wider">Change Password</h3>
          </div>

          <form onSubmit={handlePasswordChange} className="max-w-md space-y-4">
            <div>
              <label className="block text-sm text-ct-text-muted mb-1.5">Current Password</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className={inputClass}
                placeholder="Enter current password"
              />
            </div>

            <div>
              <label className="block text-sm text-ct-text-muted mb-1.5">New Password</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={6}
                className={inputClass}
                placeholder="Minimum 6 characters"
              />
            </div>

            <div>
              <label className="block text-sm text-ct-text-muted mb-1.5">Confirm New Password</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                minLength={6}
                className={inputClass}
                placeholder="Re-enter new password"
              />
            </div>

            {passwordError && (
              <div className="px-3 py-2.5 rounded-lg bg-ct-red/10 border border-ct-red/30 text-ct-red text-sm">
                {passwordError}
              </div>
            )}

            <button
              type="submit"
              disabled={changingPassword}
              className="px-6 py-2.5 rounded-lg bg-ct-accent text-ct-bg text-sm font-medium hover:bg-ct-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {changingPassword ? 'Changing...' : 'Change Password'}
            </button>
          </form>

          {/* New hash display */}
          {newHash && (
            <div className="mt-6 p-4 rounded-lg bg-ct-bg border border-ct-green/30">
              <p className="text-sm text-ct-green mb-2 font-medium">Password changed successfully!</p>
              <p className="text-xs text-ct-text-muted mb-2">
                Update <code className="text-ct-accent">CTRADE_AUTH__PASSWORD_HASH</code> in your <code className="text-ct-accent">.env</code> file:
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-xs text-ct-text bg-ct-bg-card px-3 py-2 rounded border border-ct-border font-mono break-all">
                  {newHash}
                </code>
                <button
                  onClick={handleCopyHash}
                  className="p-2 rounded-lg hover:bg-ct-bg-hover text-ct-text-muted hover:text-ct-text transition-colors flex-shrink-0"
                  title="Copy hash"
                >
                  {copied ? <Check size={16} className="text-ct-green" /> : <Copy size={16} />}
                </button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
