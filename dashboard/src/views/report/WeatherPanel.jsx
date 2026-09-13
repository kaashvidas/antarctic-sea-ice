import { vectorToSpeedDir, fmtDate } from '../../format'

function VectorIndicator({ label, u, v, unit }) {
  const { speed, bearingDeg, compass } = vectorToSpeedDir(u, v)
  return (
    <div className="vector-indicator">
      <span className="vector-label">{label}</span>
      <span className="vector-arrow" style={{ transform: `rotate(${bearingDeg}deg)` }} aria-hidden="true">↑</span>
      <span className="vector-value">{speed.toFixed(1)} {unit} <span className="vector-compass">{compass}</span></span>
    </div>
  )
}

/**
 * Conditions for the currently-selected day (shared selection with the
 * timeline / map day slider). Sea-ice and wind/current each carry their
 * own real-data flag now (day.seaice_is_real_data / day.forcing_is_real_data)
 * rather than one blanket placeholder tag — sea-ice is a real satellite
 * observation persisted forward (not a trained forecast), wind/current is
 * a real multi-day forecast. Tags reflect whichever is actually true for
 * this response instead of assuming everything is a stand-in.
 */
export default function WeatherPanel({ day }) {
  if (!day) return null

  if (day.note) {
    return (
      <div className="panel weather-panel">
        <h2 className="panel-title">Conditions</h2>
        <p className="beyond-horizon-note">{day.note}</p>
      </div>
    )
  }

  const meanPct = (day.mean_seaice_concentration ?? 0) * 100
  const maxPct = (day.max_seaice_concentration ?? 0) * 100

  return (
    <div className="panel weather-panel">
      <div className="panel-title-row">
        <h2 className="panel-title">Conditions — day {day.day}</h2>
      </div>
      <div className="weather-date">{fmtDate(day.date)}</div>

      <div className="ice-gauge">
        <div className="ice-gauge-labels">
          <span>
            Sea-ice concentration{' '}
            <span className={`tag ${day.seaice_is_real_data ? 'tag--real' : 'tag--placeholder'}`}>
              {day.seaice_is_real_data ? 'real satellite obs., persisted' : 'placeholder'}
            </span>
          </span>
          <span>{meanPct.toFixed(0)}% mean · {maxPct.toFixed(0)}% max</span>
        </div>
        <div className="ice-gauge-track">
          <div className="ice-gauge-fill mean" style={{ width: `${meanPct}%` }} />
          <div className="ice-gauge-marker" style={{ left: `${maxPct}%` }} title="max" />
        </div>
      </div>

      <div className="vector-row-title">
        Wind &amp; current{' '}
        <span className={`tag ${day.forcing_is_real_data ? 'tag--real' : 'tag--placeholder'}`}>
          {day.forcing_is_real_data ? 'real forecast' : 'placeholder'}
        </span>
      </div>
      <div className="vector-row">
        <VectorIndicator label="Wind" u={day.wind_u_ms} v={day.wind_v_ms} unit="m/s" />
        <VectorIndicator label="Current" u={day.current_u_ms} v={day.current_v_ms} unit="m/s" />
      </div>
    </div>
  )
}
