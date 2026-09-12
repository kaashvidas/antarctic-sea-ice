import { useEffect, useState } from 'react'
import './App.css'
import { fetchManifest, fetchRoutes, seaIceImageUrl } from './api'
import MapView from './components/MapView'
import DaySlider from './components/DaySlider'
import DisclosureBanner from './components/DisclosureBanner'
import Legend from './components/Legend'

export default function App() {
  const [manifest, setManifest] = useState(null)
  const [routesGeoJSON, setRoutesGeoJSON] = useState(null)
  const [error, setError] = useState(null)

  const [day, setDay] = useState(0)
  const [showSeaIce, setShowSeaIce] = useState(true)
  const [seaIceOpacity, setSeaIceOpacity] = useState(0.6)

  useEffect(() => {
    Promise.all([fetchManifest(), fetchRoutes()])
      .then(([m, r]) => {
        setManifest(m)
        setRoutesGeoJSON(r)
      })
      .catch((err) => setError(err.message))
  }, [])

  if (error) {
    return (
      <div className="app-status error">
        <div>
          Failed to load data from the backend API at{' '}
          <strong>http://localhost:8001</strong>.
          <br />
          Make sure it's running:
          <code>
            venv/Scripts/python.exe -m uvicorn src.backend.app:app --reload
            --port 8001
          </code>
          <code>{error}</code>
        </div>
      </div>
    )
  }

  if (!manifest || !routesGeoJSON) {
    return <div className="app-status">Loading Antarctic navigation data…</div>
  }

  const { bounds, iceberg_ids: icebergIds, seaice_images: seaIceImages } =
    manifest
  const leafletBounds = [
    [bounds.lat_min, bounds.lon_min],
    [bounds.lat_max, bounds.lon_max],
  ]
  const maxDay = manifest.forecast_horizon_days
  const seaIceUrl = seaIceImages[day] ? seaIceImageUrl(seaIceImages[day]) : null

  return (
    <div className="app">
      <DisclosureBanner placeholderInputs={manifest.placeholder_inputs} />

      <div className="app-title">
        <h1>Weddell Sea Navigation — Iceberg &amp; Sea-Ice Decision Support</h1>
        <p>Forecast issued {manifest.forecast_date}</p>
      </div>

      <MapView
        bounds={leafletBounds}
        icebergIds={icebergIds}
        routesGeoJSON={routesGeoJSON}
        seaIceUrl={seaIceUrl}
        showSeaIce={showSeaIce}
        seaIceOpacity={seaIceOpacity}
      />

      <Legend />

      <DaySlider
        day={day}
        maxDay={maxDay}
        onChange={setDay}
        forecastDate={manifest.forecast_date}
        showSeaIce={showSeaIce}
        onToggleSeaIce={setShowSeaIce}
        seaIceOpacity={seaIceOpacity}
        onOpacityChange={setSeaIceOpacity}
      />
    </div>
  )
}
