import type { HeatwaveResponse } from '@/types'

interface Props {
  result: HeatwaveResponse
  locationLabel: string
}

/** The plain-English summary: insights, how the threshold was set, data quality. */
export function SummaryCard({ result, locationLabel }: Props) {
  const { metadata, insights, events } = result
  const t = metadata.threshold
  const q = metadata.data_quality
  const loc = metadata.location

  const thresholdText =
    t.method === 'annual'
      ? `${t.mean_c.toFixed(1)} °C all year`
      : `${t.min_c.toFixed(1)}–${t.max_c.toFixed(1)} °C depending on the time of year`

  return (
    <section className="card summary">
      <h2>
        Heatwaves in {locationLabel}, {metadata.start_year}–{metadata.end_year}
      </h2>
      <ul className="insights">
        {insights.map((sentence) => <li key={sentence}>{sentence}</li>)}
      </ul>

      <dl className="facts">
        <div>
          <dt>Heatwave definition</dt>
          <dd>
            At least {metadata.min_duration} consecutive days with a daily maximum above the {t.percentile}th percentile
            of {t.baseline_start}–{t.baseline_end} ({thresholdText}).
          </dd>
        </div>
        <div>
          <dt>Events found</dt>
          <dd>{events.length}</dd>
        </div>
        <div>
          <dt>Data</dt>
          <dd>
            ERA5 grid cell at {loc.grid_lat.toFixed(2)}, {loc.grid_lon.toFixed(2)}
            {loc.elevation !== null && ` (${loc.elevation} m)`}. {dataQualityText(q)}
          </dd>
        </div>
      </dl>
      <p className="muted small">
        Source: {metadata.source}. ERA5 is a ~25 km reanalysis grid, not a weather station, so city-centre
        extremes can be higher than shown. {metadata.cached && 'Served from cache.'}
      </p>
    </section>
  )
}

function dataQualityText(q: HeatwaveResponse['metadata']['data_quality']): string {
  if (q.missing_raw_pct === 0 && q.impossible_values === 0) return 'No missing or invalid days.'
  const parts = [`${q.missing_raw_pct.toFixed(1)}% of days were missing`]
  if (q.impossible_values > 0) parts.push(`${q.impossible_values} impossible values were removed`)
  parts.push(`${q.filled_pct.toFixed(1)}% were filled by interpolating short gaps`)
  let text = parts.join(', ') + '.'
  if (q.low_quality_years.length > 0) text += ` Years with many gaps: ${q.low_quality_years.join(', ')}.`
  return text
}
