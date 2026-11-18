import type { CanvasSource } from 'maplibre-gl'
import { useEffect, useMemo, useRef } from 'react'
import { useMap } from 'react-map-gl/maplibre'
import type { Heatmap, HeatmapMetric, Meta } from '../../api/types'
import { useUiStore } from '../../store/ui'
import type { LngLat } from '../../lib/geo'
import { buildLut, buildScale } from '../heatmap/colorScales'
import { buildCorridorMask } from '../heatmap/corridorMask'
import { HeatmapRenderer } from '../heatmap/renderer'

const SOURCE_ID = 'corridor-heatmap'
const LAYER_ID = 'corridor-heatmap'

interface Props {
  heatmap: Heatmap
  metric: HeatmapMetric
  meta: Meta
  departureMs: number
  routes: LngLat[][]
  bufferMiles: number
}

/**
 * Imperative MapLibre canvas layer. Slider/animation updates bypass React entirely: we
 * subscribe to the store, repaint a small bitmap (~1 ms) and ask MapLibre to re-upload it
 * for exactly one frame (`play` → render → `pause`), so the map is not re-rendered by React
 * and does not repaint continuously while idle.
 */
export function HeatmapLayer({ heatmap, metric, meta, departureMs, routes, bufferMiles }: Props) {
  const { current: mapRef } = useMap()
  const renderer = useMemo(() => new HeatmapRenderer(heatmap), [heatmap])
  const mask = useMemo(
    () => buildCorridorMask(renderer.width, renderer.height, heatmap.grid, routes, bufferMiles * 1609.344),
    [renderer, heatmap, routes, bufferMiles],
  )
  const scale = useMemo(() => buildScale(metric, meta), [metric, meta])
  const lut = useMemo(() => buildLut(scale), [scale])
  const canvasRef = useRef<HTMLCanvasElement | null>(null)

  // Create / tear down the source and layer when the heat-map data changes.
  useEffect(() => {
    const map = mapRef?.getMap()
    if (!map) return
    const canvas = document.createElement('canvas')
    canvas.width = renderer.width
    canvas.height = renderer.height
    canvasRef.current = canvas
    const { west, east, south, north } = heatmap.grid
    map.addSource(SOURCE_ID, {
      type: 'canvas',
      canvas,
      animate: false,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    })
    // Below the basemap's labels so place names stay readable, above everything else.
    const firstSymbol = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id
    map.addLayer(
      {
        id: LAYER_ID,
        type: 'raster',
        source: SOURCE_ID,
        paint: { 'raster-opacity': 0.9, 'raster-resampling': 'linear', 'raster-fade-duration': 0 },
      },
      firstSymbol,
    )
    return () => {
      canvasRef.current = null
      if (map.getLayer(LAYER_ID)) map.removeLayer(LAYER_ID)
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID)
    }
  }, [mapRef, heatmap, renderer])

  // Repaint whenever the metric changes or the slider hour moves.
  useEffect(() => {
    const map = mapRef?.getMap()
    const canvas = canvasRef.current
    if (!map || !canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const image = ctx.createImageData(canvas.width, canvas.height)
    let frameRequest = 0

    const paint = (hour: number) => {
      renderer.render(image, metric, renderer.frameAt(departureMs + hour * 3_600_000), lut, scale.max)
      ctx.putImageData(image, 0, 0)
      if (mask) {
        ctx.globalCompositeOperation = 'destination-in'
        ctx.drawImage(mask, 0, 0)
        ctx.globalCompositeOperation = 'source-over'
      }
      const source = map.getSource<CanvasSource>(SOURCE_ID)
      if (!source) return
      source.play()
      map.once('render', () => source.pause())
    }
    const schedule = (hour: number) => {
      cancelAnimationFrame(frameRequest)
      frameRequest = requestAnimationFrame(() => paint(hour))
    }

    paint(useUiStore.getState().hour)
    const unsubscribe = useUiStore.subscribe((state, previous) => {
      if (state.hour !== previous.hour) schedule(state.hour)
    })
    return () => {
      unsubscribe()
      cancelAnimationFrame(frameRequest)
    }
  }, [mapRef, renderer, mask, metric, lut, scale, departureMs])

  return null
}
