import type { FeatureCollection, LineString, Point } from 'geojson'
import { memo, useEffect, useMemo } from 'react'
import { Layer, Source, useMap } from 'react-map-gl/maplibre'
import { riskColorExpression } from '../../lib/risk'
import type { RouteModel } from '../../lib/routeModel'
import { useUiStore } from '../../store/ui'

export const ROUTE_HIT_LAYER = 'route-hit'
export const CHECKPOINT_LAYER = 'checkpoints'
const CHECKPOINT_SOURCE = 'checkpoints'

interface Props {
  models: RouteModel[]
  selectedId: string | null
}

/** All route lines; the selected one is drawn on top, coloured by checkpoint risk. */
export const RouteLayers = memo(function RouteLayers({ models, selectedId }: Props) {
  const lines = useMemo<FeatureCollection<LineString, { routeId: string; selected: boolean }>>(
    () => ({
      type: 'FeatureCollection',
      features: models.map(({ route, line }) => ({
        type: 'Feature',
        properties: { routeId: route.id, selected: route.id === selectedId },
        geometry: { type: 'LineString', coordinates: line.coords },
      })),
    }),
    [models, selectedId],
  )
  const selectedSegments = useMemo(
    () => models.find((m) => m.route.id === selectedId)?.riskSegments ?? emptyCollection,
    [models, selectedId],
  )

  return (
    <>
      <Source id="routes" type="geojson" data={lines}>
        <Layer
          id="route-alt-casing"
          type="line"
          filter={['!', ['get', 'selected']]}
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': '#ffffff', 'line-width': 7, 'line-opacity': 0.9 }}
        />
        <Layer
          id="route-alt"
          type="line"
          filter={['!', ['get', 'selected']]}
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': '#64748b', 'line-width': 4, 'line-opacity': 0.75 }}
        />
        <Layer
          id="route-selected-casing"
          type="line"
          filter={['get', 'selected']}
          layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': '#0f172a', 'line-width': 10, 'line-opacity': 0.85 }}
        />
        {/* Wide transparent line makes routes easy to hover and click. */}
        <Layer
          id={ROUTE_HIT_LAYER}
          type="line"
          paint={{ 'line-color': '#000000', 'line-width': 18, 'line-opacity': 0 }}
        />
      </Source>
      <Source id="route-risk" type="geojson" data={selectedSegments}>
        <Layer
          id="route-risk"
          type="line"
          layout={{ 'line-cap': 'butt', 'line-join': 'round' }}
          paint={{ 'line-color': riskColorExpression, 'line-width': 6 }}
        />
      </Source>
    </>
  )
})

type CheckpointProps = { routeId: string; level: string; selected: boolean; uid: number; index: number }

/** Checkpoint circles for every route (selected route emphasised); hover via feature-state. */
export const CheckpointLayer = memo(function CheckpointLayer({ models, selectedId }: Props) {
  const data = useMemo<FeatureCollection<Point, CheckpointProps>>(
    () => ({
      type: 'FeatureCollection',
      features: models.flatMap(({ route }, r) =>
        route.checkpoints.map((cp) => ({
          type: 'Feature',
          properties: {
            routeId: route.id,
            index: cp.index,
            uid: r * 100_000 + cp.index,
            level: cp.risk?.level ?? 'unknown',
            selected: route.id === selectedId,
          },
          geometry: { type: 'Point', coordinates: [cp.lon, cp.lat] },
        })),
      ),
    }),
    [models, selectedId],
  )
  useHoverFeatureState(models)

  return (
    <Source id={CHECKPOINT_SOURCE} type="geojson" data={data} promoteId="uid">
      <Layer
        id={CHECKPOINT_LAYER}
        type="circle"
        layout={{ 'circle-sort-key': ['case', ['get', 'selected'], 1, 0] }}
        paint={{
          'circle-color': riskColorExpression,
          // Zoom interpolation must be the outermost expression; per-feature cases go inside.
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            4,
            ['case', ['boolean', ['feature-state', 'hover'], false], 8, ['get', 'selected'], 4, 2.5],
            9,
            ['case', ['boolean', ['feature-state', 'hover'], false], 11, ['get', 'selected'], 7, 4],
          ],
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': ['case', ['get', 'selected'], 1.5, 0.75],
          'circle-opacity': ['case', ['get', 'selected'], 1, 0.55],
          'circle-stroke-opacity': ['case', ['get', 'selected'], 1, 0.55],
        }}
      />
    </Source>
  )
})

function useHoverFeatureState(models: RouteModel[]) {
  const { current: map } = useMap()
  const hovered = useUiStore((s) => s.hovered)
  useEffect(() => {
    if (!map || !hovered) return
    const r = models.findIndex((m) => m.route.id === hovered.routeId)
    if (r < 0) return
    const target = { source: CHECKPOINT_SOURCE, id: r * 100_000 + hovered.index }
    map.setFeatureState(target, { hover: true })
    return () => {
      if (map.getSource(CHECKPOINT_SOURCE)) map.setFeatureState(target, { hover: false })
    }
  }, [map, models, hovered])
}

const emptyCollection: FeatureCollection<LineString> = { type: 'FeatureCollection', features: [] }
