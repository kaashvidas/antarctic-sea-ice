// Named quick-select locations per region, so choosing a start/destination
// doesn't require knowing or guessing valid lat/lon by hand. Real research
// stations are labeled with their real name and the real navigable point
// closest to them (a station itself sits on land/ice -- ships can't start
// there, so each station location is the nearest real open-water cell,
// found via find_open_water(), with the real distance from the station
// noted). Every coordinate here was verified via an actual plan_journey()
// call during development (not guessed). Non-station points (e.g. "open
// water") are real, tested reference points included for a second
// endpoint, not tied to any specific place.
export const REGION_INFO = {
  weddell: {
    displayName: 'Weddell Sea',
    locations: [
      { label: 'Orcadas Station (Argentina)', lat: -60.625, lon: -44.625, note: '~14 km from the real station' },
      { label: 'Iceberg cluster edge (D32/D33)', lat: -58.88, lon: -51.12 },
      { label: 'Northeast open water', lat: -54.88, lon: -35.12 },
    ],
  },
  prydz_bay: {
    displayName: 'Prydz Bay',
    locations: [
      { label: 'Bharati Station (India)', lat: -69.375, lon: 76.125, note: '~5 km from the real station' },
      { label: 'Prydz Bay iceberg zone (D23)', lat: -69.625, lon: 74.875 },
      { label: 'Open water, north of the bay', lat: -60.875, lon: 70.0 },
    ],
  },
  ross_sea: {
    displayName: 'Ross Sea',
    locations: [
      { label: 'McMurdo Station (USA/NZ)', lat: -77.375, lon: 166.125, note: '~55 km from the real station' },
      { label: 'Ross Sea open water', lat: -67.875, lon: 175.125 },
    ],
  },
}

export const DEFAULT_REGION_INFO = {
  displayName: 'this domain',
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
