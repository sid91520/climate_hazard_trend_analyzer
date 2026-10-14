import { useEffect, useState } from 'react'
import { CircleMarker, MapContainer, Rectangle, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { LatLng } from 'leaflet'
import type { Selection } from '@/types'

const MAX_BOX_DEGREES = 2 // same cap as the backend

interface Props {
  selection: Selection | null
  onSelect: (selection: Selection) => void
}

/** Map to click a point, or click two opposite corners to draw a box. */
export function MapPicker({ selection, onSelect }: Props) {
  const [mode, setMode] = useState<'point' | 'box'>('point')
  const [firstCorner, setFirstCorner] = useState<LatLng | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  function handleClick(raw: LatLng) {
    const latlng = raw.wrap() // keep longitude in -180..180 even after panning around the globe
    setMessage(null)
    if (mode === 'point') {
      onSelect({ kind: 'point', lat: latlng.lat, lon: latlng.lng, label: `${latlng.lat.toFixed(2)}, ${latlng.lng.toFixed(2)}` })
      return
    }
    if (!firstCorner) {
      setFirstCorner(latlng)
      setMessage('Now click the opposite corner.')
      return
    }
    const box = {
      minLat: Math.min(firstCorner.lat, latlng.lat),
      maxLat: Math.max(firstCorner.lat, latlng.lat),
      minLon: Math.min(firstCorner.lng, latlng.lng),
      maxLon: Math.max(firstCorner.lng, latlng.lng),
    }
    setFirstCorner(null)
    const height = box.maxLat - box.minLat
    const width = box.maxLon - box.minLon
    if (height > MAX_BOX_DEGREES || width > MAX_BOX_DEGREES) {
      setMessage(`That box is ${height.toFixed(1)}° × ${width.toFixed(1)}°. The maximum is ${MAX_BOX_DEGREES}° × ${MAX_BOX_DEGREES}°. Try again.`)
      return
    }
    if (height === 0 || width === 0) {
      setMessage('The two corners must differ. Try again.')
      return
    }
    const centre = `${((box.minLat + box.maxLat) / 2).toFixed(2)}, ${((box.minLon + box.maxLon) / 2).toFixed(2)}`
    onSelect({ kind: 'box', ...box, label: `Box centred on ${centre}` })
  }

  function switchMode(next: 'point' | 'box') {
    setMode(next)
    setFirstCorner(null)
    setMessage(next === 'box' ? 'Click one corner of the box.' : null)
  }

  return (
    <div className="map-picker">
      <div className="segmented" role="group" aria-label="Map selection mode">
        <button type="button" aria-pressed={mode === 'point'} onClick={() => switchMode('point')}>
          Click a point
        </button>
        <button type="button" aria-pressed={mode === 'box'} onClick={() => switchMode('box')}>
          Draw a box
        </button>
      </div>
      <MapContainer center={[20, 0]} zoom={2} worldCopyJump className="map">
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        <ClickHandler onClick={handleClick} />
        <FollowSelection selection={selection} />
        {selection?.kind === 'point' && <CircleMarker center={[selection.lat, selection.lon]} radius={8} />}
        {selection?.kind === 'box' && (
          <Rectangle bounds={[[selection.minLat, selection.minLon], [selection.maxLat, selection.maxLon]]} />
        )}
        {firstCorner && <CircleMarker center={firstCorner} radius={5} />}
      </MapContainer>
      {message && <div className="hint">{message}</div>}
    </div>
  )
}

function ClickHandler({ onClick }: { onClick: (latlng: LatLng) => void }) {
  useMapEvents({ click: (e) => onClick(e.latlng) })
  return null
}

/** Zoom to the selection when it's off-screen or the map is zoomed far out (e.g. after a city search). */
function FollowSelection({ selection }: { selection: Selection | null }) {
  const map = useMap()
  useEffect(() => {
    if (!selection) return
    if (selection.kind === 'point') {
      const centre: [number, number] = [selection.lat, selection.lon]
      if (map.getZoom() < 6 || !map.getBounds().contains(centre)) map.setView(centre, 8)
    } else {
      map.fitBounds([[selection.minLat, selection.minLon], [selection.maxLat, selection.maxLon]], { padding: [20, 20] })
    }
  }, [map, selection])
  return null
}
