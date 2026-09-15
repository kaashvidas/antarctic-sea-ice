import { useState } from 'react'
import LocatorMap from '../components/LocatorMap'
import { planJourney } from '../api'

const DEFAULT_SPEED = 18

function toNum(v) {
  const n = parseFloat(v)
  return Number.isFinite(n) ? n : null
}

export default function JourneyPlanner({ manifest, iceClasses, onPlanned }) {
  const routeDefaults = manifest?.domain?.default_route
  const [startLat, setStartLat] = useState(String(routeDefaults?.start?.lat ?? -65.5))
  const [startLon, setStartLon] = useState(String(routeDefaults?.start?.lon ?? -57.0))
  const [goalLat, setGoalLat] = useState(String(routeDefaults?.goal?.lat ?? -56.5))
  const [goalLon, setGoalLon] = useState(String(routeDefaults?.goal?.lon ?? -37.0))
  const [departure, setDeparture] = useState('2026-09-15T06:00')
  const [speed, setSpeed] = useState(String(DEFAULT_SPEED))
  const [iceClass, setIceClass] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [errorMessage, setErrorMessage] = useState(null)

  const iceClassKeys = Object.keys(iceClasses || {})
  const effectiveIceClass = iceClass || iceClassKeys[0] || ''

  const bounds = manifest
    ? [[manifest.bounds.lat_min, manifest.bounds.lon_min], [manifest.bounds.lat_max, manifest.bounds.lon_max]]
    : null

  const start = { lat: toNum(startLat), lon: toNum(startLon) }
  const goal = { lat: toNum(goalLat), lon: toNum(goalLon) }

  function handleMapPick({ lat, lon }) {
    const startSet = start.lat !== null && start.lon !== null
    const goalSet = goal.lat !== null && goal.lon !== null
    if (!startSet || (startSet && goalSet)) {
      setStartLat(lat.toFixed(3))
      setStartLon(lon.toFixed(3))
      setGoalLat('')
      setGoalLon('')
    } else {
      setGoalLat(lat.toFixed(3))
      setGoalLon(lon.toFixed(3))
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setErrorMessage(null)

    const s = { lat: toNum(startLat), lon: toNum(startLon) }
    const g = { lat: toNum(goalLat), lon: toNum(goalLon) }
    const spd = toNum(speed)

    if (s.lat === null || s.lon === null || g.lat === null || g.lon === null) {
      setErrorMessage('Enter a valid start and destination (lat/lon), or set them on the map.')
      return
    }
    if (spd === null || spd <= 0) {
      setErrorMessage('Vessel cruising speed must be a positive number.')
      return
    }
    if (!departure) {
      setErrorMessage('Choose a departure date and time.')
      return
    }
    if (!effectiveIceClass) {
      setErrorMessage('Select the vessel ice class.')
      return
    }

    setSubmitting(true)
    try {
      const query = {
        start: s,
        goal: g,
        departure_time: departure,
        vessel_speed_kmh: spd,
        ice_class: effectiveIceClass,
      }
      const report = await planJourney(query)
      onPlanned(report)
    } catch (err) {
      setErrorMessage(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="planner">
      <form className="planner-form" onSubmit={handleSubmit}>
        <div className="panel">
          <h2 className="panel-title">Route</h2>
          <div className="field-grid two-col">
            <label className="field">
              <span className="field-label">Start lat</span>
              <input type="number" step="0.001" value={startLat} onChange={(e) => setStartLat(e.target.value)} placeholder="-65.500" required />
            </label>
            <label className="field">
              <span className="field-label">Start lon</span>
              <input type="number" step="0.001" value={startLon} onChange={(e) => setStartLon(e.target.value)} placeholder="-57.000" required />
            </label>
            <label className="field">
              <span className="field-label">Destination lat</span>
              <input type="number" step="0.001" value={goalLat} onChange={(e) => setGoalLat(e.target.value)} placeholder="-56.500" required />
            </label>
            <label className="field">
              <span className="field-label">Destination lon</span>
              <input type="number" step="0.001" value={goalLon} onChange={(e) => setGoalLon(e.target.value)} placeholder="-37.000" required />
            </label>
          </div>
          <p className="field-hint">Or click the map — first click sets start, second sets destination.</p>
        </div>

        <div className="panel">
          <h2 className="panel-title">Departure</h2>
          <label className="field">
            <span className="field-label">Date &amp; time</span>
            <input type="datetime-local" value={departure} onChange={(e) => setDeparture(e.target.value)} required />
          </label>
        </div>

        <div className="panel">
          <h2 className="panel-title">Vessel</h2>
          <div className="field-grid">
            <label className="field">
              <span className="field-label">Cruising speed (km/h)</span>
              <input type="number" step="0.1" min="0.1" value={speed} onChange={(e) => setSpeed(e.target.value)} required />
            </label>
            <label className="field">
              <span className="field-label">Ice class</span>
              <select value={effectiveIceClass} onChange={(e) => setIceClass(e.target.value)} required>
                {iceClassKeys.length === 0 && <option value="">Loading…</option>}
                {iceClassKeys.map((key) => (
                  <option key={key} value={key}>{iceClasses[key].label}</option>
                ))}
              </select>
            </label>
          </div>
        </div>

        {errorMessage && (
          <div className="alert-panel" role="alert">
            <span className="alert-tag">Route error</span>
            <span>{errorMessage}</span>
          </div>
        )}

        <button type="submit" className="btn-primary" disabled={submitting}>
          {submitting ? 'Computing route…' : 'Plan voyage'}
        </button>
      </form>

      <div className="planner-map-pane">
        <div className="planner-map-label">{manifest?.domain?.label || 'Weddell Sea'} — click to set start / destination</div>
        {bounds ? (
          <LocatorMap
            bounds={bounds}
            start={start}
            goal={goal}
            siteMarkers={manifest?.domain?.site_markers || []}
            onPick={handleMapPick}
          />
        ) : (
          <div className="map-loading">Loading chart bounds…</div>
        )}
      </div>
    </div>
  )
}
