import { Fragment } from 'react'
import { CircleMarker, Polyline, Popup, Tooltip } from 'react-leaflet'
import { colorForIceberg } from '../icebergColors'

/**
 * Renders each iceberg from a plan_journey response's `icebergs` array:
 * current position marker, full predicted_track as a line, and a visually
 * distinct treatment (red ring + pulsing tooltip) for any iceberg flagged
 * warning: true — those are the closest-approach safety cases.
 */
export default function IcebergLayer({ icebergs }) {
  if (!icebergs || icebergs.length === 0) return null
  const ids = icebergs.map((b) => b.iceberg_id)

  return (
    <>
      {icebergs.map((berg) => {
        const color = colorForIceberg(berg.iceberg_id, ids)
        const track = (berg.predicted_track || []).map((p) => [p.lat, p.lon])
        return (
          <Fragment key={berg.iceberg_id}>
            {track.length > 1 && (
              <Polyline positions={track} pathOptions={{ color, weight: 2, opacity: 0.8, dashArray: berg.warning ? undefined : '2,4' }}>
                <Tooltip sticky>{berg.iceberg_id} — predicted track</Tooltip>
              </Polyline>
            )}
            <CircleMarker
              center={[berg.current_position.lat, berg.current_position.lon]}
              radius={berg.warning ? 9 : 7}
              pathOptions={{
                color: berg.warning ? '#d1554a' : '#ffffff',
                weight: berg.warning ? 3 : 2,
                fillColor: color,
                fillOpacity: 1,
              }}
            >
              <Tooltip direction="top" offset={[0, -6]}>
                {berg.iceberg_id}{berg.warning ? ' ⚠ warning' : ''}
              </Tooltip>
              <Popup className="iceberg-popup">
                <h4>Iceberg {berg.iceberg_id}{berg.warning ? ' — CLOSE APPROACH' : ''}</h4>
                <table>
                  <tbody>
                    <tr><td>Length</td><td className="value">{(berg.length_m / 1000).toFixed(1)} km</td></tr>
                    <tr><td>Width</td><td className="value">{(berg.width_m / 1000).toFixed(1)} km</td></tr>
                    <tr><td>Thickness</td><td className="value">{berg.thickness_m.toFixed(0)} m*</td></tr>
                    {berg.closest_approach_km != null && (
                      <tr><td>Closest approach</td><td className="value">{berg.closest_approach_km} km (day {berg.closest_approach_day})</td></tr>
                    )}
                  </tbody>
                </table>
                {berg.is_placeholder_thickness && <p className="popup-note">*assumed constant, not measured</p>}
              </Popup>
            </CircleMarker>
          </Fragment>
        )
      })}
    </>
  )
}
