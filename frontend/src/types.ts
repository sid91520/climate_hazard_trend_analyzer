// Mirrors backend/app/schemas.py. Keep the two in sync when the API changes.

export type Method = 'doy' | 'annual'

export type Selection =
  | { kind: 'point'; lat: number; lon: number; label: string }
  | { kind: 'box'; minLat: number; maxLat: number; minLon: number; maxLon: number; label: string }

export interface AnalysisParams {
  selection: Selection
  startYear: number
  endYear: number
  percentile: number
  minDuration: number
  method: Method
}

export interface Place {
  name: string
  country: string | null
  admin1: string | null
  lat: number
  lon: number
}

export interface YearlyMetrics {
  year: number
  events: number
  heatwave_days: number
  longest_event: number
  mean_intensity: number | null
  max_tmax: number | null
  missing_pct: number
  filled_pct: number
  events_rolling: number | null
  heatwave_days_rolling: number | null
  longest_event_rolling: number | null
  mean_intensity_rolling: number | null
  max_tmax_rolling: number | null
}

export type MetricKey = 'events' | 'heatwave_days' | 'longest_event' | 'mean_intensity' | 'max_tmax'

export interface HeatwaveEvent {
  start: string
  end: string
  duration: number
  peak_temp: number
  mean_excess: number
}

export interface MetricTrend {
  linear: { slope_per_decade: number; intercept: number; p_value: number; r_squared: number } | null
  mann_kendall: { trend: string; p_value: number; tau: number; sens_slope_per_decade: number } | null
  significant: boolean
}

export interface HeatwaveResponse {
  metadata: {
    hazard: 'heatwave'
    location: {
      lat: number
      lon: number
      grid_lat: number
      grid_lon: number
      elevation: number | null
      timezone: string
      bbox: number[] | null
    }
    start_year: number
    end_year: number
    min_duration: number
    threshold: {
      method: Method
      percentile: number
      baseline_start: number
      baseline_end: number
      min_c: number
      mean_c: number
      max_c: number
    }
    data_quality: {
      missing_raw_pct: number
      filled_pct: number
      missing_after_cleaning_pct: number
      impossible_values: number
      low_quality_years: number[]
    }
    source: string
    analysis_version: string
    generated_at: string
    cached: boolean
  }
  yearly: YearlyMetrics[]
  events: HeatwaveEvent[]
  trends: Record<MetricKey, MetricTrend>
  insights: string[]
}
