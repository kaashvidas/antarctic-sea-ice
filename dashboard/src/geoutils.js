// Small geometry helpers. No turf/lodash dependency needed for this.

/**
 * Convex hull via Andrew's monotone chain.
 * @param {Array<[number, number]>} points - array of [a, b] pairs (axis order doesn't matter for hull correctness)
 * @returns {Array<[number, number]>} hull points in counter-clockwise order
 */
export function convexHull(points) {
  const pts = Array.from(
    new Map(points.map((p) => [`${p[0]},${p[1]}`, p])).values(),
  ).sort((a, b) => a[0] - b[0] || a[1] - b[1])

  if (pts.length < 3) return pts

  const cross = (o, a, b) =>
    (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

  const lower = []
  for (const p of pts) {
    while (
      lower.length >= 2 &&
      cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0
    ) {
      lower.pop()
    }
    lower.push(p)
  }

  const upper = []
  for (let i = pts.length - 1; i >= 0; i--) {
    const p = pts[i]
    while (
      upper.length >= 2 &&
      cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0
    ) {
      upper.pop()
    }
    upper.push(p)
  }

  lower.pop()
  upper.pop()
  return lower.concat(upper)
}

/** Convert a GeoJSON [lon, lat] pair to Leaflet's [lat, lon] order. */
export function toLatLng([lon, lat]) {
  return [lat, lon]
}

/** Convert an array of GeoJSON [lon, lat] pairs to Leaflet [lat, lon] pairs. */
export function toLatLngs(coords) {
  return coords.map(toLatLng)
}
