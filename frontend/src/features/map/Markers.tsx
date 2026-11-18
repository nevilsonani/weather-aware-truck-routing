import { memo } from 'react'
import { Marker } from 'react-map-gl/maplibre'
import type { TripPlan } from '../../api/types'
import { formatDateTime } from '../../lib/format'
import { type RouteModel, truckStateAt } from '../../lib/routeModel'
import { useUiStore } from '../../store/ui'

export const EndpointMarkers = memo(function EndpointMarkers({ plan }: { plan: TripPlan }) {
  const { origin, destination } = plan.trip
  return (
    <>
      <Marker longitude={origin.lon} latitude={origin.lat} anchor="center">
        <div
          title={`Origin: ${origin.label}`}
          className="size-4 rounded-full border-[3px] border-white bg-slate-900 shadow-md ring-1 ring-slate-900/30"
        />
      </Marker>
      <Marker longitude={destination.lon} latitude={destination.lat} anchor="center">
        <div
          title={`Destination: ${destination.label}`}
          className="size-4 rotate-45 border-[3px] border-white bg-slate-900 shadow-md ring-1 ring-slate-900/30"
        />
      </Marker>
    </>
  )
})

export const RouteLabels = memo(function RouteLabels({
  models,
  selectedId,
}: {
  models: RouteModel[]
  selectedId: string | null
}) {
  const selectRoute = useUiStore((s) => s.selectRoute)
  return models.map(({ route, labelAt }) => {
    const selected = route.id === selectedId
    return (
      <Marker key={route.id} longitude={labelAt[0]} latitude={labelAt[1]} anchor="center">
        <button
          type="button"
          onClick={() => selectRoute(route.id)}
          aria-label={`Select ${route.label}`}
          className={`flex h-6 min-w-6 items-center justify-center gap-0.5 rounded-full px-1.5 text-xs font-bold shadow-md ring-2 ring-white transition-colors ${
            selected ? 'bg-slate-900 text-white' : 'bg-white text-slate-700 hover:bg-slate-100'
          }`}
        >
          {route.id}
          {route.recommended && <span className="text-amber-400">★</span>}
        </button>
      </Marker>
    )
  })
})

export const RestStopMarkers = memo(function RestStopMarkers({
  model,
  timeZone,
}: {
  model: RouteModel | undefined
  timeZone: string
}) {
  if (!model) return null
  return model.route.rest_stops.map((stop) => (
    <Marker key={stop.start_utc} longitude={stop.lon} latitude={stop.lat} anchor="center">
      <div
        title={`${stop.kind === 'rest' ? '10-hour rest' : '30-minute break'} · ${formatDateTime(stop.start_utc, timeZone)}`}
        className="flex size-5 items-center justify-center rounded-md border-2 border-slate-900 bg-white text-[10px] font-bold text-slate-900 shadow"
      >
        {stop.kind === 'rest' ? 'R' : 'B'}
      </div>
    </Marker>
  ))
})

/** Truck positions at the forecast slider's time; re-renders only these markers. */
export function TruckMarkers({ models, selectedId }: { models: RouteModel[]; selectedId: string | null }) {
  const hour = useUiStore((s) => s.hour)
  return models.map((model) => {
    const state = truckStateAt(model, hour * 3600)
    const selected = model.route.id === selectedId
    const paused = state.activity === 'break' || state.activity === 'rest'
    return (
      <Marker
        key={model.route.id}
        longitude={state.position[0]}
        latitude={state.position[1]}
        anchor="center"
        style={{ zIndex: selected ? 3 : 2 }}
      >
        <div
          title={`${model.route.label} truck · mile ${state.mile.toFixed(0)} · ${state.activity}`}
          className={`flex items-center justify-center rounded-full border-2 border-white font-bold text-white shadow-lg ${
            selected ? 'size-7 text-[11px]' : 'size-5 text-[9px] opacity-80'
          } ${paused ? 'bg-amber-600' : 'bg-blue-600'}`}
        >
          {model.route.id}
        </div>
      </Marker>
    )
  })
}
