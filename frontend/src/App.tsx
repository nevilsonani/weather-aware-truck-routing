import { Suspense, lazy, useMemo } from 'react'
import { MapProvider } from 'react-map-gl/maplibre'
import { useHeatmap, useMeta, usePlanTrip } from './api/hooks'
import type { TripPlanRequest } from './api/types'
import { HeatmapControls } from './features/heatmap/HeatmapControls'
import { MapLegend } from './features/map/MapLegend'
import { ResultsPanel } from './features/results/ResultsPanel'
import { TripForm } from './features/trip-form/TripForm'
import { buildRouteModels } from './lib/routeModel'
import { useUiStore } from './store/ui'

// MapLibre is the heaviest dependency; load it in parallel with the form's first paint.
const TripMap = lazy(() => import('./features/map/TripMap'))

export default function App() {
  const meta = useMeta()
  const planTrip = usePlanTrip()
  const plan = planTrip.data
  const heatmap = useHeatmap(plan)
  const models = useMemo(() => (plan ? buildRouteModels(plan) : []), [plan])
  const resetForPlan = useUiStore((s) => s.resetForPlan)

  const submit = (request: TripPlanRequest) =>
    planTrip.mutate(request, { onSuccess: (result) => resetForPlan(result.recommendation.route_id) })

  return (
    <MapProvider>
      <div className="flex h-dvh flex-col bg-slate-100 text-slate-900 md:flex-row">
        <aside className="order-2 flex min-h-0 flex-col border-slate-200 bg-white md:order-1 md:w-[420px] md:shrink-0 md:border-r">
          <header className="border-b border-slate-100 px-5 py-4">
            <h1 className="text-base font-semibold tracking-tight">Weather-aware truck routing</h1>
            <p className="text-xs text-slate-500">
              Compare three routes by forecast weather at each checkpoint&apos;s ETA, load-adjusted risk and
              travel time.
            </p>
          </header>
          <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
            <TripForm
              meta={meta.data}
              submitting={planTrip.isPending}
              error={planTrip.error}
              onSubmit={submit}
            />
            {plan ? (
              <div className={planTrip.isPending ? 'pointer-events-none opacity-50 transition-opacity' : ''}>
                <ResultsPanel plan={plan} />
              </div>
            ) : (
              <EmptyState />
            )}
          </div>
        </aside>

        <main className="relative order-1 h-[62dvh] min-h-[340px] md:order-2 md:h-auto md:flex-1">
          <Suspense fallback={<div className="size-full animate-pulse bg-slate-200" />}>
            <TripMap plan={plan} models={models} heatmap={heatmap.data} meta={meta.data} />
          </Suspense>
          <div className="pointer-events-none absolute top-3 left-3 hidden sm:block">
            <MapLegend />
          </div>
          <div className="pointer-events-none absolute inset-x-2 bottom-7 flex justify-center sm:inset-x-3 sm:bottom-8">
            <HeatmapControls
              plan={plan}
              models={models}
              meta={meta.data}
              heatmap={heatmap.data}
              loading={heatmap.isFetching}
              error={heatmap.error}
            />
          </div>
        </main>
      </div>
    </MapProvider>
  )
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-600">
      <p className="font-medium text-slate-800">How it works</p>
      <ol className="mt-1.5 list-inside list-decimal space-y-1 text-xs leading-relaxed">
        <li>
          Three distinct truck routes are generated (alternatives are forced when the router offers fewer).
        </li>
        <li>
          Weather is sampled along each route at the time the truck is expected to be there, including
          mandatory rest stops.
        </li>
        <li>
          Wind, rain and snow are classified with the load-weight rules; the safest route wins, then the
          fastest.
        </li>
        <li>Scrub the 0–48 h slider to watch the corridor forecast evolve as the trucks move.</li>
      </ol>
    </div>
  )
}
