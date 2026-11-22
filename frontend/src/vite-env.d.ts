/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin for direct API calls (e.g. https://api.example.com). Empty = same origin via the gateway. */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
