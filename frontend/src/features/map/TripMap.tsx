import 'maplibre-gl/dist/maplibre-gl.css'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Map, {
  type MapLayerMouseEvent,
  type MapRef,
  NavigationControl,
  Popup,
  ScaleControl,
} from 'react-map-gl/maplibre'
import type { Heatmap, Meta, TripPlan } from '../../api/types'
import { config } from '../../config'
import { type RouteModel, boundsOf } from '../../lib/routeModel'
import { useUiStore } from '../../store/ui'
import { CheckpointTooltip } from './CheckpointTooltip'
import { MAP_ID } from './constants'
import { HeatmapLayer } from './HeatmapLayer'
import { maplibregl } from './maplibre'
import { EndpointMarkers, RestStopMarkers, RouteLabels, TruckMarkers } from './Markers'
import { CHECKPOINT_LAYER, CheckpointLayer, ROUTE_HIT_LAYER, RouteLayers } from './RouteLayers'

const INTERACTIVE_LAYERS = [CHECKPOINT_LAYER, ROUTE_HIT_LAYER]

interface Props {
  plan: TripPlan | undefined
  models: RouteModel[]
  heatmap: Heatmap | undefined
  meta: Meta | undefined
}

export default function TripMap({ plan, models, heatmap, meta }: Props) {
  const mapRef = useRef<MapRef>(null)
  const [cursor, setCursor] = useState('')
  const selectedId = useUiStore((s) => s.selectedRouteId)
  const hovered = useUiStore((s) => s.hovered)
  const metric = useUiStore((s) => s.heatmapMetric)
  const hover = useUiStore((s) => s.hover)
  const selectRoute = useUiStore((s) => s.selectRoute)

  useEffect(() => {
    const bounds = boundsOf(models)
    const map = mapRef.current
    if (!bounds || !map) return
    // Leave room for the floating forecast panel, scaled to the map's size (mobile vs desktop).
    const { clientWidth: width, clientHeight: height } = map.getContainer()
    const side = Math.min(70, width * 0.08)
    map.fitBounds(bounds, {
      padding: { top: side, left: side, right: side, bottom: Math.min(190, height * 0.42) },
      duration: 900,
      maxZoom: 10,
    })
  }, [models])

  const onMouseMove = useCallback(
    (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0]
      const current = useUiStore.getState().hovered
      if (feature?.layer.id === CHECKPOINT_LAYER) {
        const { routeId, index } = feature.properties as { routeId: string; index: number }
        if (current?.routeId !== routeId || current.index !== index) hover({ routeId, index })
      } else if (current) {
        hover(null)
      }
      setCursor(feature ? 'pointer' : '')
    },
    [hover],
  )

  const onClick = useCallback(
    (event: MapLayerMouseEvent) => {
      const routeId = event.features?.[0]?.properties?.routeId as string | undefined
      if (routeId) selectRoute(routeId)
    },
    [selectRoute],
  )

  const routeLines = useMemo(() => models.map((m) => m.line.coords), [models])
  const hoveredModel = hovered ? models.find((m) => m.route.id === hovered.routeId) : undefined
  const hoveredCheckpoint = hovered ? hoveredModel?.route.checkpoints[hovered.index] : undefined
  const selectedModel = models.find((m) => m.route.id === selectedId)

  return (
    <Map
      id={MAP_ID}
      ref={mapRef}
      mapLib={maplibregl}
      mapStyle={config.mapStyleUrl}
      initialViewState={{ longitude: -98.5, latitude: 39.5, zoom: 3.6 }}
      interactiveLayerIds={INTERACTIVE_LAYERS}
      onMouseMove={onMouseMove}
      onMouseLeave={() => {
        hover(null)
        setCursor('')
      }}
      onClick={onClick}
      cursor={cursor}
      dragRotate={false}
      touchPitch={false}
      attributionControl={{ compact: true }}
    >
      <NavigationControl position="top-right" showCompass={false} />
      <ScaleControl position="bottom-right" unit="imperial" />
      {plan && heatmap && meta && metric !== 'off' && (
        <HeatmapLayer
          heatmap={heatmap}
          metric={metric}
          meta={meta}
          departureMs={Date.parse(plan.trip.departure_utc)}
          routes={routeLines}
          bufferMiles={plan.corridor.buffer_mi ?? 0}
        />
      )}
      {plan && (
        <>
          <RouteLayers models={models} selectedId={selectedId} />
          <CheckpointLayer models={models} selectedId={selectedId} />
          <EndpointMarkers plan={plan} />
          <RestStopMarkers model={selectedModel} timeZone={plan.trip.origin.timezone} />
          <TruckMarkers models={models} selectedId={selectedId} />
          <RouteLabels models={models} selectedId={selectedId} />
        </>
      )}
      {hoveredModel && hoveredCheckpoint && (
        <Popup
          longitude={hoveredCheckpoint.lon}
          latitude={hoveredCheckpoint.lat}
          closeButton={false}
          closeOnClick={false}
          offset={12} // no fixed anchor: MapLibre flips the popup to stay inside the map
          maxWidth="none"
          className="checkpoint-popup"
        >
          <CheckpointTooltip route={hoveredModel.route} checkpoint={hoveredCheckpoint} />
        </Popup>
      )}
    </Map>
  )
}
