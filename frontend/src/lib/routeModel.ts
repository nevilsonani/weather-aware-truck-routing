import type { Feature, FeatureCollection, LineString } from 'geojson'
import type { RiskLevel, RoutePlan, TripPlan } from '../api/types'
import { type LngLat, RouteLine, decodePolyline, haversineMi, interpolate } from './geo'

export type TruckActivity = 'waiting' | 'driving' | 'break' | 'rest' | 'arrived'

export interface StopWindow {
  kind: 'break' | 'rest'
  startS: number
  endS: number
}

/** Everything the map needs about one route, derived once per plan. */
export interface RouteModel {
  route: RoutePlan
  line: RouteLine
  timelineS: Float64Array
  timelineMi: Float64Array
  stops: StopWindow[]
  riskSegments: FeatureCollection<LineString, { routeId: string; level: RiskLevel | 'unknown' }>
  labelAt: LngLat
}

export interface TruckState {
  position: LngLat
  mile: number
  activity: TruckActivity
}

export function buildRouteModels(plan: TripPlan): RouteModel[] {
  const departureMs = Date.parse(plan.trip.departure_utc)
  const models = plan.routes.map((route) => {
    const line = new RouteLine(decodePolyline(route.geometry), route.distance_mi)
    return {
      route,
      line,
      timelineS: Float64Array.from(route.timeline, ([s]) => s),
      timelineMi: Float64Array.from(route.timeline, ([, mi]) => mi),
      stops: route.rest_stops.map((stop) => ({
        kind: stop.kind,
        startS: (Date.parse(stop.start_utc) - departureMs) / 1000,
        endS: (Date.parse(stop.end_utc) - departureMs) / 1000,
      })),
      riskSegments: buildRiskSegments(route, line),
      labelAt: line.positionAt(line.length / 2),
    }
  })
  placeLabels(models)
  return models
}

/** Consecutive checkpoints with the same level become one coloured line feature. */
function buildRiskSegments(route: RoutePlan, line: RouteLine): RouteModel['riskSegments'] {
  const features: Feature<LineString, { routeId: string; level: RiskLevel | 'unknown' }>[] = []
  let current: { level: RiskLevel | 'unknown'; from: number; to: number } | null = null
  const flush = () => {
    if (!current) return
    features.push({
      type: 'Feature',
      properties: { routeId: route.id, level: current.level },
      geometry: { type: 'LineString', coordinates: line.slice(current.from, current.to) },
    })
  }
  for (const cp of route.checkpoints) {
    const level = cp.risk?.level ?? 'unknown'
    const [from, to] = cp.coverage_mi
    if (current && current.level === level) {
      current.to = to
    } else {
      flush()
      current = { level, from, to }
    }
  }
  flush()
  return { type: 'FeatureCollection', features }
}

/** Put each route's A/B/C badge where it is farthest from the other routes. */
function placeLabels(models: RouteModel[]): void {
  if (models.length < 2) return
  for (const model of models) {
    const others = models.filter((m) => m !== model)
    let best = -1
    for (let f = 0.2; f <= 0.8; f += 0.05) {
      const candidate = model.line.positionAt(model.line.length * f)
      let nearest = Infinity
      for (const other of others) {
        for (let g = 0; g <= 1; g += 0.02) {
          nearest = Math.min(nearest, haversineMi(candidate, other.line.positionAt(other.line.length * g)))
        }
      }
      if (nearest > best) {
        best = nearest
        model.labelAt = candidate
      }
    }
  }
}

/** Where the truck on this route is `elapsedS` seconds after departure. */
export function truckStateAt(model: RouteModel, elapsedS: number): TruckState {
  const mile = interpolate(model.timelineS, model.timelineMi, elapsedS)
  const position = model.line.positionAt(mile)
  if (elapsedS < 0) return { position, mile: 0, activity: 'waiting' }
  if (elapsedS >= model.route.total_time_s) return { position, mile, activity: 'arrived' }
  const stop = model.stops.find((s) => elapsedS >= s.startS && elapsedS < s.endS)
  return { position, mile, activity: stop ? stop.kind : 'driving' }
}

export function boundsOf(models: RouteModel[]): [LngLat, LngLat] | null {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const { line } of models) {
    for (const [x, y] of line.coords) {
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
  }
  return Number.isFinite(minX)
    ? [
        [minX, minY],
        [maxX, maxY],
      ]
    : null
}
