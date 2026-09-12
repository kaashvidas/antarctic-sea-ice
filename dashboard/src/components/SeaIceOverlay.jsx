import { ImageOverlay } from 'react-leaflet'

/**
 * Renders one georeferenced day_NN.png as a Leaflet ImageOverlay covering
 * exactly the manifest's bounds. All days currently serve the same
 * (disclosed) placeholder image — that's expected, not a bug here.
 */
export default function SeaIceOverlay({ url, bounds, opacity, visible }) {
  if (!visible || !url) return null
  return <ImageOverlay url={url} bounds={bounds} opacity={opacity} zIndex={200} />
}
