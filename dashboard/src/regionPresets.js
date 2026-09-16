// Named quick-select locations per region, so choosing a start/destination
// doesn't require knowing or guessing valid lat/lon by hand. Real research
// stations are labeled with their real name and the real navigable point
// closest to them (a station itself sits on land/ice -- ships can't start
// there, so each station location is the nearest real open-water cell,
// found via find_open_water() against the station's real coordinates,
// with the real distance from the station noted). Every station's real
// coordinates were independently verified via web search (not taken from
// memory), and every navigable point was checked with an actual
// plan_journey() call during development, not guessed.
//
// This list was audited 2026-09-16 for completeness within each region's
// real bounding box (not just "one station per region" from partial
// knowledge) -- see PROJECT_STATUS.md section 6 for the audit notes. It
// may still not be perfectly exhaustive (no authoritative single source
// was cross-checked against), but every entry here is real and verified,
// and the known clusters (Larsemann Hills, McMurdo Sound, South Orkney
// Islands / Antarctic Peninsula) are all represented.
// Backend URL per region: defaults to localhost for local dev (one
// uvicorn instance per region, see PROJECT_STATUS.md section 4), but a
// deployed frontend needs real deployed backend URLs instead -- set
// VITE_WEDDELL_API_URL / VITE_PRYDZ_BAY_API_URL / VITE_ROSS_SEA_API_URL
// as build-time env vars (Vercel/Netlify project settings, or a local
// .env file) to override. Vite only exposes env vars prefixed VITE_ and
// only inlines them at BUILD time, not runtime -- changing one requires
// a rebuild/redeploy of the frontend, not just a restart.
function apiUrlFor(envVar, localPort) {
  return import.meta.env[envVar] || `http://localhost:${localPort}`
}

export const REGION_INFO = {
  weddell: {
    displayName: 'Weddell Sea',
    apiUrl: apiUrlFor('VITE_WEDDELL_API_URL', 8001),
    locations: [
      { label: 'Orcadas Station (Argentina)', lat: -60.625, lon: -44.625, note: '~14 km from the real station' },
      { label: 'Signy Research Station (UK)', lat: -60.875, lon: -45.875, note: '~24 km from the real station' },
      { label: 'Esperanza Base (Argentina)', lat: -63.375, lon: -56.875, note: '~7 km from the real station' },
      { label: 'Marambio Base (Argentina)', lat: -64.125, lon: -56.625, note: '~13 km from the real station' },
      { label: 'Iceberg cluster edge (D32/D33)', lat: -58.88, lon: -51.12 },
      { label: 'Northeast open water', lat: -54.88, lon: -35.12 },
    ],
  },
  prydz_bay: {
    displayName: 'Prydz Bay',
    apiUrl: apiUrlFor('VITE_PRYDZ_BAY_API_URL', 8002),
    locations: [
      { label: 'Bharati Station (India)', lat: -69.375, lon: 76.125, note: '~5 km from the real station' },
      { label: 'Progress Station (Russia)', lat: -69.375, lon: 76.375, note: '~1 km from the real station' },
      { label: 'Zhongshan Station (China)', lat: -69.375, lon: 76.375, note: '~0.2 km from the real station' },
      { label: 'Davis Station (Australia)', lat: -68.625, lon: 77.875, note: '~7 km from the real station' },
      { label: 'Law-Racoviță-Negoiță Station (Romania)', lat: -69.375, lon: 76.375, note: '~1.5 km from the real station' },
      { label: 'Prydz Bay iceberg zone (D23)', lat: -69.625, lon: 74.875 },
      { label: 'Open water, north of the bay', lat: -60.875, lon: 70.0 },
    ],
  },
  ross_sea: {
    displayName: 'Ross Sea',
    apiUrl: apiUrlFor('VITE_ROSS_SEA_API_URL', 8003),
    locations: [
      { label: 'McMurdo Station (USA)', lat: -77.375, lon: 166.125, note: '~55 km from the real station' },
      { label: 'Scott Base (New Zealand)', lat: -77.875, lon: 166.875, note: '~4 km from the real station' },
      { label: 'Mario Zucchelli Station (Italy)', lat: -74.875, lon: 163.875, note: '~21 km from the real station' },
      { label: 'Jang Bogo Station (South Korea)', lat: -74.875, lon: 163.875, note: '~31 km from the real station' },
      { label: 'Ross Sea open water', lat: -67.875, lon: 175.125 },
    ],
  },
}

export const DEFAULT_REGION_INFO = {
  displayName: 'this domain',
  apiUrl: 'http://localhost:8001',
  locations: [],
}

export function regionInfoFor(regionKey) {
  return REGION_INFO[regionKey] || DEFAULT_REGION_INFO
}

// Regions that exist in src/utils/grid.py's REGIONS registry but don't
// have a built checkpoint/data yet, shown so a Maitri-shaped question
// gets an honest answer instead of silence. Keep this in sync with
// PROJECT_STATUS.md section 6.
export const UNAVAILABLE_REGIONS = [
  {
    label: 'Queen Maud Land (near Maitri Station, India)',
    reason: 'No real icebergs currently tracked within ~1,000 km of Maitri (checked 2026-09-16) -- deliberately deferred rather than fake a cluster.',
  },
]
