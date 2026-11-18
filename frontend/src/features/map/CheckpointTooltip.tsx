import type { Checkpoint, RoutePlan } from '../../api/types'
import { formatDateTime, formatMiles, formatRate } from '../../lib/format'
import { riskStyle } from '../../lib/risk'

const CONDITION_LABEL = { wind: 'Wind', rain: 'Rain', snow: 'Snow' } as const

export function CheckpointTooltip({ route, checkpoint }: { route: RoutePlan; checkpoint: Checkpoint }) {
  const style = riskStyle(checkpoint.risk?.level)
  const { weather, risk } = checkpoint
  const isEnd = checkpoint.index === route.checkpoints.length - 1
  return (
    <div className="w-64 text-[13px] leading-snug text-slate-700">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="font-semibold text-slate-900">
          {route.label} ·{' '}
          {checkpoint.index === 0
            ? 'Origin'
            : isEnd
              ? 'Destination'
              : `Mile ${checkpoint.distance_mi.toFixed(0)}`}
        </span>
        <span
          className="rounded px-1.5 py-0.5 text-[11px] font-semibold"
          style={{ background: style.tint, color: style.color }}
        >
          {style.label}
        </span>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
        <dt className="text-slate-500">ETA</dt>
        <dd className="font-medium tabular-nums text-slate-900">
          {formatDateTime(checkpoint.eta_utc, checkpoint.timezone)}
        </dd>
        {checkpoint.road && (
          <>
            <dt className="text-slate-500">Road</dt>
            <dd>{checkpoint.road}</dd>
          </>
        )}
        {weather ? (
          <>
            <dt className="text-slate-500">Wind</dt>
            <dd className="tabular-nums">
              {weather.wind_mph.toFixed(0)} mph
              {weather.gust_mph !== null && (
                <span className="text-slate-500"> · gusts {weather.gust_mph.toFixed(0)}</span>
              )}
            </dd>
            <dt className="text-slate-500">Rain</dt>
            <dd className="tabular-nums">{formatRate(weather.rain_in_hr)}</dd>
            <dt className="text-slate-500">Snow</dt>
            <dd className="tabular-nums">{formatRate(weather.snow_in_hr)}</dd>
          </>
        ) : (
          <dd className="col-span-2 text-slate-500">No forecast for this time and place.</dd>
        )}
        <dt className="text-slate-500">Covers</dt>
        <dd className="tabular-nums">
          {formatMiles(checkpoint.coverage_mi[0])} – {formatMiles(checkpoint.coverage_mi[1])}
        </dd>
      </dl>
      {risk && risk.score > 0 && (
        <ul className="mt-2 space-y-0.5 border-t border-slate-100 pt-2 text-[12px]">
          {checkpoint.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
          {risk.drivers.length > 0 && (
            <li className="text-slate-500">
              Driven by{' '}
              {risk.drivers
                .map((d) => CONDITION_LABEL[d])
                .join(' & ')
                .toLowerCase()}
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
