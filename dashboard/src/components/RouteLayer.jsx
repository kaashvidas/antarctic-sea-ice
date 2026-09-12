import { Polyline, Tooltip } from 'react-leaflet'
import { toLatLngs } from '../geoutils'

/**
 * Renders the two route LineString features from /api/routes, distinguished
 * by properties.route_type ("optimized" | "naive"). This comparison is the
 * core demo moment, so the two must read as obviously different at a glance.
 */
export default function RouteLayer({ routesGeoJSON }) {
  if (!routesGeoJSON) return null

  const features = routesGeoJSON.features.filter(
    (f) => f.properties?.route_type === 'optimized' || f.properties?.route_type === 'naive',
  )

  return (
    <>
      {features.map((f, i) => {
        const isOptimized = f.properties.route_type === 'optimized'
        const positions = toLatLngs(f.geometry.coordinates)
        return (
          <Polyline
            key={`route-${i}`}
            positions={positions}
            pathOptions={
              isOptimized
                ? { color: '#37d67a', weight: 4, opacity: 0.95 }
                : {
                    color: '#ff5c5c',
                    weight: 3,
                    opacity: 0.85,
                    dashArray: '10,7',
                  }
            }
          >
            <Tooltip sticky>
              {isOptimized ? 'Optimized route (ice-avoiding)' : 'Naive route (straight line)'}
            </Tooltip>
          </Polyline>
        )
      })}
    </>
  )
}
