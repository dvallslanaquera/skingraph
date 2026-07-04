/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Injected at build time by Vite's `define` (see vite.config.ts) from
// package.json — the single source of truth for the displayed app version.
declare const __APP_VERSION__: string;
