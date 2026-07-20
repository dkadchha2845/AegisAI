/// <reference types="vite/client" />

/** Typed env access. `VITE_API_BASE` lets the frontend point at a backend on
 *  another host — useful when the API runs in a container or on a second
 *  laptop during a demo. Defaults to localhost:8000 in lib/api.ts. */
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
