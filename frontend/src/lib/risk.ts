import type { RiskLevel } from '../api/types'

export interface RiskStyle {
  key: RiskLevel
  label: string
  score: number
  /** Solid colour for markers, lines and chips. */
  color: string
  /** Soft background for badges. */
  tint: string
}

/** Ordered Low → No Travel. Colours follow common hazard conventions; purple = prohibitive. */
export const RISK_LEVELS: readonly RiskStyle[] = [
  { key: 'low', label: 'Low', score: 0, color: '#16a34a', tint: '#dcfce7' },
  { key: 'moderate', label: 'Moderate', score: 1, color: '#d4a106', tint: '#fef9c3' },
  { key: 'high', label: 'High', score: 2, color: '#ea580c', tint: '#ffedd5' },
  { key: 'severe', label: 'Severe', score: 3, color: '#dc2626', tint: '#fee2e2' },
  { key: 'no_travel', label: 'No Travel', score: 4, color: '#9333ea', tint: '#f3e8ff' },
]

export const UNKNOWN_STYLE = { label: 'No data', color: '#94a3b8', tint: '#f1f5f9' } as const

const byKey = new Map(RISK_LEVELS.map((level) => [level.key, level]))

export function riskStyle(level: RiskLevel | null | undefined): RiskStyle | typeof UNKNOWN_STYLE {
  return (level && byKey.get(level)) || UNKNOWN_STYLE
}

/** MapLibre `match` expression colouring features by their `level` property. */
export const riskColorExpression = [
  'match',
  ['get', 'level'],
  ...RISK_LEVELS.flatMap((level) => [level.key, level.color]),
  UNKNOWN_STYLE.color,
] as unknown as string
