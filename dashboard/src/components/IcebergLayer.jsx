import { Fragment } from 'react'
import { CircleMarker, Polygon, Polyline, Popup, Tooltip } from 'react-leaflet'
import { convexHull, toLatLng, toLatLngs } from '../geoutils'
import { colorForIceberg } from '../icebergColors'

/**
 * Renders the 6 tracked icebergs from /api/routes:
 *  - iceberg_current      -> solid circle marker (current real position)
 *  - iceberg_predicted_track -> thin solid line (center-member 7-day drift)
 *  - iceberg_drift_cone    -> light translucent hull (ensemble day-7 spread)
 * All three share one color per iceberg id so they read as "the same berg"
 * while remaining visually distinct from each other by shape/style.
 */
export default function IcebergLayer({ routesGeoJSON, icebergIds }) {
  if (!routesGeoJSON) return null

  const byId = {}
  for (const id of icebergIds) {
    byId[id] = { current: null, track: null, cone: null }
  }

  for (const f of routesGeoJSON.features) {
    const p = f.properties || {}
    const id = p.iceberg_id
    if (!id || !byId[id]) continue
    if (p.feature_type === 'iceberg_current') byId[id].current = f
    else if (p.feature_type === 'iceberg_predicted_track') byId[id].track = f
    else if (p.feature_type === 'iceberg_drift_cone') byId[id].cone = f
  }

  return (
    <>
      {icebergIds.map((id) => {
        const entry = byId[id]
        const color = colorForIceberg(id, icebergIds)
        if (!entry) return null

        return (
          <Fragment key={id}>
            {entry.cone && <DriftCone feature={entry.cone} color={color} />}
            {entry.track && <PredictedTrack feature={entry.track} color={color} />}
            {entry.current && (
              <CurrentPosition feature={entry.current} color={color} />
            )}
          </Fragment>
        )
      })}
    </>
  )
}

function CurrentPosition({ feature, color }) {
  const pos = toLatLng(feature.geometry.coordinates)
  const { iceberg_id: id, length_m: length, width_m: width } = feature.properties

  return (
    <CircleMarker
      center={pos}
      radius={7}
      pathOptions={{
        color: '#ffffff',
        weight: 2,
        fillColor: color,
        fillOpacity: 1,
      }}
    >
      <Tooltip direction="top" offset={[0, -6]}>
        {id}
      </Tooltip>
      <Popup className="iceberg-popup">
        <h4>Iceberg {id}</h4>
        <table>
          <tbody>
            <tr>
              <td>Length</td>
              <td className="value">{(length / 1000).toFixed(1)} km</td>
            </tr>
            <tr>
              <td>Width</td>
              <td className="value">{(width / 1000).toFixed(1)} km</td>
            </tr>
            <tr>
              <td>Position</td>
              <td className="value">
                {pos[0].toFixed(2)}, {pos[1].toFixed(2)}
              </td>
            </tr>
          </tbody>
        </table>
      </Popup>
    </CircleMarker>
  )
}

function PredictedTrack({ feature, color }) {
  const positions = toLatLngs(feature.geometry.coordinates)
  return (
    <Polyline
      positions={positions}
      pathOptions={{ color, weight: 2, opacity: 0.85 }}
    >
      <Tooltip sticky>{feature.properties.iceberg_id} — predicted 7-day track</Tooltip>
    </Polyline>
  )
}

function DriftCone({ feature, color }) {
  const points = toLatLngs(feature.geometry.coordinates)
  const hull = points.length >= 3 ? convexHull(points) : points

  return (
    <Polygon
      positions={hull}
      pathOptions={{
        color,
        weight: 1,
        dashArray: '3,4',
        fillColor: color,
        fillOpacity: 0.15,
      }}
    >
      <Tooltip sticky>
        {feature.properties.iceberg_id} — day-7 drift uncertainty (
        {feature.properties.n_ensemble_members} ensemble members)
      </Tooltip>
    </Polygon>
  )
}
