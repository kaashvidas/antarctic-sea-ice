import { colorForIceberg } from '../../icebergColors'

/**
 * One card per tracked iceberg -- real USNIC length/width and real WDE17
 * drift-ensemble uncertainty only. No thickness field: no public dataset
 * gives real per-iceberg thickness for this cluster (an exhaustive real
 * ICESat-2 search came up empty), and this project doesn't display a
 * literature estimate as if it were data -- see src/integration/pipeline.py's
 * comment on _UNUSED_THICKNESS_M for why the physics engine's internal
 * IcebergState still carries an unused placeholder value that never
 * reaches here.
 */
export default function IcebergPanel({ icebergs }) {
  if (!icebergs || icebergs.length === 0) return null
  const ids = icebergs.map((b) => b.iceberg_id)

  return (
    <div className="panel iceberg-panel">
      <h2 className="panel-title">Tracked icebergs</h2>
      <div className="iceberg-cards">
        {icebergs.map((b) => {
          const color = colorForIceberg(b.iceberg_id, ids)
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
            </div>
          )
        })}
      </div>
    </div>
  )
}
