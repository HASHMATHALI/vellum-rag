import React, { useEffect, useRef, useState } from 'react';
import api from '../services/api';

// Minimal typing for Google Identity Services (https://developers.google.com/identity/gsi/web)
declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (cfg: Record<string, unknown>) => void;
          renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
          disableAutoSelect: () => void;
        };
      };
    };
  }
}

const GSI_SRC = 'https://accounts.google.com/gsi/client';
let gsiLoading: Promise<void> | null = null;

const loadGsi = () => {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!gsiLoading) {
    gsiLoading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = GSI_SRC;
      s.async = true;
      s.defer = true;
      s.onload = () => resolve();
      s.onerror = () => { gsiLoading = null; reject(new Error('Could not load Google sign-in')); };
      document.head.appendChild(s);
    });
  }
  return gsiLoading;
};

interface Props {
  onCredential: (credential: string) => void;
  onError?: (message: string) => void;
}

/** Renders Google's own "Sign in with Google" button when the server has a Google client ID configured. */
export const GoogleSignInButton: React.FC<Props> = ({ onCredential, onError }) => {
  const ref = useRef<HTMLDivElement>(null);
  const [clientId, setClientId] = useState<string | null>(null);
  const callback = useRef(onCredential);
  callback.current = onCredential;

  useEffect(() => {
    let cancelled = false;
    api.get('/api/auth/config')
      .then((r) => { if (!cancelled) setClientId(r.data.google_client_id || null); })
      .catch(() => { /* Google sign-in simply stays hidden */ });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!clientId || !ref.current) return;
    let cancelled = false;
    loadGsi()
      .then(() => {
        if (cancelled || !ref.current || !window.google) return;
        window.google.accounts.id.initialize({
          client_id: clientId,
          callback: (resp: { credential?: string }) => {
            if (resp.credential) callback.current(resp.credential);
            else onError?.('Google sign-in was cancelled.');
          },
          ux_mode: 'popup',
          use_fedcm_for_prompt: true,
        });
        window.google.accounts.id.renderButton(ref.current, {
          type: 'standard', theme: 'filled_black', shape: 'pill', size: 'large', text: 'continue_with',
          width: ref.current.offsetWidth || 320,
        });
      })
      .catch((e: Error) => onError?.(e.message));
    return () => { cancelled = true; };
  }, [clientId, onError]);

  if (!clientId) return null;
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 text-[11px] uppercase tracking-wider text-zinc-500">
        <span className="h-px flex-1 bg-zinc-700" />or<span className="h-px flex-1 bg-zinc-700" />
      </div>
      <div ref={ref} className="flex justify-center min-h-[44px]" />
    </div>
  );
};
