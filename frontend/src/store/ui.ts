import { create } from 'zustand'
import type { HeatmapMetric } from '../api/types'

export interface HoveredCheckpoint {
  routeId: string
  index: number
}

interface UiState {
  selectedRouteId: string | null
  hovered: HoveredCheckpoint | null
  heatmapMetric: HeatmapMetric | 'off'
  /** Hours after departure shown by the forecast slider (fractional while scrubbing/playing). */
  hour: number
  playing: boolean
  selectRoute: (id: string) => void
  hover: (checkpoint: HoveredCheckpoint | null) => void
  setHeatmapMetric: (metric: HeatmapMetric | 'off') => void
  setHour: (hour: number) => void
  setPlaying: (playing: boolean) => void
  resetForPlan: (recommendedRouteId: string) => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedRouteId: null,
  hovered: null,
  heatmapMetric: 'risk',
  hour: 0,
  playing: false,
  selectRoute: (id) => set({ selectedRouteId: id }),
  hover: (hovered) => set({ hovered }),
  setHeatmapMetric: (heatmapMetric) => set({ heatmapMetric }),
  setHour: (hour) => set({ hour }),
  setPlaying: (playing) => set({ playing }),
  resetForPlan: (id) => set({ selectedRouteId: id, hovered: null, hour: 0, playing: false }),
}))
