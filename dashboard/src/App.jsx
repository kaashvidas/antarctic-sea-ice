import { useEffect, useState } from 'react'
import './App.css'
import { fetchManifest, fetchIceClasses } from './api'
import JourneyPlanner from './views/JourneyPlanner'
import VoyageReport from './views/VoyageReport'

export default function App() {
  const [manifest, setManifest] = useState(null)
  const [iceClasses, setIceClasses] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [report, setReport] = useState(null)

  useEffect(() => {
    Promise.all([fetchManifest(), fetchIceClasses()])
      .then(([m, ic]) => {
        setManifest(m)
        setIceClasses(ic)
      })
      .catch((err) => setLoadError(err.message))
  }, [])

  if (loadError) {
    return (
      <div className="app-status error">
        <div>
          Failed to load data from the backend API at <strong>http://localhost:8001</strong>.
          <br />
          Make sure it&rsquo;s running:
          <code>venv/Scripts/python.exe -m uvicorn src.backend.app:app --reload --port 8001</code>
          <code>{loadError}</code>
        </div>
      </div>
    )
  }

  if (!manifest || !iceClasses) {
    return <div className="app-status">Loading Antarctic navigation data…</div>
  }

  return (
    <div className="app">
      <header className="app-topbar">
        <div className="app-topbar-title">
          <span className="app-mark" aria-hidden="true">⬡</span>
          KRYOS <span className="app-topbar-subtitle">— Antarctic Voyage Navigator</span>
        </div>
        <div className="app-topbar-meta">
          Forecast issued {manifest.forecast_date} · {manifest.forecast_horizon_days}-day horizon
        </div>
      </header>

      <main className="app-main">
        {report ? (
          <VoyageReport
            report={report}
            manifest={manifest}
            onPlanAnother={() => setReport(null)}
          />
        ) : (
          <JourneyPlanner
            manifest={manifest}
            iceClasses={iceClasses}
            onPlanned={(r) => setReport(r)}
          />
        )}
      </main>
    </div>
  )
}
