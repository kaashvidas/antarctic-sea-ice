// Fixed, distinct color per iceberg id so the same berg reads consistently
// across its current-position marker, predicted track, and drift cone.
const PALETTE = [
  '#ff6b6b', // D32 - red
  '#4dabf7', // D33A - blue
  '#ffd43b', // D33B - yellow
  '#da77f2', // D33C - purple
  '#ff922b', // D33D - orange
  '#20c997', // D35 - teal
]

const FALLBACK = '#adb5bd'

export function colorForIceberg(icebergId, allIds) {
  const idx = allIds.indexOf(icebergId)
  if (idx === -1) return FALLBACK
  return PALETTE[idx % PALETTE.length]
}
