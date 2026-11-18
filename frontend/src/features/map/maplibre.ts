import * as maplibregl from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'

/*
 * MapLibre v6 locates its web worker relative to its own module URL. Bundlers (Vite's dev
 * pre-bundling, Rolldown in production) move that module, so the computed URL breaks.
 * We emit the self-contained worker as an asset, register it explicitly, and hand this exact
 * module instance to react-map-gl (`mapLib`) so no second, unconfigured copy is ever used.
 */
maplibregl.setWorkerUrl(workerUrl)

export { maplibregl }
