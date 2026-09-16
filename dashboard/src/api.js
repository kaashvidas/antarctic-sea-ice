// Thin fetch wrappers around the FastAPI backend (src/backend/app.py).
// The backend allows CORS from any localhost/127.0.0.1 origin (regex-based),
// so this works regardless of which port Vite dev server picks.
//
// One backend process serves exactly one region (set via the REGION env
// var at startup, see src/utils/grid.py) -- there's no live per-request
// region switch on the server side. To let the dashboard show more than
// one region without restarting anything, run one uvicorn instance per
// region on its own port (see REGION_PORTS in regionPresets.js) and let
// the frontend pick which port to talk to. API_BASE is therefore mutable,
// not a fixed constant -- setApiBase() below changes it, and every
// existing call site already reads it fresh on each request.

let apiBase = 'http://localhost:8001'

export function setApiBase(base) {
  apiBase = base
}

export function getApiBase() {
  return apiBase
}

async function getJSON(path) {
  const res = await fetch(`${apiBase}${path}`)
  if (!res.ok) {
    throw new Error(`${path} -> HTTP ${res.status}`)
  }
  return res.json()
}

/** GET /api/manifest */
export function fetchManifest() {
  return getJSON('/api/manifest')
}

/** GET /api/ice_classes -> { key: {label, max_safe_concentration, seaice_weight_multiplier}, ... } */
export function fetchIceClasses() {
  return getJSON('/api/ice_classes')
}

/** Build the absolute URL for a file under outputs/, e.g. "seaice/day_00.png" */
export function outputUrl(relativePath) {
  return `${apiBase}/outputs/${relativePath}`
}

/**
 * POST /api/plan_journey. Throws an Error whose .message is the backend's
 * human-readable `detail` string on a 400 (e.g. "no feasible route..."),
 * so callers can render it directly rather than a generic failure.
 */
export async function planJourney(payload) {
  let res
  try {
    res = await fetch(`${apiBase}/api/plan_journey`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  } catch {
    throw new Error(
      `Could not reach the backend at ${apiBase}. Is uvicorn running?`,
    )
  }

  const body = await res.json().catch(() => null)
  if (!res.ok) {
    throw new Error(body?.detail || `Request failed (HTTP ${res.status}).`)
  }
  return body
}
