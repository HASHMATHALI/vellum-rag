import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import api, { errorMessage } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Shield, Key, Smartphone } from 'lucide-react';

type Status = { type: 'success' | 'error'; text: string } | null;

const StatusBox: React.FC<{ status: Status }> = ({ status }) =>
  status ? (
    <div className={`p-4 rounded-xl text-xs font-semibold border ${
      status.type === 'success'
        ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-400 border-emerald-500/10'
        : 'bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400 border-red-500/10'
    }`}>
      {status.text}
    </div>
  ) : null;

export const ProfilePage: React.FC = () => {
  const { user, updateUser } = useAuth();
  const isGuest = user?.role === 'guest';

  const [fullName, setFullName] = useState(user?.full_name || '');
  const [profileStatus, setProfileStatus] = useState<Status>(null);
  const [savingProfile, setSavingProfile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordStatus, setPasswordStatus] = useState<Status>(null);
  const [savingPassword, setSavingPassword] = useState(false);

  const [mfaSetup, setMfaSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [mfaCode, setMfaCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [mfaStatus, setMfaStatus] = useState<Status>(null);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingProfile(true);
    setProfileStatus(null);
    try {
      await api.put('/api/auth/profile', { full_name: fullName });
      updateUser({ full_name: fullName });
      setProfileStatus({ type: 'success', text: 'Profile updated.' });
    } catch (err) {
      setProfileStatus({ type: 'error', text: errorMessage(err, 'Failed to update profile.') });
    } finally {
      setSavingProfile(false);
    }
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordStatus(null);
    if (newPassword !== confirmPassword) {
      setPasswordStatus({ type: 'error', text: 'New passwords do not match.' });
      return;
    }
    setSavingPassword(true);
    try {
      await api.post('/api/auth/password', { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
      setPasswordStatus({ type: 'success', text: 'Password changed. Other devices have been signed out.' });
    } catch (err) {
      setPasswordStatus({ type: 'error', text: errorMessage(err, 'Failed to change password.') });
    } finally {
      setSavingPassword(false);
    }
  };

  const startMfa = async () => {
    setMfaStatus(null);
    try {
      const r = await api.post('/api/auth/mfa/setup');
      setMfaSetup(r.data);
    } catch (err) {
      setMfaStatus({ type: 'error', text: errorMessage(err) });
    }
  };

  const enableMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await api.post('/api/auth/mfa/enable', { code: mfaCode });
      setRecoveryCodes(r.data.recovery_codes);
      setMfaSetup(null);
      setMfaCode('');
      updateUser({ mfa_enabled: true });
      setMfaStatus({ type: 'success', text: 'Two-factor authentication is on.' });
    } catch (err) {
      setMfaStatus({ type: 'error', text: errorMessage(err, 'Invalid code.') });
    }
  };

  if (isGuest) {
    return (
      <div className="max-w-3xl mx-auto space-y-6">
        <h2 className="font-display text-2xl font-bold">Guest workspace</h2>
        <Card className="p-8 bg-white dark:bg-dark-card">
          <p className="text-sm text-gray-600 dark:text-dark-muted">
            You are using a private guest workspace. Your documents and chats are visible only to you and are deleted
            automatically after 24 hours. <Link to="/login" className="underline font-semibold">Sign in</Link> to keep your data.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold">Account Profile</h2>
        <p className="text-sm text-gray-500 dark:text-dark-muted">Manage your profile, password and two-factor authentication.</p>
      </div>

      <Card className="p-8 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg">
        <form onSubmit={saveProfile} className="space-y-6">
          <StatusBox status={profileStatus} />
          <div className="flex items-center gap-4 border-b border-gray-200/50 dark:border-white/5 pb-6">
            <div className="w-14 h-14 rounded-full bg-brand-100 dark:bg-brand-900/30 text-brand-500 flex items-center justify-center font-display font-bold text-2xl">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div>
              <h3 className="font-semibold text-lg">{user?.full_name}</h3>
              <p className="text-xs text-gray-500 dark:text-dark-muted flex items-center gap-1.5 mt-0.5 capitalize">
                <Shield className="w-3.5 h-3.5 text-brand-500" />
                <span>Role: {user?.role}</span>
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Input label="Email Address" id="email" type="email" value={user?.email || ''} disabled
              helperText="Contact an administrator to change your e-mail." />
            <Input label="Full Name" id="fullName" type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
          </div>
          <Button type="submit" loading={savingProfile} className="px-6 py-2.5">Save Profile</Button>
        </form>
      </Card>

      <Card className="p-8 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg">
        <form onSubmit={changePassword} className="space-y-6">
          <h4 className="font-semibold text-base flex items-center gap-2">
            <Key className="w-5 h-5 text-brand-500" /><span>Change Password</span>
          </h4>
          <StatusBox status={passwordStatus} />
          <Input label="Current Password" id="currentPassword" type="password" autoComplete="current-password"
            value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} required />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Input label="New Password" id="newPassword" type="password" autoComplete="new-password"
              helperText="At least 10 characters." value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required />
            <Input label="Confirm New Password" id="confirmPassword" type="password" autoComplete="new-password"
              value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} required />
          </div>
          <Button type="submit" loading={savingPassword} className="px-6 py-2.5">Change Password</Button>
        </form>
      </Card>

      <Card className="p-8 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg space-y-5">
        <h4 className="font-semibold text-base flex items-center gap-2">
          <Smartphone className="w-5 h-5 text-brand-500" /><span>Two-Factor Authentication</span>
        </h4>
        <StatusBox status={mfaStatus} />
        {recoveryCodes && (
          <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-50 dark:bg-amber-950/20 text-xs space-y-2">
            <p className="font-semibold">Recovery codes (shown once). Each code works one time if you lose your authenticator:</p>
            <pre className="font-mono whitespace-pre-wrap">{recoveryCodes.join('\n')}</pre>
          </div>
        )}
        {user?.mfa_enabled ? (
          <p className="text-sm text-gray-600 dark:text-dark-muted">Enabled. Sign-ins require a code from your authenticator app.</p>
        ) : mfaSetup ? (
          <form onSubmit={enableMfa} className="space-y-4">
            <p className="text-sm text-gray-600 dark:text-dark-muted">
              Add this key to your authenticator app (Google Authenticator, 1Password, Aegis…), then enter the 6-digit code.
            </p>
            <code className="block p-3 rounded-lg bg-gray-100 dark:bg-dark-bg font-mono text-sm break-all select-all">{mfaSetup.secret}</code>
            <Input label="Code" id="mfaCode" inputMode="numeric" autoComplete="one-time-code" value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)} required />
            <Button type="submit" className="px-6 py-2.5">Verify &amp; Enable</Button>
          </form>
        ) : (
          <Button type="button" onClick={startMfa} className="px-6 py-2.5">Set up two-factor authentication</Button>
        )}
      </Card>
    </div>
  );
};
