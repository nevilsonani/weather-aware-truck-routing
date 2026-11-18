import type { CorridorGrid } from '../../api/types'
import type { LngLat } from '../../lib/geo'

const EARTH_RADIUS_M = 6_371_008.8
const mercatorY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))

/**
 * Soft-edged corridor mask drawn from the actual route lines.
 *
 * The forecast grid is coarse (tens of km per cell), so clipping by "cell is in the corridor"
 * produces a staircase outline. Stroking the routes with the corridor width (and a blur) gives
 * a smooth band that follows the roads; it is composited over each heat-map frame with
 * `destination-in`. Built once per heat map, reused for every animation frame.
 */
export function buildCorridorMask(
  width: number,
  height: number,
  grid: CorridorGrid,
  routes: LngLat[][],
  bufferMeters: number,
): HTMLCanvasElement | null {
  if (bufferMeters <= 0 || routes.length === 0) return null
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return null

  const yNorth = mercatorY(grid.north)
  const ySpan = yNorth - mercatorY(grid.south)
  const xSpan = grid.east - grid.west
  const project = ([lon, lat]: LngLat): [number, number] => [
    ((lon - grid.west) / xSpan) * width,
    ((yNorth - mercatorY(lat)) / ySpan) * height,
  ]
  const midLat = ((grid.north + grid.south) / 2) * (Math.PI / 180)
  const metersPerPixel = (EARTH_RADIUS_M * Math.cos(midLat) * xSpan * (Math.PI / 180)) / width
  const bufferPx = bufferMeters / metersPerPixel

  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = '#fff'
  ctx.lineWidth = bufferPx * 1.6 // slightly inside the data buffer so edges come from the mask
  ctx.filter = `blur(${Math.max(1, bufferPx * 0.3)}px)`
  for (const route of routes) {
    // The mask is low resolution; a few hundred vertices per route are plenty.
    const step = Math.max(1, Math.floor(route.length / 400))
    ctx.beginPath()
    route.forEach((point, i) => {
      if (i % step !== 0 && i !== route.length - 1) return
      const [x, y] = project(point)
      if (i === 0) ctx.moveTo(x, y)
      else ctx.lineTo(x, y)
    })
    ctx.stroke()
  }
  return canvas
}
