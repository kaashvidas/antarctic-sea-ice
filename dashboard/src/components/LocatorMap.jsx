import { MapContainer, TileLayer, CircleMarker, Polyline, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { useEffect } from 'react'

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

function FitToBounds({ bounds }) {
  const map = useMap()
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [16, 16] })
  }, [bounds, map])
  return null
}

function ClickCatcher({ onPick }) {
  useMapEvents({
    click(e) {
      onPick({ lat: e.latlng.lat, lon: e.latlng.lng })
    },
  })
  return null
}

/**
 * Small interactive locator map for the journey planner. Fully controlled:
 * `start`/`goal` are {lat, lon} | null from the form state, and clicks are
 * reported up via onPick rather than the map owning its own point state —
 * that keeps the number inputs and the map in sync in one direction.
 */
export default function LocatorMap({ bounds, start, goal, onPick }) {
  const center = bounds
    ? [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
    : [-61, -47.5]

  const startPos = start && Number.isFinite(start.lat) && Number.isFinite(start.lon)
    ? [start.lat, start.lon] : null
  const goalPos = goal && Number.isFinite(goal.lat) && Number.isFinite(goal.lon)
    ? [goal.lat, goal.lon] : null

  return (
    <MapContainer className="locator-map" center={center} zoom={4} minZoom={3} maxZoom={9}>
      <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} className="basemap-tiles" />
      {bounds && <FitToBounds bounds={bounds} />}
      <ClickCatcher onPick={onPick} />

      {startPos && goalPos && (
        <Polyline positions={[startPos, goalPos]} pathOptions={{ color: '#34c3b8', weight: 2, dashArray: '4,5', opacity: 0.8 }} />
      )}
      {startPos && (
        <CircleMarker center={startPos} radius={7} pathOptions={{ color: '#fff', weight: 2, fillColor: '#34c3b8', fillOpacity: 1 }}>
          <Tooltip permanent direction="top" offset={[0, -6]} className="locator-tooltip">START</Tooltip>
        </CircleMarker>
      )}
      {goalPos && (
        <CircleMarker center={goalPos} radius={7} pathOptions={{ color: '#fff', weight: 2, fillColor: '#d1554a', fillOpacity: 1 }}>
          <Tooltip permanent direction="top" offset={[0, -6]} className="locator-tooltip">DEST</Tooltip>
        </CircleMarker>
      )}
    </MapContainer>
  )
}
