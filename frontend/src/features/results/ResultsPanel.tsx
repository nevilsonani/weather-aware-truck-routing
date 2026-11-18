import type { TripPlan } from '../../api/types'
import { formatDateTime, formatLbs } from '../../lib/format'
import { useUiStore } from '../../store/ui'
import { CheckpointList } from './CheckpointList'
import { RecommendationBanner } from './RecommendationBanner'
import { RouteCard } from './RouteCard'

export function ResultsPanel({ plan }: { plan: TripPlan }) {
  const selectedId = useUiStore((s) => s.selectedRouteId)
  const selectRoute = useUiStore((s) => s.selectRoute)
  const selected = plan.routes.find((r) => r.id === selectedId) ?? plan.routes[0]
  const winner = plan.routes.find((r) => r.id === plan.recommendation.route_id)
  const { trip } = plan

  return (
    <div className="space-y-4">
      <RecommendationBanner plan={plan} />

      <p className="text-xs leading-relaxed text-slate-500">
        Departs {formatDateTime(trip.departure_utc, trip.origin.timezone)} · {formatLbs(trip.load_weight_lbs)}{' '}
        load ({formatLbs(trip.gross_weight_lbs)} gross) · weather every {trip.sample_interval_mi} mi at each
        checkpoint&apos;s ETA · {trip.apply_hos ? 'HOS stops included' : 'no HOS stops'} ·{' '}
        {trip.provider === 'valhalla' ? 'truck routing' : `routing: ${trip.provider}`}
      </p>

      {plan.warnings.length > 0 && (
        <details
          className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900"
          open
        >
          <summary className="cursor-pointer font-semibold">
            {plan.warnings.length} note{plan.warnings.length > 1 ? 's' : ''} about this plan
          </summary>
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {plan.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </details>
      )}

      <section aria-label="Route options" className="space-y-2">
        {plan.routes.map((route) => (
          <RouteCard
            key={route.id}
            route={route}
            selected={route.id === selected.id}
            winnerLabel={winner?.label ?? ''}
            onSelect={selectRoute}
          />
        ))}
      </section>

      <CheckpointList route={selected} />
    </div>
  )
}
