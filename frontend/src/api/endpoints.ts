import { config } from '../config'
import { request } from './client'
import type { CorridorGrid, Heatmap, Meta, Place, TripPlan, TripPlanRequest } from './types'

export const api = {
  meta: (signal?: AbortSignal) => request<Meta>('/api/v1/meta', { signal }),

  searchPlaces: (q: string, signal?: AbortSignal) => {
    const params = new URLSearchParams({
      q,
      limit: '6',
      lat: String(config.searchBias.lat),
      lon: String(config.searchBias.lon),
    })
    return request<{ results: Place[] }>(`/api/v1/places/search?${params}`, { signal }).then(
      (body) => body.results,
    )
  },

  planTrip: (body: TripPlanRequest) =>
    request<TripPlan>('/api/v1/trips/plan', { method: 'POST', json: body }),

  heatmap: (body: { grid: CorridorGrid; departure: string; load_weight_lbs: number }, signal?: AbortSignal) =>
    request<Heatmap>('/api/v1/trips/heatmap', { method: 'POST', json: body, signal }),
}
