import { useEffect, useState } from 'react'
import { searchPlaces } from '@/api/client'
import { placeLabel } from '@/format'
import { useDebounce } from '@/hooks/useDebounce'
import type { Place } from '@/types'

interface Props {
  onSelect: (place: Place) => void
}

/** City search box with a debounced autocomplete list. */
export function LocationSearch({ onSelect }: Props) {
  const [text, setText] = useState('')
  const [chosenLabel, setChosenLabel] = useState<string | null>(null)
  const [results, setResults] = useState<Place[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Wait for a 350 ms pause in typing before calling the API (fewer requests).
  const query = useDebounce(text.trim(), 350)

  useEffect(() => {
    // Don't search again for the text we just filled in from a chosen result.
    if (query.length < 2 || query === chosenLabel) {
      setResults([])
      return
    }
    const controller = new AbortController() // cancels this request if the user keeps typing
    setLoading(true)
    searchPlaces(query, controller.signal)
      .then((places) => {
        setResults(places)
        setError(places.length === 0 ? 'No places found.' : null)
      })
      .catch((err: Error) => {
        if (err.name !== 'AbortError') setError(err.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [query, chosenLabel])

  function choose(place: Place) {
    const label = placeLabel(place)
    setChosenLabel(label)
    setText(label)
    setResults([])
    setError(null)
    onSelect(place)
  }

  return (
    <div className="search">
      <label htmlFor="city-search">City</label>
      <input
        id="city-search"
        type="search"
        placeholder="Search a city, e.g. Mumbai"
        value={text}
        maxLength={100}
        autoComplete="off"
        onChange={(e) => setText(e.target.value)}
        aria-autocomplete="list"
        aria-controls="city-results"
      />
      {loading && <div className="hint">Searching…</div>}
      {error && !loading && <div className="hint">{error}</div>}
      {results.length > 0 && (
        <ul id="city-results" className="search-results" role="listbox">
          {results.map((place) => (
            <li key={`${place.lat},${place.lon}`} role="option" aria-selected={false}>
              <button type="button" onClick={() => choose(place)}>
                <strong>{place.name}</strong>
                <span>{[place.admin1, place.country].filter(Boolean).join(', ')}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
