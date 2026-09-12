export default function DaySlider({
  day,
  maxDay,
  onChange,
  forecastDate,
  showSeaIce,
  onToggleSeaIce,
  seaIceOpacity,
  onOpacityChange,
}) {
  const pct = maxDay === 0 ? 0 : (day / maxDay) * 100

  const dateLabel = (() => {
    if (!forecastDate) return null
    const base = new Date(`${forecastDate}T00:00:00Z`)
    if (Number.isNaN(base.getTime())) return null
    base.setUTCDate(base.getUTCDate() + day)
    return base.toISOString().slice(0, 10)
  })()

  return (
    <div className="day-control">
      <div className="day-control-top">
        <span className="day-control-label">
          Sea-ice forecast &mdash; Day {day} of {maxDay}
        </span>
        {dateLabel && <span className="day-control-date">{dateLabel}</span>}
      </div>

      <div className="day-control-row">
        <button
          type="button"
          className="day-control-btn"
          onClick={() => onChange(Math.max(0, day - 1))}
          disabled={day <= 0}
          aria-label="Previous day"
        >
          ‹
        </button>
        <input
          type="range"
          className="day-slider"
          min={0}
          max={maxDay}
          step={1}
          value={day}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{ '--pct': `${pct}%` }}
          aria-label="Forecast day"
        />
        <button
          type="button"
          className="day-control-btn"
          onClick={() => onChange(Math.min(maxDay, day + 1))}
          disabled={day >= maxDay}
          aria-label="Next day"
        >
          ›
        </button>
      </div>

      <div className="day-control-ticks">
        {Array.from({ length: maxDay + 1 }, (_, i) => (
          <span key={i}>{i}</span>
        ))}
      </div>

      <div className="day-control-footer">
        <label className="seaice-toggle">
          <input
            type="checkbox"
            checked={showSeaIce}
            onChange={(e) => onToggleSeaIce(e.target.checked)}
          />
          Sea-ice overlay
        </label>
        <label className="seaice-opacity">
          Opacity
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={seaIceOpacity}
            onChange={(e) => onOpacityChange(Number(e.target.value))}
            disabled={!showSeaIce}
          />
        </label>
      </div>
    </div>
  )
}
