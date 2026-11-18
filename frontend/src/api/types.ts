/** API contract types. Mirrors backend `api/presenters.py`; every key states its unit. */

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'
export type HeatmapMetric = 'risk' | 'wind' | 'rain' | 'snow'
export type RecommendationStatus = 'clear' | 'caution' | 'no_safe_route' | 'insufficient_data'

export interface Place {
  id: string
  name: string
  label: string
  lat: number
  lon: number
  kind: string
  country_code: string | null
  timezone: string
}

export interface TripEndpoint {
  lat: number
  lon: number
  label: string
}

export interface TripPlanRequest {
  origin: TripEndpoint
  destination: TripEndpoint
  /** ISO-8601; naive = wall-clock time at the origin. Omitted = leave now. */
  departure?: string | null
  load_weight_lbs: number
  sample_interval_mi: number
  apply_hos: boolean
}

export interface CheckpointWeather {
  wind_mph: number
  gust_mph: number | null
  rain_in_hr: number
  snow_in_hr: number
}

export interface CheckpointRisk {
  level: RiskLevel
  score: number
  wind: RiskLevel
  rain: RiskLevel
  snow: RiskLevel
  load_escalated: boolean
  drivers: Array<'wind' | 'rain' | 'snow'>
}

export interface Checkpoint {
  index: number
  distance_mi: number
  lat: number
  lon: number
  road: string | null
  eta_utc: string
  elapsed_s: number
  timezone: string
  coverage_mi: [number, number]
  weather: CheckpointWeather | null
  risk: CheckpointRisk | null
  reasons: string[]
}

export interface RestStop {
  kind: 'break' | 'rest'
  start_utc: string
  end_utc: string
  distance_mi: number
  lat: number
  lon: number
}

export interface RouteSummary {
  miles_by_level: Record<RiskLevel | 'unknown', number>
  average_risk: number | null
  max_level: RiskLevel | null
  checkpoint_count: number
}

export interface RoutePlan {
  id: string
  label: string
  name: string
  rank: number
  recommended: boolean
  not_recommended_because: { criterion: string | null; text: string } | null
  distance_mi: number
  driving_time_s: number
  stop_time_s: number
  total_time_s: number
  departure_utc: string
  arrival_utc: string
  arrival_timezone: string
  /** Encoded polyline, precision 6. */
  geometry: string
  summary: RouteSummary
  checkpoints: Checkpoint[]
  rest_stops: RestStop[]
  /** Knots of [elapsed seconds since departure, miles driven]; non-decreasing. */
  timeline: Array<[number, number]>
  notices: string[]
}

export interface CorridorGrid {
  west: number
  east: number
  south: number
  north: number
  nx: number
  ny: number
  /** Row-major cell indices inside the corridor; row 0 is the northern edge. */
  cells: number[]
  /** Corridor half-width (plan responses only). */
  buffer_mi?: number
}

export interface TripPlan {
  trip: {
    origin: TripEndpoint & { timezone: string }
    destination: TripEndpoint & { timezone: string }
    departure_utc: string
    load_weight_lbs: number
    gross_weight_lbs: number
    sample_interval_mi: number
    apply_hos: boolean
    provider: string
  }
  recommendation: {
    route_id: string
    status: RecommendationStatus
    headline: string
    ranking: string[]
    reasons: string[]
    criteria: string[]
  }
  routes: RoutePlan[]
  corridor: CorridorGrid
  warnings: string[]
  generated_at: string
}

export interface Heatmap {
  start_utc: string
  departure_utc: string
  step_s: number
  frame_count: number
  hours: number
  grid: CorridorGrid
  layers: {
    risk: number[][]
    wind_mph: Array<Array<number | null>>
    rain_in_hr: Array<Array<number | null>>
    snow_in_hr: Array<Array<number | null>>
  }
  warnings: string[]
}

export interface Threshold {
  level: RiskLevel
  value: number
  inclusive: boolean
}

export interface Meta {
  risk_levels: Array<{ key: RiskLevel; label: string; score: number }>
  conditions: Record<'wind' | 'rain' | 'snow', { unit: string; thresholds: Threshold[] }>
  load_rules: Array<{ wind_level: RiskLevel; load_over_lbs: number; escalate_to: RiskLevel }>
  wind_basis: 'sustained' | 'gust'
  ranking_criteria: string[]
  sample_intervals_mi: number[]
  max_departure_days: number
  truck_tare_weight_lbs: number
  heatmap_hours: number
  hos: { max_driving_h: number; break_after_h: number; break_min: number; rest_h: number }
}

export interface ApiErrorBody {
  error: { code: string; message: string; details: Record<string, unknown> }
}
