export default function Legend() {
  return (
    <div className="legend">
      <h3>Legend</h3>

      <div className="legend-section">
        <div className="legend-row">
          <span
            className="legend-swatch line"
            style={{ borderTopColor: '#37d67a' }}
          />
          <span>Optimized route (ice-avoiding)</span>
        </div>
        <div className="legend-row">
          <span
            className="legend-swatch line dashed"
            style={{ borderTopColor: '#ff5c5c' }}
          />
          <span>Naive route (straight line)</span>
        </div>
      </div>

      <div className="legend-section">
        <div className="legend-row">
          <span
            className="legend-swatch dot"
            style={{ background: '#4dabf7' }}
          />
          <span>Iceberg — current position</span>
        </div>
        <div className="legend-row">
          <span
            className="legend-swatch line"
            style={{ borderTopColor: '#4dabf7', borderTopWidth: 2 }}
          />
          <span>Predicted 7-day drift track</span>
        </div>
        <div className="legend-row">
          <span className="legend-swatch area" />
          <span>Drift uncertainty (ensemble spread)</span>
        </div>
      </div>
    </div>
  )
}
