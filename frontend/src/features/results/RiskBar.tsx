import type { RouteSummary } from '../../api/types'
import { formatMiles } from '../../lib/format'
import { RISK_LEVELS, UNKNOWN_STYLE } from '../../lib/risk'

/** Stacked bar of miles per risk level along the route. */
export function RiskBar({ summary }: { summary: RouteSummary }) {
  const parts = [
    ...RISK_LEVELS.map((l) => ({
      key: l.key,
      label: l.label,
      color: l.color,
      miles: summary.miles_by_level[l.key],
    })),
    {
      key: 'unknown',
      label: UNKNOWN_STYLE.label,
      color: UNKNOWN_STYLE.color,
      miles: summary.miles_by_level.unknown,
    },
  ].filter((p) => p.miles > 0)
  const total = parts.reduce((sum, p) => sum + p.miles, 0) || 1
  const description = parts.map((p) => `${p.label} ${formatMiles(p.miles)}`).join(', ')
  return (
    <div
      role="img"
      aria-label={`Miles by risk level: ${description}`}
      className="flex h-2 overflow-hidden rounded-full bg-slate-100"
    >
      {parts.map((p) => (
        <div
          key={p.key}
          title={`${p.label}: ${formatMiles(p.miles, 1)}`}
          style={{ width: `${(p.miles / total) * 100}%`, background: p.color }}
        />
      ))}
    </div>
  )
}
