import React, { useState } from 'react';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { User, Shield, Key } from 'lucide-react';

export const ProfilePage: React.FC = () => {
  const { user, updateUser } = useAuth();
  
  const [fullName, setFullName] = useState(user?.full_name || '');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: 'success' | 'error', text: string } | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMessage(null);

    if (password && password !== confirmPassword) {
      setStatusMessage({ type: 'error', text: 'Passwords do not match.' });
      return;
    }

    setLoading(true);
    try {
      const payload: any = { full_name: fullName };
      if (password) {
        payload.password = password;
      }
      
      await api.put('/api/auth/profile', payload);
      
      updateUser(fullName);
      setPassword('');
      setConfirmPassword('');
      setStatusMessage({ type: 'success', text: 'Profile updated successfully.' });
    } catch (err: any) {
      setStatusMessage({ 
        type: 'error', 
        text: err.response?.data?.detail || 'Failed to update profile.' 
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold">Account Profile</h2>
        <p className="text-sm text-gray-500 dark:text-dark-muted">Manage your authentication details and role profiles.</p>
      </div>

      <Card className="p-8 border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card shadow-lg">
        <form onSubmit={handleSubmit} className="space-y-6">
          {statusMessage && (
            <div className={`p-4 rounded-xl text-xs font-semibold border ${
              statusMessage.type === 'success' 
                ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-950/20 dark:text-emerald-400 border-emerald-500/10'
                : 'bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400 border-red-500/10'
            }`}>
              {statusMessage.text}
            </div>
          )}

          <div className="flex items-center gap-4 border-b border-gray-200/50 dark:border-white/5 pb-6">
            <div className="w-14 h-14 rounded-full bg-brand-100 dark:bg-brand-900/30 text-brand-500 flex items-center justify-center font-display font-bold text-2xl">
              {user?.full_name?.charAt(0).toUpperCase() || 'U'}
            </div>
            <div>
              <h3 className="font-semibold text-lg">{user?.full_name}</h3>
              <p className="text-xs text-gray-500 dark:text-dark-muted flex items-center gap-1.5 mt-0.5 capitalize">
                <Shield className="w-3.5 h-3.5 text-brand-500" />
                <span>Role privileges: {user?.role}</span>
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Input
              label="Email Address"
              id="email"
              type="email"
              value={user?.email || ''}
              disabled
              helperText="Contact admin to modify registered email addresses."
            />

            <Input
              label="Full Name"
              id="fullName"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
          </div>

          <div className="h-px bg-gray-200 dark:bg-dark-border" />

          <div>
            <h4 className="font-semibold text-base mb-4 flex items-center gap-2">
              <Key className="w-5 h-5 text-brand-500" />
              <span>Modify Password</span>
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Input
                label="New Password"
                id="password"
                type="password"
                placeholder="Leave blank to keep current"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />

              <Input
                label="Confirm New Password"
                id="confirmPassword"
                type="password"
                placeholder="Leave blank to keep current"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
              />
            </div>
          </div>

          <Button type="submit" loading={loading} className="px-6 py-2.5">
            Save Changes
          </Button>
        </form>
      </Card>
    </div>
  );
};


