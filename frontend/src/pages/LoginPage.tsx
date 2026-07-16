import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card } from '../components/ui/Card';
import { Mail, Lock } from 'lucide-react';

export const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.message || 'Incorrect email or password.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6">
        
        {/* Brand Header */}
        <div className="text-center">
          <Link to="/" className="inline-flex items-center gap-2 font-display text-3xl font-black text-gray-900 dark:text-white">
            <span>Vellum <span className="font-normal text-zinc-500 dark:text-zinc-400">RAG</span></span>
          </Link>
          <h2 className="mt-3 text-2xl font-bold tracking-tight">Access your Console</h2>
          <p className="mt-1.5 text-sm text-gray-500 dark:text-dark-muted">
            Enter your credentials to manage documents and chat.
          </p>
        </div>

        {/* Login Card */}
        <Card className="p-8 shadow-xl border-gray-200/50 dark:border-white/5 bg-white dark:bg-dark-card">
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="p-3.5 rounded-xl bg-red-50 text-red-600 dark:bg-red-950/20 dark:text-red-400 text-xs font-semibold border border-red-500/10">
                {error}
              </div>
            )}

            <div className="space-y-4">
              <Input
                label="Email Address"
                id="email"
                type="email"
                placeholder="user@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />

              <Input
                label="Password"
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <Button type="submit" loading={loading} className="w-full">
              Sign In
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
};


