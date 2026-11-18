import { type FormEvent, useState } from 'react'
import { ApiError } from '../../api/client'
import type { Meta, Place, TripPlanRequest } from '../../api/types'
import { SegmentedControl } from '../../components/SegmentedControl'
import { Spinner } from '../../components/Spinner'
import { formatLbs } from '../../lib/format'
import { riskStyle } from '../../lib/risk'
import { nextHourInputValue, timeZoneAbbreviation, toLocalInputValue } from '../../lib/time'
import { EXAMPLE_TRIPS } from './examples'
import { PlaceInput } from './PlaceInput'

const DEFAULT_INTERVALS = [10, 25, 50]
const MAX_LOAD_LBS = 100_000

interface Props {
  meta: Meta | undefined
  submitting: boolean
  error: Error | null
  onSubmit: (request: TripPlanRequest) => void
}

export function TripForm({ meta, submitting, error, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departureMode, setDepartureMode] = useState<'now' | 'later'>('now')
  const [departureLocal, setDepartureLocal] = useState('')
  // Picker bounds are captured when scheduling starts; the server re-validates on submit.
  const [departureBounds, setDepartureBounds] = useState({ min: '', max: '' })
  const [load, setLoad] = useState('42000')
  const [interval, setSampleInterval] = useState(25)
  const [applyHos, setApplyHos] = useState(true)
  const [problem, setProblem] = useState<string | null>(null)

  const originTz = origin?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone
  const maxDays = meta?.max_departure_days ?? 7
  const loadLbs = Number(load)

  const chooseLater = () => {
    const now = Date.now()
    setDepartureMode('later')
    setDepartureBounds({
      min: toLocalInputValue(now, originTz),
      max: toLocalInputValue(now + maxDays * 86_400_000, originTz),
    })
    if (!departureLocal) setDepartureLocal(nextHourInputValue(now, originTz))
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!origin || !destination) return setProblem('Choose an origin and a destination from the suggestions.')
    if (origin.lat === destination.lat && origin.lon === destination.lon)
      return setProblem('Origin and destination must be different places.')
    if (!Number.isFinite(loadLbs) || loadLbs < 0 || loadLbs > MAX_LOAD_LBS)
      return setProblem(`Load weight must be between 0 and ${formatLbs(MAX_LOAD_LBS)}.`)
    if (departureMode === 'later' && !departureLocal) return setProblem('Pick a departure time.')
    setProblem(null)
    onSubmit({
      origin: { lat: origin.lat, lon: origin.lon, label: origin.label },
      destination: { lat: destination.lat, lon: destination.lon, label: destination.label },
      departure: departureMode === 'later' ? departureLocal : null,
      load_weight_lbs: loadLbs,
      sample_interval_mi: interval,
      apply_hos: applyHos,
    })
  }

  const serverMessages =
    error instanceof ApiError ? [error.message, ...error.fieldErrors] : error ? [error.message] : []
  const messages = problem ? [problem] : serverMessages

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="space-y-2.5">
        <PlaceInput
          label="Origin"
          placeholder="City, address or depot"
          value={origin}
          onChange={setOrigin}
          marker="origin"
        />
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setOrigin(destination)
              setDestination(origin)
            }}
            aria-label="Swap origin and destination"
            className="absolute -top-3 right-2 z-10 rounded-full border border-slate-200 bg-white p-1 text-slate-500 shadow-xs transition hover:text-slate-900"
          >
            <svg
              viewBox="0 0 16 16"
              className="size-3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              aria-hidden
            >
              <path
                d="M5 2v11M2 10l3 3 3-3M11 14V3M8 6l3-3 3 3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </button>
          <PlaceInput
            label="Destination"
            placeholder="City, address or depot"
            value={destination}
            onChange={setDestination}
            marker="destination"
          />
        </div>
        <div className="flex flex-wrap gap-1.5" aria-label="Example trips">
          {EXAMPLE_TRIPS.map((example) => (
            <button
              key={example.label}
              type="button"
              onClick={() => {
                setOrigin(example.origin)
                setDestination(example.destination)
              }}
              className="rounded-full border border-slate-200 px-2.5 py-0.5 text-xs text-slate-600 transition hover:border-slate-400 hover:text-slate-900"
            >
              {example.label}
            </button>
          ))}
        </div>
      </div>

      <fieldset className="space-y-1.5">
        <legend className="mb-1 text-xs font-medium text-slate-600">Departure</legend>
        <SegmentedControl
          label="Departure"
          value={departureMode}
          options={[
            { value: 'now', label: 'Leave now' },
            { value: 'later', label: 'Schedule' },
          ]}
          onChange={(mode) => (mode === 'later' ? chooseLater() : setDepartureMode('now'))}
        />
        {departureMode === 'later' && (
          <div>
            <input
              type="datetime-local"
              aria-label="Departure date and time"
              value={departureLocal}
              min={departureBounds.min}
              max={departureBounds.max}
              onChange={(e) => setDepartureLocal(e.target.value)}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm tabular-nums outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
            />
            <p className="mt-1 text-xs text-slate-500">
              Local time at the origin ({timeZoneAbbreviation(originTz)} · {originTz}), up to {maxDays} days
              ahead.
            </p>
          </div>
        )}
      </fieldset>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="load" className="mb-1 block text-xs font-medium text-slate-600">
            Load weight
          </label>
          <div className="relative">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_LOAD_LBS}
              step={500}
              value={load}
              onChange={(e) => setLoad(e.target.value)}
              className="w-full rounded-lg border border-slate-300 py-2 pr-8 pl-3 text-sm tabular-nums outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
            />
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-xs text-slate-500">
              lb
            </span>
          </div>
        </div>
        <div>
          <span className="mb-1 block text-xs font-medium text-slate-600">Sample weather every</span>
          <SegmentedControl
            label="Weather sampling interval"
            value={interval}
            options={(meta?.sample_intervals_mi ?? DEFAULT_INTERVALS).map((mi) => ({
              value: mi,
              label: `${mi} mi`,
            }))}
            onChange={setSampleInterval}
          />
        </div>
      </div>

      <LoadRuleHint meta={meta} loadLbs={loadLbs} />

      <label className="flex cursor-pointer items-start gap-2.5 text-sm">
        <input
          type="checkbox"
          checked={applyHos}
          onChange={(e) => setApplyHos(e.target.checked)}
          className="mt-0.5 size-4 accent-slate-900"
        />
        <span>
          <span className="font-medium text-slate-800">Hours-of-service stops in ETAs</span>
          <span className="block text-xs text-slate-500">
            30-min break after {meta?.hos.break_after_h ?? 8} h and a {meta?.hos.rest_h ?? 10}-h rest after{' '}
            {meta?.hos.max_driving_h ?? 11} h of driving (FMCSA).
          </span>
        </span>
      </label>

      {messages.length > 0 && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
        >
          {messages.map((m) => (
            <p key={m}>{m}</p>
          ))}
        </div>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 focus-visible:ring-2 focus-visible:ring-slate-900/30 focus-visible:ring-offset-2 disabled:cursor-progress disabled:bg-slate-700"
      >
        {submitting && <Spinner />}
        {submitting ? 'Planning routes & sampling forecasts…' : 'Plan routes'}
      </button>
    </form>
  )
}

function LoadRuleHint({ meta, loadLbs }: { meta: Meta | undefined; loadLbs: number }) {
  if (!meta || !Number.isFinite(loadLbs)) return null
  const wind = meta.conditions.wind.thresholds
  const bandText = (level: string) => {
    const i = wind.findIndex((t) => t.level === level)
    const next = wind[i + 1]
    return next ? `${wind[i].value}–${next.value - 1} mph` : `≥${wind[i].value} mph`
  }
  const active = meta.load_rules.filter((rule) => loadLbs > rule.load_over_lbs)
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
      {active.length === 0 ? (
        <p>No load rules apply at this weight; standard wind thresholds are used.</p>
      ) : (
        <>
          <p className="mb-0.5 font-medium text-slate-700">Load rules in effect at {formatLbs(loadLbs)}:</p>
          <ul className="space-y-0.5">
            {active.map((rule) => (
              <li key={rule.load_over_lbs}>
                Over {formatLbs(rule.load_over_lbs)}: wind {bandText(rule.wind_level)} is treated as{' '}
                <span className="font-semibold" style={{ color: riskStyle(rule.escalate_to).color }}>
                  {riskStyle(rule.escalate_to).label}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
