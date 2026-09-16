import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, Tooltip, useMap, useMapEvents } from 'react-leaflet'
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
 *
 * `stations`: real named locations (research stations, open-water
 * reference points) for this region -- see regionPresets.js. Rendered as
 * distinct diamond markers with a click-to-open popup offering explicit
 * "Set as start"/"Set as destination" choices, so picking a named place
 * is as easy as clicking the map itself, not just a fallback text list.
 */
export default function LocatorMap({ bounds, start, goal, onPick, stations, onSetStart, onSetGoal }) {
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

      {(stations || []).map((station) => (
        <CircleMarker
          key={station.label}
          center={[station.lat, station.lon]}
          radius={6}
          pathOptions={{ color: '#f2b84b', weight: 2, fillColor: '#1a2230', fillOpacity: 1 }}
        >
          <Tooltip direction="top" offset={[0, -6]}>{station.label}</Tooltip>
          <Popup className="station-popup">
            <strong>{station.label}</strong>
            {station.note && <p className="station-popup-note">{station.note}</p>}
            <div className="station-popup-actions">
              <button type="button" className="btn-chip" onClick={() => onSetStart?.(station.lat, station.lon)}>Set as start</button>
              <button type="button" className="btn-chip" onClick={() => onSetGoal?.(station.lat, station.lon)}>Set as destination</button>
            </div>
          </Popup>
        </CircleMarker>
      ))}

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
