export default function WarningsPanel({ icebergs }) {
  const warnings = (icebergs || []).filter((b) => b.warning)

  if (warnings.length === 0) {
    return (
      <div className="warnings-panel warnings-panel--clear">
        <span className="warnings-tag ok">CLEAR</span>
        <span>No close-approach warnings for this route — all tracked icebergs stay outside the {50} km threshold.</span>
      </div>
    )
  }

  return (
    <div className="warnings-panel warnings-panel--alert" role="alert">
      <span className="warnings-tag alert">⚠ {warnings.length} WARNING{warnings.length > 1 ? 'S' : ''}</span>
      <div className="warnings-list">
        {warnings.map((b) => (
          <div className="warning-row" key={b.iceberg_id}>
            <strong>{b.iceberg_id}</strong>
            <span>closest approach {b.closest_approach_km} km on day {b.closest_approach_day}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
