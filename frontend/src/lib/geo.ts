/** Polyline decoding and distance-based interpolation along a route. Coordinates are [lon, lat]. */

export type LngLat = [number, number]

const EARTH_RADIUS_MI = 3958.7613

export function decodePolyline(encoded: string, precision = 6): LngLat[] {
  const factor = 10 ** precision
  const coords: LngLat[] = []
  let index = 0
  let lat = 0
  let lon = 0
  while (index < encoded.length) {
    for (let axis = 0; axis < 2; axis++) {
      let result = 0
      let shift = 0
      let byte: number
      do {
        if (index >= encoded.length) throw new Error('Truncated polyline')
        byte = encoded.charCodeAt(index++) - 63
        result |= (byte & 0x1f) << shift
        shift += 5
      } while (byte >= 0x20)
      const delta = result & 1 ? ~(result >> 1) : result >> 1
      if (axis === 0) lat += delta
      else lon += delta
    }
    coords.push([lon / factor, lat / factor])
  }
  return coords
}

export function haversineMi(a: LngLat, b: LngLat): number {
  const toRad = Math.PI / 180
  const dLat = (b[1] - a[1]) * toRad
  const dLon = (b[0] - a[0]) * toRad
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * toRad) * Math.cos(b[1] * toRad) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Index of the last element of a sorted array that is <= value (clamped to [0, n-2]). */
export function bracket(sorted: ArrayLike<number>, value: number): number {
  let lo = 0
  let hi = sorted.length - 1
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1
    if (sorted[mid] <= value) lo = mid
    else hi = mid
  }
  return lo
}

/** Piecewise-linear interpolation of y(x) for non-decreasing xs, clamped at the ends. */
export function interpolate(xs: ArrayLike<number>, ys: ArrayLike<number>, x: number): number {
  const n = xs.length
  if (n === 0) return NaN
  if (x <= xs[0]) return ys[0]
  if (x >= xs[n - 1]) return ys[n - 1]
  const i = bracket(xs, x)
  const span = xs[i + 1] - xs[i]
  const t = span > 0 ? (x - xs[i]) / span : 0
  return ys[i] + t * (ys[i + 1] - ys[i])
}

/**
 * A route line with cumulative mileage. The geometric length is rescaled to the route's
 * reported distance so mile markers from the API line up with positions on the line.
 */
export class RouteLine {
  readonly coords: LngLat[]
  readonly miles: Float64Array

  constructor(coords: LngLat[], reportedMiles?: number) {
    this.coords = coords
    this.miles = new Float64Array(coords.length)
    for (let i = 1; i < coords.length; i++) {
      this.miles[i] = this.miles[i - 1] + haversineMi(coords[i - 1], coords[i])
    }
    const total = this.miles[coords.length - 1] ?? 0
    if (reportedMiles && total > 0) {
      const scale = reportedMiles / total
      for (let i = 0; i < this.miles.length; i++) this.miles[i] *= scale
    }
  }

  get length(): number {
    return this.miles[this.miles.length - 1] ?? 0
  }

  positionAt(mile: number): LngLat {
    const { coords, miles } = this
    if (coords.length === 1 || mile <= 0) return coords[0]
    if (mile >= this.length) return coords[coords.length - 1]
    const i = bracket(miles, mile)
    const span = miles[i + 1] - miles[i]
    const t = span > 0 ? (mile - miles[i]) / span : 0
    const [x0, y0] = coords[i]
    const [x1, y1] = coords[i + 1]
    return [x0 + t * (x1 - x0), y0 + t * (y1 - y0)]
  }

  /** Sub-line between two mile markers (inclusive of interpolated end points). */
  slice(fromMile: number, toMile: number): LngLat[] {
    const start = Math.max(0, Math.min(fromMile, toMile))
    const end = Math.min(this.length, Math.max(fromMile, toMile))
    const out: LngLat[] = [this.positionAt(start)]
    for (let i = bracket(this.miles, start) + 1; i < this.coords.length; i++) {
      if (this.miles[i] >= end) break
      if (this.miles[i] > start) out.push(this.coords[i])
    }
    out.push(this.positionAt(end))
    return out
  }
}
