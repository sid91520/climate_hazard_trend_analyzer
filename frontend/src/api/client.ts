import type { AnalysisParams, HeatwaveResponse, Place } from '@/types'

// Set NEXT_PUBLIC_API_URL in .env.local (local) or in the Vercel dashboard (production).
// NEXT_PUBLIC_ variables are inlined into the browser bundle at build time, so changing
// it on Vercel needs a redeploy. It's a public URL, not a secret.
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

/** An error the UI can show as-is. `code` matches the backend's error codes. */
export class ApiError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

async function getJson<T>(path: string, params: URLSearchParams, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}?${params}`, { signal })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError('network_error', "Can't reach the server. It may be starting up. Please try again in a moment.")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    // The backend always sends {"error": {"code", "message"}}.
    throw new ApiError(body?.error?.code ?? 'http_error', body?.error?.message ?? `Request failed (${response.status})`)
  }
  return body as T
}

/** Turn the UI's params into the backend's query string. */
export function analysisQuery(p: AnalysisParams): URLSearchParams {
  const q = new URLSearchParams({
    start_year: String(p.startYear),
    end_year: String(p.endYear),
    percentile: String(p.percentile),
    min_duration: String(p.minDuration),
    method: p.method,
  })
  const s = p.selection
  if (s.kind === 'point') {
    q.set('lat', s.lat.toFixed(4))
    q.set('lon', s.lon.toFixed(4))
  } else {
    q.set('min_lat', s.minLat.toFixed(4))
    q.set('max_lat', s.maxLat.toFixed(4))
    q.set('min_lon', s.minLon.toFixed(4))
    q.set('max_lon', s.maxLon.toFixed(4))
  }
  return q
}

export function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  return getJson<Place[]>('/api/geocode', new URLSearchParams({ q: query }), signal)
}

export function fetchHeatwave(p: AnalysisParams, signal?: AbortSignal): Promise<HeatwaveResponse> {
  return getJson<HeatwaveResponse>('/api/hazards/heatwave', analysisQuery(p), signal)
}

/** A plain link is enough: the backend sends Content-Disposition: attachment. */
export function csvUrl(p: AnalysisParams, table: 'yearly' | 'events'): string {
  const q = analysisQuery(p)
  q.set('table', table)
  return `${API_URL}/api/hazards/heatwave/export.csv?${q}`
}

/** Fire-and-forget request so a sleeping Render server starts waking up early. */
export function wakeServer(): void {
  fetch(`${API_URL}/api/health`).catch(() => undefined)
}
