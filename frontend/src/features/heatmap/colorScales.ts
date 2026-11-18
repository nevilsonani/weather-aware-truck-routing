import type { HeatmapMetric, Meta, RiskLevel } from '../../api/types'
import { RISK_LEVELS } from '../../lib/risk'

export interface ColorStop {
  value: number
  color: string
  alpha: number
}

export interface ColorScale {
  metric: HeatmapMetric
  label: string
  unit: string
  /** Values are clamped to [0, max] before lookup. */
  max: number
  stops: ColorStop[]
  /** Legend ticks (threshold values), each with the risk level it starts. */
  ticks: Array<{ value: number; level: RiskLevel }>
}

const ALPHA: Record<RiskLevel, number> = {
  low: 0.13,
  moderate: 0.42,
  high: 0.52,
  severe: 0.6,
  no_travel: 0.68,
}
const riskColor = (level: RiskLevel) => RISK_LEVELS.find((l) => l.key === level)!.color

/**
 * Colour ramps are anchored on the backend's risk thresholds, so a cell drawn orange in the
 * Rain layer is rain that alone reaches the High band. Below the Moderate threshold a neutral
 * tint shows weather that exists but carries little risk.
 */
export function buildScale(metric: HeatmapMetric, meta: Meta): ColorScale {
  if (metric === 'risk') {
    return {
      metric,
      label: 'Load-adjusted risk',
      unit: '',
      max: 4,
      stops: RISK_LEVELS.map((l) => ({ value: l.score, color: l.color, alpha: ALPHA[l.key] })),
      ticks: RISK_LEVELS.map((l) => ({ value: l.score, level: l.key })),
    }
  }
  const condition = meta.conditions[metric]
  const thresholds = condition.thresholds
  const first = thresholds[0].value
  const last = thresholds[thresholds.length - 1].value
  const tint = { wind: '#64748b', rain: '#0ea5e9', snow: '#818cf8' }[metric]
  return {
    metric,
    label: {
      wind: meta.wind_basis === 'gust' ? 'Wind gusts' : 'Wind speed',
      rain: 'Rain rate',
      snow: 'Snowfall rate',
    }[metric],
    unit: condition.unit,
    max: last * 1.3,
    stops: [
      { value: 0, color: tint, alpha: 0 },
      { value: first * 0.15, color: tint, alpha: 0.12 },
      { value: first * 0.999, color: tint, alpha: 0.3 },
      ...thresholds.map((t) => ({ value: t.value, color: riskColor(t.level), alpha: ALPHA[t.level] })),
    ],
    ticks: thresholds.map((t) => ({ value: t.value, level: t.level })),
  }
}

function hexToRgb(hex: string): [number, number, number] {
  const n = Number.parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** 1024-entry RGBA lookup table (premultiplication is left to the GPU). */
export function buildLut(scale: ColorScale, size = 1024): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(size * 4)
  const stops = scale.stops.map((s) => ({ ...s, rgb: hexToRgb(s.color) }))
  for (let i = 0; i < size; i++) {
    const value = (i / (size - 1)) * scale.max
    let k = 0
    while (k < stops.length - 2 && value > stops[k + 1].value) k++
    const a = stops[k]
    const b = stops[Math.min(k + 1, stops.length - 1)]
    const span = b.value - a.value
    const t = span > 0 ? Math.min(1, Math.max(0, (value - a.value) / span)) : 1
    for (let c = 0; c < 3; c++) lut[i * 4 + c] = a.rgb[c] + t * (b.rgb[c] - a.rgb[c])
    lut[i * 4 + 3] = 255 * (a.alpha + t * (b.alpha - a.alpha))
  }
  return lut
}
