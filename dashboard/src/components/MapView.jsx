import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import SeaIceOverlay from './SeaIceOverlay'
import IcebergLayer from './IcebergLayer'
import RouteLayer from './RouteLayer'

// Standard OSM raster tiles: no API key required. A CSS filter darkens/
// desaturates the tiles so the colored route/iceberg overlays read clearly
// against a professional-looking chart rather than a bright generic web map.
const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

function FitToBounds({ bounds }) {
  const map = useMap()
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [20, 20] })
  }, [bounds, map])
  return null
}

export default function MapView({
  bounds,
  optimizedPath,
  naivePath,
  start,
  goal,
  icebergs,
  seaIceUrl,
  showSeaIce,
  seaIceOpacity,
  siteMarkers = [],
}) {
  const center = bounds
    ? [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
    : [-61, -47.5]

  return (
    <MapContainer className="app-map" center={center} zoom={5} minZoom={3} maxZoom={10}>
      <TileLayer url={TILE_URL} attribution={TILE_ATTRIBUTION} className="basemap-tiles" />
      {bounds && <FitToBounds bounds={bounds} />}

      <SeaIceOverlay url={seaIceUrl} bounds={bounds} opacity={seaIceOpacity} visible={showSeaIce} />

      <RouteLayer optimizedPath={optimizedPath} naivePath={naivePath} start={start} goal={goal} />
      {siteMarkers.map((site) => (
        <CircleMarker
          key={site.id}
          center={[site.lat, site.lon]}
          radius={site.kind === 'research_station' ? 5 : 6}
          pathOptions={{
            color: site.navigable ? '#7bdff2' : '#f2c14e',
            weight: 2,
            fillColor: '#14232d',
            fillOpacity: 0.9,
          }}
        >
          <Tooltip direction="right" offset={[7, 0]}>{site.label}</Tooltip>
        </CircleMarker>
      ))}
      <IcebergLayer icebergs={icebergs} />
    </MapContainer>
  )
}
