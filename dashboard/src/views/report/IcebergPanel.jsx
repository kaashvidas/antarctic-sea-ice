import { colorForIceberg } from '../../icebergColors'

/**
 * One card per tracked iceberg with a proportional thickness bar so the
 * relative scale across bergs is visible at a glance, not just numbers.
 * thickness_m is always a disclosed placeholder (is_placeholder_thickness),
 * so every card carries an explicit "assumed" tag rather than burying that
 * in fine print.
 */
export default function IcebergPanel({ icebergs }) {
  if (!icebergs || icebergs.length === 0) return null
  const ids = icebergs.map((b) => b.iceberg_id)
  const maxThickness = Math.max(...icebergs.map((b) => b.thickness_m), 1)

  return (
    <div className="panel iceberg-panel">
      <h2 className="panel-title">Tracked icebergs</h2>
      <div className="iceberg-cards">
        {icebergs.map((b) => {
          const color = colorForIceberg(b.iceberg_id, ids)
          const barPct = (b.thickness_m / maxThickness) * 100
          return (
            <div className={`iceberg-card${b.warning ? ' iceberg-card--warning' : ''}`} key={b.iceberg_id}>
              <div className="iceberg-card-head">
                <span className="iceberg-swatch" style={{ background: color }} />
                <span className="iceberg-id">{b.iceberg_id}</span>
                {b.warning && <span className="tag tag--danger">WARNING</span>}
              </div>
              <div className="iceberg-stats">
                <div className="iceberg-stat"><span>Length</span><strong>{(b.length_m / 1000).toFixed(1)} km</strong></div>
                <div className="iceberg-stat"><span>Width</span><strong>{(b.width_m / 1000).toFixed(1)} km</strong></div>
                <div className="iceberg-stat"><span>Drift uncertainty (day 7)</span><strong>{b.drift_uncertainty_radius_km_day7} km</strong></div>
              </div>
              <div className="thickness-row">
                <span className="thickness-label">Thickness</span>
                <div className="thickness-bar-track">
                  <div className="thickness-bar-fill" style={{ width: `${barPct}%`, background: color }} />
                </div>
                <span className="thickness-value">{b.thickness_m.toFixed(0)} m</span>
              </div>
              {b.is_placeholder_thickness && <span className="tag tag--placeholder">assumed constant, not measured</span>}
            </div>
          )
        })}
      </div>
    </div>
  )
}
