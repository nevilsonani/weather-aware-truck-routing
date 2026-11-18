import { useEffect, useMemo } from 'react'
import type { Heatmap, HeatmapMetric, Meta, TripPlan } from '../../api/types'
import { SegmentedControl } from '../../components/SegmentedControl'
import { Spinner } from '../../components/Spinner'
import { formatDateTime } from '../../lib/format'
import { riskStyle } from '../../lib/risk'
import { type RouteModel, truckStateAt } from '../../lib/routeModel'
import { useUiStore } from '../../store/ui'
import { type ColorScale, buildScale } from './colorScales'

const PLAYBACK_HOURS_PER_SECOND = 4
const METRICS: ReadonlyArray<{ value: HeatmapMetric | 'off'; label: string }> = [
  { value: 'risk', label: 'Risk' },
  { value: 'wind', label: 'Wind' },
  { value: 'rain', label: 'Rain' },
  { value: 'snow', label: 'Snow' },
  { value: 'off', label: 'Off' },
]
const ACTIVITY_LABEL = {
  waiting: 'not departed',
  driving: 'driving',
  break: 'on 30-min break',
  rest: 'on 10-hr rest',
  arrived: 'arrived',
} as const

interface Props {
  plan: TripPlan | undefined
  models: RouteModel[]
  meta: Meta | undefined
  heatmap: Heatmap | undefined
  loading: boolean
  error: Error | null
}

export function HeatmapControls({ plan, models, meta, heatmap, loading, error }: Props) {
  const metric = useUiStore((s) => s.heatmapMetric)
  const setMetric = useUiStore((s) => s.setHeatmapMetric)
  const hour = useUiStore((s) => s.hour)
  const setHour = useUiStore((s) => s.setHour)
  const playing = useUiStore((s) => s.playing)
  const setPlaying = useUiStore((s) => s.setPlaying)
  const selectedId = useUiStore((s) => s.selectedRouteId)
  const hours = meta?.heatmap_hours ?? 48
  usePlayback(playing, hours)

  const scale = useMemo(() => (meta && metric !== 'off' ? buildScale(metric, meta) : null), [meta, metric])
  const disabled = !plan
  const departureMs = plan ? Date.parse(plan.trip.departure_utc) : 0
  const timeZone = plan?.trip.origin.timezone ?? 'UTC'
  const selected = models.find((m) => m.route.id === selectedId)
  const truck = selected ? truckStateAt(selected, hour * 3600) : null
  const arrivalHour = selected ? selected.route.total_time_s / 3600 : null

  return (
    <section
      aria-label="Corridor weather forecast"
      className="pointer-events-auto w-full max-w-3xl rounded-xl border border-slate-200/80 bg-white/95 p-2 shadow-lg backdrop-blur sm:p-3"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <SegmentedControl
          label="Heat-map layer"
          size="sm"
          value={metric}
          options={METRICS}
          onChange={setMetric}
          disabled={disabled}
        />
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-600" aria-live="polite">
          {loading && (
            <>
              <Spinner className="size-3.5" /> Loading corridor forecast…
            </>
          )}
          {error && !loading && (
            <span className="text-red-600">Forecast layer unavailable: {error.message}</span>
          )}
          {plan && !loading && !error && (
            <span className="font-medium tabular-nums text-slate-900">
              {formatDateTime(departureMs + hour * 3_600_000, timeZone)}
              <span className="ml-1.5 font-normal text-slate-500">
                departure +{hour.toFixed(hour % 1 ? 1 : 0)} h
              </span>
            </span>
          )}
        </div>
      </div>

      <div className="mt-2 flex items-center gap-3">
        <button
          type="button"
          disabled={disabled || !heatmap}
          onClick={() => {
            if (!playing && hour >= hours) setHour(0)
            setPlaying(!playing)
          }}
          aria-label={playing ? 'Pause forecast animation' : 'Play forecast animation'}
          className="flex size-8 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-slate-700 disabled:bg-slate-300"
        >
          {playing ? (
            <svg viewBox="0 0 16 16" className="size-3.5" fill="currentColor" aria-hidden>
              <rect x="3" y="2" width="3.5" height="12" rx="1" />
              <rect x="9.5" y="2" width="3.5" height="12" rx="1" />
            </svg>
          ) : (
            <svg viewBox="0 0 16 16" className="ml-0.5 size-3.5" fill="currentColor" aria-hidden>
              <path d="M4 2.5v11a1 1 0 0 0 1.5.86l9-5.5a1 1 0 0 0 0-1.72l-9-5.5A1 1 0 0 0 4 2.5Z" />
            </svg>
          )}
        </button>
        <div className="relative flex-1">
          <input
            type="range"
            min={0}
            max={hours}
            step={0.25}
            value={hour}
            disabled={disabled}
            onChange={(e) => {
              setPlaying(false)
              setHour(Number(e.target.value))
            }}
            aria-label="Hours after departure"
            aria-valuetext={`${hour.toFixed(1)} hours after departure`}
            className="forecast-slider w-full"
          />
          <div className="pointer-events-none relative mt-0.5 h-3 text-[10px] tabular-nums text-slate-400">
            {Array.from({ length: hours / 6 + 1 }, (_, i) => i * 6).map((h) => (
              <span key={h} className="absolute -translate-x-1/2" style={{ left: `${(h / hours) * 100}%` }}>
                {h}h
              </span>
            ))}
            {arrivalHour !== null && arrivalHour <= hours && (
              <span
                className="absolute -top-5 -translate-x-1/2 text-[10px] font-semibold text-slate-700"
                style={{ left: `${(arrivalHour / hours) * 100}%` }}
                title="Selected route arrives"
              >
                ▼
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-2 hidden flex-wrap items-center justify-between gap-2 sm:flex">
        {scale ? (
          <ColorRamp scale={scale} />
        ) : (
          <span className="text-xs text-slate-500">Heat map hidden</span>
        )}
        {truck && selected && (
          <p className="text-xs text-slate-600">
            <span className="font-semibold text-slate-900">{selected.route.label} truck</span> · mile{' '}
            <span className="tabular-nums">{truck.mile.toFixed(0)}</span> · {ACTIVITY_LABEL[truck.activity]}
          </p>
        )}
      </div>
    </section>
  )
}

function ColorRamp({ scale }: { scale: ColorScale }) {
  const gradient = scale.stops
    .map(
      (s) =>
        `color-mix(in srgb, ${s.color} ${Math.round(Math.max(s.alpha, 0.05) * 140)}%, white) ${(s.value / scale.max) * 100}%`,
    )
    .join(', ')
  return (
    <div className="min-w-56 flex-1">
      <div className="mb-0.5 flex justify-between text-[10px] text-slate-500">
        <span className="font-medium text-slate-700">
          {scale.label}
          {scale.unit && ` (${scale.unit})`}
        </span>
        {scale.metric === 'risk' && <span>includes load rules</span>}
      </div>
      <div
        className="relative h-2 rounded-full"
        style={{ background: `linear-gradient(to right, ${gradient})` }}
      />
      <div className="relative h-3 text-[10px] tabular-nums text-slate-500">
        {scale.ticks.map((tick, i) => {
          const edge = i === 0 && tick.value === 0 ? 'start' : tick.value >= scale.max ? 'end' : 'middle'
          return (
            <span
              key={tick.value}
              className={`absolute whitespace-nowrap ${
                edge === 'start' ? '' : edge === 'end' ? '-translate-x-full' : '-translate-x-1/2'
              }`}
              style={{ left: `${(tick.value / scale.max) * 100}%` }}
            >
              {scale.metric === 'risk' ? riskStyle(tick.level).label : tick.value}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/** Advances the forecast hour with requestAnimationFrame while playing. */
function usePlayback(playing: boolean, hours: number) {
  useEffect(() => {
    if (!playing) return
    const { setHour, setPlaying } = useUiStore.getState()
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    let frame = 0
    let last = performance.now()
    const tick = (now: number) => {
      const elapsed = (now - last) / 1000
      if (reducedMotion && elapsed < 0.5) {
        frame = requestAnimationFrame(tick)
        return
      }
      last = now
      const current = useUiStore.getState().hour
      const next = reducedMotion ? Math.floor(current) + 1 : current + elapsed * PLAYBACK_HOURS_PER_SECOND
      if (next >= hours) {
        setHour(hours)
        setPlaying(false)
        return
      }
      setHour(next)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, hours])
}
