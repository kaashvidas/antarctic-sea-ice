// Small formatting/derivation helpers shared by the report views. Kept
// separate from geoutils.js (pure geometry) since these are about
// presenting API values, not computing geographic geometry.

const COMPASS = [
  'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW',
]

/**
 * u = eastward component (m/s), v = northward component (m/s).
 * Returns speed (m/s) and the compass bearing the vector points TOWARD
 * (0 = north, 90 = east), plus a 16-point compass label. Good enough for
 * a placeholder-data display; not a navigation-grade convention.
 */
export function vectorToSpeedDir(u, v) {
  const speed = Math.hypot(u, v)
  const mathDeg = Math.atan2(v, u) * (180 / Math.PI) // 0=east(+x), 90=north(+y)
  const bearingDeg = (90 - mathDeg + 360) % 360
  const compass = COMPASS[Math.round(bearingDeg / 22.5) % 16]
  return { speed, bearingDeg, compass }
}

export function fmtKm(km) {
  if (km === null || km === undefined || Number.isNaN(km)) return '—'
  return `${km.toLocaleString(undefined, { maximumFractionDigits: 1 })} km`
}

export function fmtPct(p, digits = 0) {
  if (p === null || p === undefined || Number.isNaN(p)) return '—'
  return `${p.toFixed(digits)}%`
}

export function fmtDateTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export function fmtDate(iso) {
  if (!iso) return '—'
  const d = new Date(`${iso}T00:00:00Z`)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString(undefined, {
    timeZone: 'UTC', month: 'short', day: '2-digit', year: 'numeric',
  })
}

export function humanize(fieldName) {
  return fieldName
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}
