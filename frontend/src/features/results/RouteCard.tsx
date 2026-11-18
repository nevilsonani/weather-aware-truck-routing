import { memo } from 'react'
import type { RoutePlan } from '../../api/types'
import { formatDateTime, formatDuration, formatMiles } from '../../lib/format'
import { riskStyle } from '../../lib/risk'
import { RiskBar } from './RiskBar'

interface Props {
  route: RoutePlan
  selected: boolean
  winnerLabel: string
  onSelect: (id: string) => void
}

export const RouteCard = memo(function RouteCard({ route, selected, winnerLabel, onSelect }: Props) {
  const m = route.summary.miles_by_level
  const exposure = [
    { level: 'no_travel' as const, miles: m.no_travel },
    { level: 'severe' as const, miles: m.severe },
    { level: 'high' as const, miles: m.high },
  ]
  return (
    <button
      type="button"
      onClick={() => onSelect(route.id)}
      aria-pressed={selected}
      className={`w-full rounded-xl border p-3 text-left transition ${
        selected
          ? 'border-slate-900 bg-white shadow-md ring-1 ring-slate-900'
          : 'border-slate-200 bg-white hover:border-slate-400'
      }`}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={`flex size-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${
            selected ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700'
          }`}
        >
          {route.id}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-2">
            <h3 className="truncate text-sm font-semibold text-slate-900" title={route.name}>
              {route.name}
            </h3>
            {route.recommended ? (
              <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 ring-1 ring-emerald-200">
                ★ Recommended
              </span>
            ) : (
              <span className="shrink-0 text-[11px] font-medium text-slate-400">#{route.rank}</span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-slate-600 tabular-nums">
            {formatMiles(route.distance_mi)} · {formatDuration(route.driving_time_s)} driving
            {route.stop_time_s > 0 && <> · {formatDuration(route.total_time_s)} with stops</>}
          </p>
          <p className="text-xs text-slate-500 tabular-nums">
            Arrives {formatDateTime(route.arrival_utc, route.arrival_timezone)}
          </p>
        </div>
      </div>

      <div className="mt-2.5">
        <RiskBar summary={route.summary} />
        <dl className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] tabular-nums">
          {exposure.map(({ level, miles }) => (
            <div key={level} className="flex gap-1">
              <dt className="text-slate-500">{riskStyle(level).label}</dt>
              <dd className="font-semibold" style={{ color: miles > 0 ? riskStyle(level).color : '#334155' }}>
                {formatMiles(miles)}
              </dd>
            </div>
          ))}
          <div className="flex gap-1">
            <dt className="text-slate-500">Avg risk</dt>
            <dd className="font-semibold text-slate-700">
              {route.summary.average_risk === null ? 'n/a' : route.summary.average_risk.toFixed(2)}
            </dd>
          </div>
        </dl>
      </div>

      {route.not_recommended_because && (
        <p className="mt-2 border-t border-slate-100 pt-1.5 text-[11px] text-slate-500">
          {winnerLabel} wins: {route.not_recommended_because.text.replace(/^./, (c) => c.toLowerCase())}
        </p>
      )}
    </button>
  )
})
