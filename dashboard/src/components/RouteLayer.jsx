import { Polyline, CircleMarker, Tooltip } from 'react-leaflet'

/**
 * Draws the optimized (solid cyan) vs naive (dashed red) route from a
 * plan_journey response's route_comparison paths — plain {lat,lon}[]
 * arrays, not GeoJSON. Deliberately distinct styles per the legend so the
 * comparison reads at a glance.
 */
export default function RouteLayer({ optimizedPath, naivePath, start, goal }) {
  const toPositions = (path) => (path || []).map((p) => [p.lat, p.lon])

  return (
    <>
      {naivePath && (
        <Polyline
          positions={toPositions(naivePath)}
          pathOptions={{ color: '#d1554a', weight: 3, opacity: 0.85, dashArray: '9,7' }}
        >
          <Tooltip sticky>Naive route (direct line)</Tooltip>
        </Polyline>
      )}
      {optimizedPath && (
        <Polyline
          positions={toPositions(optimizedPath)}
          pathOptions={{ color: '#34c3b8', weight: 4, opacity: 0.95 }}
        >
          <Tooltip sticky>Optimized route (ice-avoiding)</Tooltip>
        </Polyline>
      )}
      {start && (
        <CircleMarker center={[start.lat, start.lon]} radius={6} pathOptions={{ color: '#fff', weight: 2, fillColor: '#34c3b8', fillOpacity: 1 }}>
          <Tooltip direction="top" offset={[0, -6]}>Start</Tooltip>
        </CircleMarker>
      )}
      {goal && (
        <CircleMarker center={[goal.lat, goal.lon]} radius={6} pathOptions={{ color: '#fff', weight: 2, fillColor: '#d1554a', fillOpacity: 1 }}>
          <Tooltip direction="top" offset={[0, -6]}>Destination</Tooltip>
        </CircleMarker>
      )}
    </>
  )
}
