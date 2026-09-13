/**
 * Honesty banner driven entirely by report.disclosure.data_sources (see
 * src/integration/journey_report.py's plan_journey return value) — one
 * line per data source stating what it actually is (real observation,
 * real forecast, or placeholder), never hardcoded, so it can't drift out
 * of sync with the backend as sources get swapped in over time.
 */
export default function DisclosureBanner({ dataSources, note, compact = false }) {
  if (!dataSources) return null
  const entries = Object.values(dataSources)
  if (entries.length === 0) return null

  return (
    <div className={`disclosure-banner${compact ? ' compact' : ''}`} role="status">
      {entries.map((entry) => (
        <div className="disclosure-row" key={entry.variable}>
          <span className={`disclosure-tag ${entry.is_real_data ? 'disclosure-tag--real' : ''}`}>
            {entry.is_real_data
              ? entry.is_true_forecast ? 'Real forecast' : 'Real observation'
              : 'Placeholder'}
          </span>
          <span className="disclosure-text">
            <strong>{entry.variable.replace(/_/g, ' ')}</strong>: {entry.source}
            {entry.observation_date ? ` (observed ${entry.observation_date})` : null}
            {entry.method ? ` — ${entry.method}` : null}
          </span>
        </div>
      ))}
      {note ? <div className="disclosure-note">{note}</div> : null}
    </div>
  )
}
