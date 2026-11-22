import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';

/**
 * API client.
 *
 * Authentication uses HttpOnly cookies set by the backend (never readable by JavaScript, so an XSS bug cannot
 * steal the session). State-changing requests carry an X-CSRF-Token header; the token is kept in memory only.
 * VITE_API_BASE_URL may point at the backend directly (e.g. when a static-site proxy buffers SSE streams);
 * it is empty when the frontend and API share an origin through the nginx gateway.
 */
export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') || '';

let csrfToken: string | null = null;
export const setCsrfToken = (token: string | null) => { csrfToken = token; };
export const getCsrfToken = () => csrfToken;

const api = axios.create({ baseURL: API_BASE_URL, timeout: 60000, withCredentials: true });

const UNSAFE = new Set(['post', 'put', 'patch', 'delete']);
api.interceptors.request.use((config) => {
  if (csrfToken && UNSAFE.has((config.method || 'get').toLowerCase())) {
    config.headers.set('X-CSRF-Token', csrfToken);
  }
  return config;
});

let refreshing: Promise<boolean> | null = null;
export const refreshSession = (): Promise<boolean> => {
  if (!refreshing) {
    refreshing = axios
      .post(`${API_BASE_URL}/api/auth/refresh`, null, { withCredentials: true })
      .then((r) => { setCsrfToken(r.data.csrf_token); return true; })
      .catch(() => false)
      .finally(() => { setTimeout(() => { refreshing = null; }, 0); });
  }
  return refreshing;
};

// On 401, try one silent refresh (rotating refresh token), then replay the request.
api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const config = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const url = config?.url || '';
    if (error.response?.status === 401 && config && !config._retried && !url.includes('/api/auth/')) {
      config._retried = true;
      if (await refreshSession()) return api(config);
      window.dispatchEvent(new Event('vellum:session-expired'));
    }
    return Promise.reject(error);
  }
);

/** Human-readable message from an API error (FastAPI `detail` string or validation list). */
export const errorMessage = (err: unknown, fallback = 'Something went wrong. Please try again.'): string => {
  const e = err as AxiosError<{ detail?: unknown }>;
  const detail = e?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join('; ');
  if (e?.response?.status === 429) return 'Too many requests. Please wait a moment and try again.';
  if (e?.code === 'ECONNABORTED') return 'The request timed out. Please try again.';
  if (!e?.response) return 'Cannot reach the server. Check your connection.';
  return fallback;
};

export default api;
