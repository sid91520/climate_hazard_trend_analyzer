'use client'

// Everything below the page is interactive (state, effects, browser APIs), so the
// whole app is one client component tree rendered inside the server-side page.
import { useEffect, useRef, useState } from 'react'
import { ApiError, csvUrl, fetchHeatwave, wakeServer } from '@/api/client'
import { Controls } from './Controls'
import { EventTable } from './EventTable'
import { MetricChart } from './MetricChart'
import { SummaryCard } from './SummaryCard'
import type { AnalysisParams, HeatwaveResponse } from '@/types'

type Status = 'idle' | 'loading' | 'error' | 'done'

export function HeatwaveApp() {
  const [status, setStatus] = useState<Status>('idle')
  const [result, setResult] = useState<HeatwaveResponse | null>(null)
  const [params, setParams] = useState<AnalysisParams | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef<AbortController | null>(null)

  // Start waking the (possibly sleeping) free-tier backend as soon as the page opens.
  useEffect(wakeServer, [])

  async function analyse(next: AnalysisParams) {
    inFlight.current?.abort() // a newer request replaces any older one still running
    const controller = new AbortController()
    inFlight.current = controller
    setParams(next)
    setStatus('loading')
    setError(null)
    try {
      setResult(await fetchHeatwave(next, controller.signal))
      setStatus('done')
    } catch (err) {
      if (controller.signal.aborted) return
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setStatus('error')
    }
  }

  return (
    <div className="layout">
      <header className="site-header">
        <h1>Heatwave Trend Analyzer</h1>
        <p className="muted">How have heatwaves changed at a place over the decades?</p>
      </header>

      <aside className="sidebar">
        <Controls loading={status === 'loading'} onSubmit={analyse} />
      </aside>

      <main className="results">
        {status === 'idle' && (
          <div className="card empty-state">
            <h2>Pick a place and a period</h2>
            <p>
              Search for a city or click the map, choose a year range, then press <strong>Analyse heatwaves</strong>.
              You’ll get yearly heatwave counts, durations and intensity, their trends, and a plain-English summary.
            </p>
          </div>
        )}

        {status === 'loading' && (
          <div className="card empty-state" role="status">
            <div className="spinner" aria-hidden="true" />
            <h2>Analysing…</h2>
            <p className="muted">
              The first request can take up to a minute: the free server may be asleep, and decades of daily data
              are downloaded. Repeat requests are cached and fast.
            </p>
          </div>
        )}

        {status === 'error' && params && (
          <div className="card error-state" role="alert">
            <h2>Couldn’t run the analysis</h2>
            <p>{error}</p>
            <button type="button" onClick={() => analyse(params)}>Try again</button>
          </div>
        )}

        {status === 'done' && result && params && (
          <>
            <SummaryCard result={result} locationLabel={params.selection.label} />

            <div className="export-bar no-print">
              <a className="button" href={csvUrl(params, 'yearly')}>Download yearly CSV</a>
              <a className="button" href={csvUrl(params, 'events')}>Download events CSV</a>
              <button type="button" onClick={() => window.print()}>Print / save as PDF</button>
            </div>

            <div className="chart-grid">
              <MetricChart title="Heatwave events per year" metric="events" unit="events"
                yearly={result.yearly} trend={result.trends.events} />
              <MetricChart title="Total heatwave days per year" metric="heatwave_days" unit="days"
                yearly={result.yearly} trend={result.trends.heatwave_days} />
              <MetricChart title="Longest heatwave each year" metric="longest_event" unit="days"
                yearly={result.yearly} trend={result.trends.longest_event} />
              <MetricChart title="Mean heatwave intensity" metric="mean_intensity" unit="°C above threshold"
                yearly={result.yearly} trend={result.trends.mean_intensity} />
            </div>

            <EventTable events={result.events} />
          </>
        )}
      </main>
    </div>
  )
}
