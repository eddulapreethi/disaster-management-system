import test from 'node:test'
import assert from 'node:assert/strict'

import {
  GEOJSON_LAYERS,
  GEOJSON_LAYER_STYLES,
  INITIAL_GEOJSON_VISIBILITY,
  parseGeoJsonFeatureCollection,
} from '../src/maps/geoJsonLayers.js'

test('GIS overlay allowlist has six independently toggleable reference layers', () => {
  assert.deepEqual(
    GEOJSON_LAYERS.map(layer => layer.key),
    ['administrative_boundaries', 'rivers', 'watersheds', 'lakes', 'land_use', 'roads'],
  )
  assert.deepEqual(Object.keys(INITIAL_GEOJSON_VISIBILITY), GEOJSON_LAYERS.map(layer => layer.key))
  assert.ok(Object.values(INITIAL_GEOJSON_VISIBILITY).every(visible => visible === false))
  assert.ok(GEOJSON_LAYERS.filter(layer => layer.heavy).every(layer => !INITIAL_GEOJSON_VISIBILITY[layer.key]))
  assert.deepEqual(Object.keys(GEOJSON_LAYER_STYLES).sort(), GEOJSON_LAYERS.map(layer => layer.key).sort())
})

test('GIS response parser accepts FeatureCollections and rejects other payloads', () => {
  const collection = { type: 'FeatureCollection', features: [] }
  assert.equal(parseGeoJsonFeatureCollection(collection), collection)
  assert.throws(
    () => parseGeoJsonFeatureCollection({ type: 'Feature', geometry: null }),
    /GeoJSON FeatureCollection/,
  )
})
