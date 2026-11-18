/** Build-time configuration (Vite env vars). */
export const config = {
  /** Empty string = same origin (production bundle served by Django, or the Vite dev proxy). */
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, ''),
  /** Any MapLibre style URL. OpenFreeMap needs no API key and has no usage limits. */
  mapStyleUrl: import.meta.env.VITE_MAP_STYLE_URL ?? 'https://tiles.openfreemap.org/styles/positron',
  /** Place search prefers results near here (continental US); other places still match. */
  searchBias: { lat: 39.5, lon: -98.35 },
} as const
