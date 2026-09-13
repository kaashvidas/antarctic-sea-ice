// Fixed, distinct color per iceberg id so the same berg reads consistently
// across its current-position marker and predicted track. Deliberately
// avoids the red family — that's reserved for the naive route and
// close-approach warnings, so an iceberg's own color never gets confused
// with a safety signal.
const PALETTE = [
  '#4f8fd6', // D32 - blue
  '#e0a53c', // D33A - amber
  '#9b7fe0', // D33B - violet
  '#3ec9a7', // D33C - teal
  '#e08fc0', // D33D - pink
  '#a8c93c', // D35 - lime
]

const FALLBACK = '#adb5bd'

export function colorForIceberg(icebergId, allIds) {
  const idx = allIds.indexOf(icebergId)
  if (idx === -1) return FALLBACK
  return PALETTE[idx % PALETTE.length]
}
