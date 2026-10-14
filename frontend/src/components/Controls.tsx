import { useState } from 'react'
import dynamic from 'next/dynamic'
import type { AnalysisParams, Method, Selection } from '@/types'
import { placeLabel } from '@/format'
import { LocationSearch } from './LocationSearch'

// Leaflet touches `window` as soon as it is imported, which breaks Next.js's server
// render. ssr: false loads the map only in the browser.
const MapPicker = dynamic(() => import('./MapPicker').then((m) => m.MapPicker), {
  ssr: false,
  loading: () => <div className="map map-loading">Loading map…</div>,
})

// Same limits as backend/app/schemas.py, checked here too so users get instant feedback.
export const FIRST_YEAR = 1940
export const LAST_YEAR = new Date().getFullYear() - 1 // last full year in the archive
const MIN_RANGE = 10
const MAX_RANGE = 85

// Only heatwave is implemented; the others show the design is ready to grow.
const HAZARDS = [
  { id: 'heatwave', label: 'Heatwave', available: true },
  { id: 'drought', label: 'Drought (coming soon)', available: false },
  { id: 'heavy_rain', label: 'Heavy rain (coming soon)', available: false },
]

interface Props {
  loading: boolean
  onSubmit: (params: AnalysisParams) => void
}

export function Controls({ loading, onSubmit }: Props) {
  const [selection, setSelection] = useState<Selection | null>(null)
  // Default range starts in 1961 so the standard 1961-1990 baseline is used.
  const [startYear, setStartYear] = useState(1961)
  const [endYear, setEndYear] = useState(LAST_YEAR)
  const [hazard, setHazard] = useState('heatwave')
  const [percentile, setPercentile] = useState(95)
  const [minDuration, setMinDuration] = useState(3)
  const [method, setMethod] = useState<Method>('doy')

  const problems = validate(selection, startYear, endYear, percentile, minDuration)

  function submit(e: React.FormEvent) {
    e.preventDefault()
    if (problems.length > 0 || !selection) return
    onSubmit({ selection, startYear, endYear, percentile, minDuration, method })
  }

  return (
    <form className="controls" onSubmit={submit}>
      <LocationSearch
        onSelect={(place) => setSelection({ kind: 'point', lat: place.lat, lon: place.lon, label: placeLabel(place) })}
      />
      <MapPicker selection={selection} onSelect={setSelection} />
      <div className="selected-location" aria-live="polite">
        {selection ? <>Selected: <strong>{selection.label}</strong></> : 'No location selected yet.'}
      </div>

      <div className="field-row">
        <label>
          From
          <input type="number" min={FIRST_YEAR} max={LAST_YEAR} value={startYear}
            onChange={(e) => setStartYear(Number(e.target.value))} />
        </label>
        <label>
          To
          <input type="number" min={FIRST_YEAR} max={LAST_YEAR} value={endYear}
            onChange={(e) => setEndYear(Number(e.target.value))} />
        </label>
      </div>

      <label>
        Hazard
        <select value={hazard} onChange={(e) => setHazard(e.target.value)}>
          {HAZARDS.map((h) => (
            <option key={h.id} value={h.id} disabled={!h.available}>{h.label}</option>
          ))}
        </select>
      </label>

      <details className="advanced">
        <summary>Advanced options</summary>
        <label>
          Threshold percentile
          <input type="number" min={80} max={99} step={0.5} value={percentile}
            onChange={(e) => setPercentile(Number(e.target.value))} />
        </label>
        <label>
          Minimum heatwave length (days)
          <input type="number" min={2} max={10} value={minDuration}
            onChange={(e) => setMinDuration(Number(e.target.value))} />
        </label>
        <label>
          Threshold method
          <select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
            <option value="doy">Day-of-year (seasonal, ±7 days)</option>
            <option value="annual">Single annual value</option>
          </select>
        </label>
      </details>

      {problems.length > 0 && (
        <ul className="form-problems">
          {problems.map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}

      <button type="submit" className="primary" disabled={loading || problems.length > 0}>
        {loading ? 'Analysing…' : 'Analyse heatwaves'}
      </button>
    </form>
  )
}

function validate(selection: Selection | null, start: number, end: number, percentile: number, minDuration: number): string[] {
  const problems: string[] = []
  if (!selection) problems.push('Search for a city or click on the map.')
  if (start < FIRST_YEAR || end > LAST_YEAR) problems.push(`Years must be between ${FIRST_YEAR} and ${LAST_YEAR}.`)
  if (start >= end) problems.push('"From" must be before "To".')
  else if (end - start + 1 < MIN_RANGE || end - start + 1 > MAX_RANGE)
    problems.push(`Choose a range of ${MIN_RANGE} to ${MAX_RANGE} years.`)
  if (!(percentile >= 80 && percentile <= 99)) problems.push('Percentile must be between 80 and 99.')
  if (!(Number.isInteger(minDuration) && minDuration >= 2 && minDuration <= 10))
    problems.push('Minimum length must be a whole number from 2 to 10.')
  return problems
}
