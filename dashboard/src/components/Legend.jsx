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
          <span className="legend-swatch dot" style={{ background: 'var(--accent-blue)', opacity: 0.25, border: 'none', width: 14, height: 14 }} />
          <span>Drift uncertainty (grows with lead day, from the real perturbed-ensemble spread)</span>
        </div>
        <div className="legend-row">
          <span className="legend-swatch dot warn" style={{ background: 'var(--accent-red)' }} />
          <span>Close-approach warning</span>
        </div>
      </div>

      <div className="legend-section">
        <div className="legend-label">Sea-ice concentration</div>
        <div className="legend-gradient-bar" />
        <div className="legend-gradient-labels">
          <span>0% (open water)</span>
          <span>100% (dense ice)</span>
        </div>
      </div>
    </div>
  )
}
