import { useEffect, useState } from 'react'
// Import order matters (CSS cascade) and matches these files' original
// order inside the single App.css they were split from -- see
// styles/shell.css's header for why.
import './styles/shell.css'
import './styles/controls.css'
import './styles/report.css'
import { fetchManifest, fetchIceClasses, setApiBase, getApiBase } from './api'
import { REGION_INFO } from './regionPresets'
import JourneyPlanner from './views/JourneyPlanner'
import VoyageReport from './views/VoyageReport'
import Splash from './components/Splash'

// Real minimum time the opening splash stays up, so it reads as an
// intentional opening beat rather than a one-frame flash when the local
// backend responds fast -- not an artificial delay on top of loading,
// just a floor under how quickly it can be dismissed.
const SPLASH_MIN_MS = 1400

// One backend process per region (see api.js's comment on setApiBase) --
// this is what actually lets the dashboard show more than one region:
// switching here points every API call at a different already-running
// uvicorn instance, rather than only ever showing whichever region the
// single backend happened to start with.
const REGION_KEYS = Object.keys(REGION_INFO)

export default function App() {
  const [selectedRegion, setSelectedRegion] = useState(REGION_KEYS[0])
  const [manifest, setManifest] = useState(null)
  const [iceClasses, setIceClasses] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [report, setReport] = useState(null)
  const [showSplash, setShowSplash] = useState(true)

  useEffect(() => {
    const timer = setTimeout(() => setShowSplash(false), SPLASH_MIN_MS)
    return () => clearTimeout(timer)
  }, [])

  useEffect(() => {
    setApiBase(`http://localhost:${REGION_INFO[selectedRegion].apiPort}`)
    setManifest(null)
    setIceClasses(null)
    setLoadError(null)
    setReport(null)
    Promise.all([fetchManifest(), fetchIceClasses()])
      .then(([m, ic]) => {
        setManifest(m)
        setIceClasses(ic)
      })
      .catch((err) => setLoadError(err.message))
  }, [selectedRegion])

  if (showSplash) {
    return <Splash />
  }

  if (loadError) {
    return (
      <div className="app-status error">
        <div>
          Failed to load data from the backend API at <strong>{getApiBase()}</strong>.
          <br />
          Make sure it&rsquo;s running for this region:
          <code>REGION={selectedRegion} venv/Scripts/python.exe -m uvicorn src.backend.app:app --port {REGION_INFO[selectedRegion].apiPort}</code>
          <code>{loadError}</code>
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      <header className="app-topbar">
        <div className="app-topbar-title">
          <span className="app-mark" aria-hidden="true">⬡</span>
          KRYOS <span className="app-topbar-subtitle">— Antarctic Voyage Navigator</span>
        </div>
        <div className="app-topbar-controls">
          <div className="region-switcher" role="tablist" aria-label="Region">
            {REGION_KEYS.map((key) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={key === selectedRegion}
                className={`region-tab${key === selectedRegion ? ' region-tab--active' : ''}`}
                onClick={() => setSelectedRegion(key)}
              >
                {REGION_INFO[key].displayName}
              </button>
            ))}
          </div>
          {manifest && (
            <div className="app-topbar-meta">
              Forecast issued {manifest.forecast_date} · {manifest.forecast_horizon_days}-day horizon
            </div>
          )}
        </div>
      </header>

      <main className="app-main">
        {!manifest || !iceClasses ? (
          <div className="app-status">Loading {REGION_INFO[selectedRegion].displayName} navigation data…</div>
        ) : report ? (
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
