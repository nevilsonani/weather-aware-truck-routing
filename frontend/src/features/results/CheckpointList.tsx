import { useMemo, useState } from 'react'
import { useMap } from 'react-map-gl/maplibre'
import type { Checkpoint, RestStop, RoutePlan } from '../../api/types'
import { formatDateTime, formatDuration, formatShortDateTime, truncate } from '../../lib/format'
import { riskStyle } from '../../lib/risk'
import { useUiStore } from '../../store/ui'
import { MAP_ID } from '../map/constants'

type Item = { type: 'checkpoint'; checkpoint: Checkpoint } | { type: 'stop'; stop: RestStop }

export function CheckpointList({ route }: { route: RoutePlan }) {
  const maps = useMap()
  const hover = useUiStore((s) => s.hover)
  const hovered = useUiStore((s) => s.hovered)
  const [onlyRisky, setOnlyRisky] = useState(false)

  const items = useMemo<Item[]>(() => {
    const checkpoints: Item[] = route.checkpoints
      .filter((cp) => !onlyRisky || (cp.risk?.score ?? 1) > 0)
      .map((checkpoint) => ({ type: 'checkpoint', checkpoint }))
    const stops: Item[] = route.rest_stops.map((stop) => ({ type: 'stop', stop }))
    const mile = (item: Item) =>
      item.type === 'checkpoint' ? item.checkpoint.distance_mi : item.stop.distance_mi + 1e-6
    return [...checkpoints, ...stops].sort((a, b) => mile(a) - mile(b))
  }, [route, onlyRisky])

  const flyTo = (lon: number, lat: number) =>
    maps[MAP_ID]?.flyTo({
      center: [lon, lat],
      zoom: Math.max(maps[MAP_ID]?.getZoom() ?? 0, 8),
      duration: 700,
    })

  return (
    <section aria-label={`${route.label} checkpoints`}>
      <div className="mb-1.5 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {route.label} timeline · {route.checkpoints.length} checkpoints
        </h3>
        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={onlyRisky}
            onChange={(e) => setOnlyRisky(e.target.checked)}
            className="size-3.5 accent-slate-900"
          />
          Hide Low
        </label>
      </div>
      <ol
        className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white"
        onMouseLeave={() => hover(null)}
      >
        {items.length === 0 && (
          <li className="px-3 py-4 text-center text-sm text-slate-500">Every checkpoint is Low risk.</li>
        )}
        {items.map((item) =>
          item.type === 'stop' ? (
            <StopRow
              key={`stop-${item.stop.start_utc}`}
              stop={item.stop}
              timeZone={timeZoneNear(route, item.stop.distance_mi)}
              onClick={() => flyTo(item.stop.lon, item.stop.lat)}
            />
          ) : (
            <CheckpointRow
              key={item.checkpoint.index}
              checkpoint={item.checkpoint}
              last={item.checkpoint.index === route.checkpoints.length - 1}
              active={hovered?.routeId === route.id && hovered.index === item.checkpoint.index}
              onHover={() => hover({ routeId: route.id, index: item.checkpoint.index })}
              onClick={() => flyTo(item.checkpoint.lon, item.checkpoint.lat)}
            />
          ),
        )}
      </ol>
    </section>
  )
}

function CheckpointRow({
  checkpoint,
  last,
  active,
  onHover,
  onClick,
}: {
  checkpoint: Checkpoint
  last: boolean
  active: boolean
  onHover: () => void
  onClick: () => void
}) {
  const style = riskStyle(checkpoint.risk?.level)
  const w = checkpoint.weather
  const place =
    checkpoint.index === 0 ? 'Origin' : last ? 'Destination' : `Mile ${checkpoint.distance_mi.toFixed(0)}`
  return (
    <li className="checkpoint-row">
      <button
        type="button"
        onMouseEnter={onHover}
        onFocus={onHover}
        onClick={onClick}
        className={`grid w-full grid-cols-[10px_1fr_auto] items-center gap-x-2.5 px-3 py-1.5 text-left text-xs transition-colors ${
          active ? 'bg-slate-100' : 'hover:bg-slate-50'
        }`}
      >
        <span className="size-2.5 rounded-full" style={{ background: style.color }} aria-hidden />
        <span className="min-w-0">
          <span className="flex items-baseline gap-1.5">
            <span className="font-semibold text-slate-900">{place}</span>
            {checkpoint.road && <span className="truncate text-slate-500">{checkpoint.road}</span>}
          </span>
          <span className="block tabular-nums text-slate-500">
            {formatShortDateTime(checkpoint.eta_utc, checkpoint.timezone)}
            {w && (
              <span title="Wind (mph) · rain and snow (in/hr) at the ETA">
                {' · '}
                {truncate(w.wind_mph, 0)} mph · rain {truncate(w.rain_in_hr, 2)} · snow{' '}
                {truncate(w.snow_in_hr, 2)}
              </span>
            )}
          </span>
        </span>
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
          style={{ background: style.tint, color: style.color }}
        >
          {style.label}
        </span>
      </button>
    </li>
  )
}

/** Rest stops are shown in the local time of the nearest checkpoint. */
function timeZoneNear(route: RoutePlan, mile: number): string {
  let best = route.checkpoints[0]
  for (const cp of route.checkpoints) {
    if (Math.abs(cp.distance_mi - mile) < Math.abs(best.distance_mi - mile)) best = cp
  }
  return best.timezone
}

function StopRow({ stop, timeZone, onClick }: { stop: RestStop; timeZone: string; onClick: () => void }) {
  const duration = (Date.parse(stop.end_utc) - Date.parse(stop.start_utc)) / 1000
  return (
    <li className="checkpoint-row">
      <button
        type="button"
        onClick={onClick}
        className="grid w-full grid-cols-[10px_1fr] items-center gap-x-2.5 bg-slate-50/70 px-3 py-1.5 text-left text-xs text-slate-600 hover:bg-slate-100"
      >
        <span className="size-2.5 rounded-sm border-2 border-slate-700" aria-hidden />
        <span>
          <span className="font-semibold text-slate-800">
            {stop.kind === 'rest' ? 'Off-duty rest' : 'Required break'} · {formatDuration(duration)}
          </span>{' '}
          near mile {stop.distance_mi.toFixed(0)} · resumes {formatDateTime(stop.end_utc, timeZone)}
        </span>
      </button>
    </li>
  )
}
