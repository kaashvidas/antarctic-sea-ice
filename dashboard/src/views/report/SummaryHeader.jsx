import { fmtKm, fmtPct, fmtDateTime } from '../../format'

export default function SummaryHeader({ report, onPlanAnother }) {
  const { optimized, naive, risk_reduction_pct: riskReduction } = report.route_comparison
  const profile = report.ice_class_profile

  return (
    <header className="summary-header">
      <div className="summary-readouts">
        <div className="readout">
          <span className="readout-label">Distance</span>
          <span className="readout-value">{fmtKm(optimized.distance_km)}</span>
          <span className="readout-sub">direct route: {fmtKm(naive.distance_km)}</span>
        </div>
        <div className="readout">
          <span className="readout-label">ETA</span>
          <span className="readout-value readout-value--sm">{fmtDateTime(optimized.eta)}</span>
        </div>
        <div className="readout readout--accent">
          <span className="readout-label">Risk reduction vs. direct route</span>
          <span className="readout-value">
            {riskReduction === null
              ? 'not computed'
              : riskReduction >= 0
                ? `${fmtPct(riskReduction, 1)} lower`
                : `${fmtPct(Math.abs(riskReduction), 1)} higher`}
          </span>
          <span className="readout-sub">
            {riskReduction === null
              ? 'direct route crosses infeasible cells; scores not comparable'
              : 'ice / iceberg risk exposure of the optimized route vs. the naive one'}
          </span>
        </div>
        <div className="readout">
          <span className="readout-label">Ice class</span>
          <span className="readout-value readout-value--sm">{profile.label}</span>
          <span className="readout-sub">
            {profile.hard_infeasible_concentration > profile.max_safe_concentration
              ? `cautious beyond ${fmtPct(profile.max_safe_concentration * 100)} · hard limit ${fmtPct(profile.hard_infeasible_concentration * 100)}`
              : `max safe concentration ${fmtPct(profile.max_safe_concentration * 100)}`}
          </span>
        </div>
      </div>
      <button type="button" className="btn-secondary" onClick={onPlanAnother}>Plan another journey</button>
    </header>
  )
}
