import type { TripPlan } from '../../api/types'

const STATUS = {
  clear: {
    title: 'Clear to go',
    classes: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    dot: 'bg-emerald-500',
  },
  caution: {
    title: 'Proceed with caution',
    classes: 'border-amber-200 bg-amber-50 text-amber-900',
    dot: 'bg-amber-500',
  },
  no_safe_route: {
    title: 'No safe route right now',
    classes: 'border-red-200 bg-red-50 text-red-900',
    dot: 'bg-red-600',
  },
  insufficient_data: {
    title: 'Weather data incomplete',
    classes: 'border-slate-200 bg-slate-50 text-slate-800',
    dot: 'bg-slate-400',
  },
} as const

export function RecommendationBanner({ plan }: { plan: TripPlan }) {
  const { recommendation } = plan
  const status = STATUS[recommendation.status]
  const winner = plan.routes.find((r) => r.id === recommendation.route_id)
  return (
    <section aria-live="polite" className={`rounded-xl border p-3 ${status.classes}`}>
      <div className="flex items-center gap-2">
        <span className={`size-2 rounded-full ${status.dot}`} aria-hidden />
        <h2 className="text-sm font-semibold">
          {status.title} · {winner?.label} recommended
        </h2>
      </div>
      <p className="mt-1 text-sm">{recommendation.headline}</p>
      {recommendation.reasons.length > 0 && (
        <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-xs opacity-80">
          {recommendation.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[11px] opacity-70">
        Ranked by No Travel miles, then Severe miles, High miles, average risk and travel time.
      </p>
    </section>
  )
}
