import { fmtKm, fmtPct, fmtDateTime } from '../../format'

/**
 * The "direct route" is a straight geometric line, shown ONLY as a
 * reference for how much detour the real route costs -- it's never a
 * real candidate, since it ignores every obstacle. When it crosses
 * infeasible cells (too much ice / too shallow for this vessel), that's
 * the expected, common case, not an error -- rationale() below makes
 * that explicit instead of leaving a viewer to infer it from a null
 * risk-reduction number.
 */
function rationale(optimized, naive) {
  const detourKm = optimized.distance_km - naive.distance_km
  const detourPhrase = detourKm > 1
    ? `adding ${fmtKm(detourKm)}`
    // The "direct line" is great-circle straight-line distance; the
    // optimized route (summed over real grid-cell hops) can occasionally
    // come out shorter, not just longer -- say so plainly rather than
    // imply a detour that didn't happen.
    : detourKm < -1
      ? `and is actually ${fmtKm(Math.abs(detourKm))} shorter`
      : 'at essentially the same distance'
  if (naive.infeasible_cells_crossed > 0) {
    return `The direct line isn't a real option here -- it crosses ${naive.infeasible_cells_crossed} `
      + `cell${naive.infeasible_cells_crossed === 1 ? '' : 's'} this vessel can't safely enter (too much ice or `
      + `too shallow). The optimized route is the actual safe path, ${detourPhrase} to stay clear of it.`
  }
  if (detourKm > 1) {
    return `Both routes are physically passable; the optimized route adds ${fmtKm(detourKm)} to reduce real `
      + `ice/iceberg risk exposure along the way.`
  }
  return 'Conditions along the direct line are already low-risk, so the optimized route stays close to it.'
}

export default function SummaryHeader({ report, onPlanAnother }) {
  const { optimized, naive, risk_reduction_pct: riskReduction } = report.route_comparison
  const profile = report.ice_class_profile

  return (
    <header className="summary-header">
      <p className="route-rationale">{rationale(optimized, naive)}</p>
      <div className="summary-readouts">
        <div className="readout">
          <span className="readout-label">Distance</span>
          <span className="readout-value">{fmtKm(optimized.distance_km)}</span>
          <span className="readout-sub">
            direct line: {fmtKm(naive.distance_km)}{naive.infeasible_cells_crossed > 0 ? ' (not navigable)' : ''}
          </span>
        </div>
        <div className="readout">
          <span className="readout-label">ETA</span>
          <span className="readout-value readout-value--sm">{fmtDateTime(optimized.eta)}</span>
        </div>
        <div className="readout readout--accent">
          <span className="readout-label">Risk reduction vs. direct route</span>
          <span className="readout-value">
            {riskReduction === null
              ? 'n/a'
              : riskReduction >= 0
                ? `${fmtPct(riskReduction, 1)} lower`
                : `${fmtPct(Math.abs(riskReduction), 1)} higher`}
          </span>
          <span className="readout-sub">
            {riskReduction === null
              ? 'direct route is not navigable, so there is nothing to compare a risk score against'
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
