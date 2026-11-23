import React, { createContext, useCallback, useEffect, useState } from 'react';
import api, { errorMessage, refreshSession, setCsrfToken } from '../services/api';

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: 'guest' | 'user' | 'admin';
  mfa_enabled?: boolean;
}

export type LoginResult = { mfaRequired: true; mfaToken: string } | { mfaRequired: false };

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<LoginResult>;
  loginMfa: (mfaToken: string, code: string) => Promise<void>;
  loginWithGoogle: (credential: string) => Promise<LoginResult>;
  register: (email: string, password: string, fullName: string) => Promise<LoginResult>;
  logout: () => Promise<void>;
  updateUser: (patch: Partial<User>) => void;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface SessionPayload { user: User; csrf_token: string }

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const applySession = (data: SessionPayload) => {
    setCsrfToken(data.csrf_token);
    setUser(data.user);
    setError(null);
  };

  /** Each visitor without an account gets an isolated, short-lived guest workspace (never a shared account). */
  const startGuest = useCallback(async () => {
    try {
      const r = await api.post<SessionPayload>('/api/auth/guest');
      applySession(r.data);
    } catch (e) {
      setUser(null);
      setError(errorMessage(e, 'Could not start a session.'));
    }
  }, []);

  const restore = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get<SessionPayload>('/api/auth/session');
      applySession(r.data);
    } catch {
      if (await refreshSession()) {
        try {
          const r = await api.get<SessionPayload>('/api/auth/session');
          applySession(r.data);
          return;
        } catch { /* fall through to guest */ }
      }
      await startGuest();
    } finally {
      setLoading(false);
    }
  }, [startGuest]);

  useEffect(() => {
    restore();
    const onExpired = () => { restore(); };
    window.addEventListener('vellum:session-expired', onExpired);
    return () => window.removeEventListener('vellum:session-expired', onExpired);
  }, [restore]);

  const login = async (email: string, password: string): Promise<LoginResult> => {
    try {
      const r = await api.post('/api/auth/login', { email, password });
      if (r.data.mfa_required) return { mfaRequired: true, mfaToken: r.data.mfa_token };
      applySession(r.data);
      return { mfaRequired: false };
    } catch (e) {
      throw new Error(errorMessage(e, 'Authentication failed'));
    }
  };

  const loginWithGoogle = async (credential: string): Promise<LoginResult> => {
    try {
      const r = await api.post('/api/auth/google', { credential });
      if (r.data.mfa_required) return { mfaRequired: true, mfaToken: r.data.mfa_token };
      applySession(r.data);
      return { mfaRequired: false };
    } catch (e) {
      throw new Error(errorMessage(e, 'Google sign-in failed'));
    }
  };

  const loginMfa = async (mfaToken: string, code: string) => {
    try {
      const r = await api.post('/api/auth/login/mfa', { mfa_token: mfaToken, code });
      applySession(r.data);
    } catch (e) {
      throw new Error(errorMessage(e, 'Invalid authentication code'));
    }
  };

  const register = async (email: string, password: string, fullName: string) => {
    try {
      await api.post('/api/auth/register', { email, password, full_name: fullName });
    } catch (e) {
      throw new Error(errorMessage(e, 'Registration failed'));
    }
    return login(email, password);
  };

  const logout = async () => {
    try {
      await api.post('/api/auth/logout');
    } catch { /* session may already be gone */ }
    setCsrfToken(null);
    setUser(null);
    await startGuest();
  };

  const updateUser = (patch: Partial<User>) => setUser((u) => (u ? { ...u, ...patch } : u));

  return (
    <AuthContext.Provider value={{ user, loading, error, login, loginMfa, loginWithGoogle, register, logout, updateUser }}>
      {children}
    </AuthContext.Provider>
  );
};
