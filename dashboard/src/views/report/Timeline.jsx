import { fmtDate, vectorToSpeedDir, seaIceConfidence } from '../../format'

/**
 * Day-by-day drift-trajectory timeline: one entry per day_by_day item.
 * Clicking an entry drives the shared selectedDay state (map overlay,
 * weather panel). Entries past the forecast horizon carry a `note`
 * instead of numeric fields — shown distinctly, not silently dropped.
 */
export default function Timeline({ dayByDay, selectedDay, onSelectDay }) {
  return (
    <div className="panel timeline-panel">
      <h2 className="panel-title">Day-by-day timeline</h2>
      <div className="timeline-track">
        {dayByDay.map((d) => {
          const isSelected = d.day === selectedDay
          if (d.note) {
            return (
              <button
                type="button"
                key={d.day}
                className={`timeline-item timeline-item--note${isSelected ? ' selected' : ''}`}
                onClick={() => onSelectDay(d.day)}
              >
                <span className="timeline-day">Day {d.day}+</span>
                <span className="timeline-note">Beyond forecast horizon</span>
              </button>
            )
          }
          const meanPct = (d.mean_seaice_concentration ?? 0) * 100
          const { speed, compass } = vectorToSpeedDir(d.wind_u_ms, d.wind_v_ms)
          const conf = seaIceConfidence(d.seaice_mae_this_lead_day)
          return (
            <button
              type="button"
              key={d.day}
              className={`timeline-item${isSelected ? ' selected' : ''}`}
              onClick={() => onSelectDay(d.day)}
            >
              <span className="timeline-day">
                Day {d.day}
                {conf && (
                  <span
                    className={`timeline-confidence-dot timeline-confidence-dot--${conf.short}`}
                    title={`Sea-ice forecast: ${conf.text} (measured error ±${(d.seaice_mae_this_lead_day * 100).toFixed(1)} pts)`}
                  />
                )}
              </span>
              <span className="timeline-date">{fmtDate(d.date)}</span>
              <div className="timeline-mini-gauge">
                <div className="timeline-mini-gauge-fill" style={{ width: `${meanPct}%` }} />
              </div>
              <span className="timeline-mini-label">{meanPct.toFixed(0)}% ice</span>
              <span className="timeline-mini-label">{speed.toFixed(1)} m/s {compass} wind</span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
