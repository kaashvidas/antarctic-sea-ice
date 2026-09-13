export default function Legend() {
  return (
    <div className="legend">
      <h3>Legend</h3>

      <div className="legend-section">
        <div className="legend-row">
          <span className="legend-swatch line" style={{ borderTopColor: 'var(--accent-cyan)' }} />
          <span>Optimized route (ice-avoiding)</span>
        </div>
        <div className="legend-row">
          <span className="legend-swatch line dashed" style={{ borderTopColor: 'var(--accent-red)' }} />
          <span>Naive route (direct line)</span>
        </div>
      </div>

      <div className="legend-section">
        <div className="legend-row">
          <span className="legend-swatch dot" style={{ background: 'var(--accent-blue)' }} />
          <span>Iceberg — current position</span>
        </div>
        <div className="legend-row">
          <span className="legend-swatch line" style={{ borderTopColor: 'var(--accent-blue)', borderTopWidth: 2 }} />
          <span>Predicted drift track</span>
        </div>
        <div className="legend-row">
          <span className="legend-swatch dot warn" style={{ background: 'var(--accent-red)' }} />
          <span>Close-approach warning</span>
        </div>
      </div>
    </div>
  )
}
