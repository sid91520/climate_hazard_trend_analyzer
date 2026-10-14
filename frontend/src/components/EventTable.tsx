import { useMemo, useState } from 'react'
import type { HeatwaveEvent } from '@/types'

type SortKey = keyof HeatwaveEvent

const COLUMNS: { key: SortKey; label: string; numeric: boolean }[] = [
  { key: 'start', label: 'Start', numeric: false },
  { key: 'end', label: 'End', numeric: false },
  { key: 'duration', label: 'Days', numeric: true },
  { key: 'peak_temp', label: 'Peak Tmax (°C)', numeric: true },
  { key: 'mean_excess', label: 'Mean above threshold (°C)', numeric: true },
]

/** Sortable list of every detected heatwave. Click a header to sort; click again to reverse. */
export function EventTable({ events }: { events: HeatwaveEvent[] }) {
  const [sortKey, setSortKey] = useState<SortKey>('start')
  const [descending, setDescending] = useState(true)

  const sorted = useMemo(() => {
    // ISO dates ("2023-10-23") sort correctly as strings, so one comparison works for all columns.
    const copy = [...events]
    copy.sort((a, b) => (a[sortKey] < b[sortKey] ? -1 : a[sortKey] > b[sortKey] ? 1 : 0))
    return descending ? copy.reverse() : copy
  }, [events, sortKey, descending])

  function sortBy(key: SortKey) {
    if (key === sortKey) setDescending(!descending)
    else {
      setSortKey(key)
      setDescending(true)
    }
  }

  if (events.length === 0) {
    return (
      <section className="card">
        <h3>Individual heatwaves</h3>
        <p className="muted">No heatwaves were detected with these settings.</p>
      </section>
    )
  }

  return (
    <section className="card">
      <h3>Individual heatwaves ({events.length})</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className={col.numeric ? 'num' : undefined}
                  aria-sort={sortKey === col.key ? (descending ? 'descending' : 'ascending') : 'none'}
                >
                  <button type="button" onClick={() => sortBy(col.key)}>
                    {col.label}
                    <span aria-hidden="true">{sortKey === col.key ? (descending ? ' ▼' : ' ▲') : ''}</span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((e) => (
              <tr key={e.start}>
                <td>{e.start}</td>
                <td>{e.end}</td>
                <td className="num">{e.duration}</td>
                <td className="num">{e.peak_temp.toFixed(1)}</td>
                <td className="num">{e.mean_excess.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
