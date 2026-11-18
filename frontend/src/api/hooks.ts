import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { api } from './endpoints'
import type { TripPlan, TripPlanRequest } from './types'

export function useMeta() {
  return useQuery({
    queryKey: ['meta'],
    queryFn: ({ signal }) => api.meta(signal),
    staleTime: Infinity,
  })
}

export function usePlaceSearch(query: string) {
  const q = query.trim()
  return useQuery({
    queryKey: ['places', q.toLowerCase()],
    queryFn: ({ signal }) => api.searchPlaces(q, signal),
    enabled: q.length >= 2,
    staleTime: 10 * 60_000,
    placeholderData: keepPreviousData,
  })
}

export function usePlanTrip() {
  return useMutation({
    mutationKey: ['plan'],
    mutationFn: (body: TripPlanRequest) => api.planTrip(body),
  })
}

/** Loaded after the plan so routes render immediately; cached per plan. */
export function useHeatmap(plan: TripPlan | undefined) {
  return useQuery({
    queryKey: ['heatmap', plan?.generated_at, plan?.trip.departure_utc, plan?.trip.load_weight_lbs],
    queryFn: ({ signal }) =>
      api.heatmap(
        {
          grid: plan!.corridor,
          departure: plan!.trip.departure_utc,
          load_weight_lbs: plan!.trip.load_weight_lbs,
        },
        signal,
      ),
    enabled: Boolean(plan),
    staleTime: 15 * 60_000,
    retry: 1,
  })
}
