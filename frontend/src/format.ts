import type { MetricTrend, Place } from './types'

/** "Mumbai, Maharashtra, India" */
export function placeLabel(place: Place): string {
  return [place.name, place.admin1, place.country].filter(Boolean).join(', ')
}

export function formatP(p: number): string {
  return p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`
}

/** One-line trend summary shown under each chart title. */
export function describeTrend(trend: MetricTrend, unit: string): string {
  const mk = trend.mann_kendall
  if (!mk) return 'Too few years with heatwaves to test for a trend.'
  const slope = mk.sens_slope_per_decade
  const verdict = trend.significant ? 'statistically significant' : 'not statistically significant'
  return `Trend ${slope >= 0 ? '+' : ''}${slope.toFixed(2)} ${unit} per decade (Sen's slope) · Mann-Kendall ${formatP(mk.p_value)}, ${verdict}`
}
