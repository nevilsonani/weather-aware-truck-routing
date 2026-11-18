import { describe, expect, it } from 'vitest'
import type { RoutePlan, TripPlan } from '../api/types'
import { buildRouteModels, truckStateAt } from './routeModel'

const HOUR = 3600

function route(overrides: Partial<RoutePlan> = {}): RoutePlan {
  return {
    id: 'A',
    label: 'Route A',
    name: 'via I-80',
    rank: 1,
    recommended: true,
    not_recommended_because: null,
    distance_mi: 600,
    driving_time_s: 10 * HOUR,
    stop_time_s: 0.5 * HOUR,
    total_time_s: 10.5 * HOUR,
    departure_utc: '2026-11-18T12:00:00Z',
    arrival_utc: '2026-11-18T22:30:00Z',
    arrival_timezone: 'America/Chicago',
    geometry: '_p~iF~ps|U_ulLnnqC', // two points; re-scaled to distance_mi
    summary: {
      miles_by_level: { low: 300, moderate: 0, high: 300, severe: 0, no_travel: 0, unknown: 0 },
      average_risk: 1,
      max_level: 'high',
      checkpoint_count: 2,
    },
    checkpoints: [
      { index: 0, distance_mi: 0, coverage_mi: [0, 300], risk: { level: 'low' } },
      { index: 1, distance_mi: 600, coverage_mi: [300, 600], risk: { level: 'high' } },
    ] as RoutePlan['checkpoints'],
    rest_stops: [
      {
        kind: 'break',
        start_utc: '2026-11-18T20:00:00Z',
        end_utc: '2026-11-18T20:30:00Z',
        distance_mi: 480,
        lat: 0,
        lon: 0,
      },
    ],
    // 60 mph for 8 h, 30-min break, then 2 h more
    timeline: [
      [0, 0],
      [8 * HOUR, 480],
      [8.5 * HOUR, 480],
      [10.5 * HOUR, 600],
    ],
    notices: [],
    ...overrides,
  }
}

const plan = { trip: { departure_utc: '2026-11-18T12:00:00Z' }, routes: [route()] } as unknown as TripPlan

describe('truckStateAt', () => {
  const [model] = buildRouteModels(plan)

  it('follows the timeline while driving', () => {
    const state = truckStateAt(model, 4 * HOUR)
    expect(state.activity).toBe('driving')
    expect(state.mile).toBeCloseTo(240)
  })

  it('stays put during a mandatory break', () => {
    const state = truckStateAt(model, 8.25 * HOUR)
    expect(state.activity).toBe('break')
    expect(state.mile).toBeCloseTo(480)
  })

  it('reports waiting before departure and arrival at the end', () => {
    expect(truckStateAt(model, -60).activity).toBe('waiting')
    const done = truckStateAt(model, 30 * HOUR)
    expect(done.activity).toBe('arrived')
    expect(done.mile).toBe(600)
  })
})

describe('risk segments', () => {
  it('merges consecutive checkpoints of equal level into one coloured feature each', () => {
    const [model] = buildRouteModels(plan)
    expect(model.riskSegments.features.map((f) => f.properties.level)).toEqual(['low', 'high'])
  })
})
