// Named quick-select locations per region, so choosing a start/destination
// doesn't require knowing or guessing valid lat/lon by hand. Every
// coordinate here was verified via a real plan_journey() call during
// development (not guessed) -- see PROJECT_STATUS.md / tests/
// test_journey_report.py's _REGION_TEST_FIXTURES for the same verified
// pairs. Keep these two in sync if a region's fixture coordinates change.
export const REGION_INFO = {
  weddell: {
    displayName: 'Weddell Sea',
    locations: [
      { label: 'Iceberg cluster edge (D32/D33)', lat: -58.88, lon: -51.12 },
      { label: 'Northeast approach', lat: -54.88, lon: -35.12 },
    ],
  },
  prydz_bay: {
    displayName: 'Prydz Bay (near Bharati)',
    locations: [
      { label: 'Bharati approach', lat: -60.875, lon: 70.0 },
      { label: 'Prydz Bay iceberg zone (D23)', lat: -69.625, lon: 74.875 },
    ],
  },
  ross_sea: {
    displayName: 'Ross Sea (near McMurdo)',
    locations: [
      { label: 'McMurdo Sound', lat: -77.375, lon: 166.125 },
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
