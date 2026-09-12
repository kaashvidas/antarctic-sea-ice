// Thin fetch wrappers around the FastAPI backend (src/backend/app.py).
// The backend only allows CORS from the Vite dev server origin(s), so this
// must be run via `npm run dev` (port 5173) while the API runs on :8001.
// (Not :8000 -- this dev machine has a stuck orphaned listener on 8000
// from an earlier session that the OS won't release; 8001 is the one
// that's actually free. Change both here and in src/backend/app.py's run
// instructions together if you ever move off 8001.)

export const API_BASE = 'http://localhost:8001'

async function getJSON(path) {
  const res = await fetch(`${API_BASE}${path}`)
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`)
  }
  return res.json()
}

/** GET /api/manifest */
export function fetchManifest() {
  return getJSON('/api/manifest')
}

/** GET /api/routes -> GeoJSON FeatureCollection */
export function fetchRoutes() {
  return getJSON('/api/routes')
}

/** Build the absolute URL for a sea-ice overlay PNG, e.g. "seaice/day_00.png" */
export function seaIceImageUrl(relativePath) {
  return `${API_BASE}/outputs/${relativePath}`
}
