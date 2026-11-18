/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API origin, e.g. https://api.example.com. Empty = same origin. */
  readonly VITE_API_BASE_URL?: string
  /** MapLibre style URL for the basemap. */
  readonly VITE_MAP_STYLE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
