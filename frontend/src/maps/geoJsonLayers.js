export const GEOJSON_LAYERS = Object.freeze([
  { key: 'administrative_boundaries', label: 'Administrative boundaries', heavy: false },
  { key: 'rivers', label: 'Rivers', heavy: false },
  { key: 'watersheds', label: 'Watersheds (HydroSHEDS)', heavy: false },
  { key: 'lakes', label: 'Lakes', heavy: true },
  { key: 'land_use', label: 'Land use', heavy: true },
  { key: 'roads', label: 'Roads (largest layer)', heavy: true },
])

export const INITIAL_GEOJSON_VISIBILITY = Object.freeze(
  Object.fromEntries(GEOJSON_LAYERS.map(layer => [layer.key, false])),
)

export const GEOJSON_LAYER_STYLES = Object.freeze({
  administrative_boundaries: {
    color: '#667085',
    weight: 1.4,
    fillOpacity: 0.02,
  },
  rivers: {
    color: '#168aad',
    weight: 1.5,
  },
  watersheds: {
    color: '#6b8e63',
    weight: 1.3,
    dashArray: '4 3',
    fillColor: '#93ad7f',
    fillOpacity: 0.06,
  },
  lakes: {
    color: '#2788a5',
    weight: 0.5,
    fillColor: '#3ba3bd',
    fillOpacity: 0.2,
  },
  land_use: {
    color: '#87934e',
    weight: 0.35,
    fillColor: '#a9b96a',
    fillOpacity: 0.12,
  },
  roads: {
    color: '#8a7563',
    weight: 0.55,
  },
})

export function parseGeoJsonFeatureCollection(value) {
  if (
    !value
    || value.type !== 'FeatureCollection'
    || !Array.isArray(value.features)
  ) {
    throw new Error('GIS layer response was not a GeoJSON FeatureCollection.')
  }
  return value
}
