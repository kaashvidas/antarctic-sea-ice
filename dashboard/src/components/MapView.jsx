import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import SeaIceOverlay from './SeaIceOverlay'
import IcebergLayer from './IcebergLayer'
import RouteLayer from './RouteLayer'

// Standard OSM raster tiles: no API key required (CARTO's free basemap
// tiles now return an "API key required" watermark without one — verified
// by curl during development, so this avoids that dead end). A CSS filter
// darkens/desaturates the tiles so the colored route/iceberg overlays still
// read clearly against a professional-looking chart rather than a bright
// generic web map.
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
  icebergIds,
  routesGeoJSON,
  seaIceUrl,
  showSeaIce,
  seaIceOpacity,
}) {
  const center = bounds
    ? [
        (bounds[0][0] + bounds[1][0]) / 2,
        (bounds[0][1] + bounds[1][1]) / 2,
      ]
    : [-61, -47.5]

  return (
    <MapContainer
      className="app-map"
      center={center}
      zoom={5}
      minZoom={3}
      maxZoom={10}
    >
      <TileLayer
        url={TILE_URL}
        attribution={TILE_ATTRIBUTION}
        className="basemap-tiles"
      />
      {bounds && <FitToBounds bounds={bounds} />}

      <SeaIceOverlay
        url={seaIceUrl}
        bounds={bounds}
        opacity={seaIceOpacity}
        visible={showSeaIce}
      />

      <RouteLayer routesGeoJSON={routesGeoJSON} />
      <IcebergLayer routesGeoJSON={routesGeoJSON} icebergIds={icebergIds} />
    </MapContainer>
  )
}
