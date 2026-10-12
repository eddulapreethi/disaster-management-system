import test from 'node:test'
import assert from 'node:assert/strict'

import { alertLocation, alertTimestamp } from '../src/services/alertPresentation.js'
import { simulationMeasurements } from '../src/services/simulationService.js'

test('simulation forwards real zero weather measurements without substituting defaults', () => {
  assert.deepEqual(
    simulationMeasurements({ precipitationMm: 0, temperatureC: 0, windKmh: 0 }),
    { rainfall_mm: 0, temperature_c: 0, wind_speed_kmh: 0 },
  )
})

test('simulation rejects unavailable or non-finite weather instead of defaulting it', () => {
  assert.throws(
    () => simulationMeasurements({ precipitationMm: null, temperatureC: 25, windKmh: Number.NaN }),
    /rainfall_mm, wind_speed_kmh unavailable/,
  )
})

test('alert card fields match the persisted API alert schema', () => {
  const alert = {
    latitude: 9.9312,
    longitude: 76.2673,
    created_at: '2026-10-11T10:00:00Z',
  }
  assert.equal(alertLocation(alert), '9.9312, 76.2673')
  assert.equal(alertTimestamp(alert), new Date(alert.created_at).toLocaleString())
})

test('alerts without coordinates or valid timestamps render an explicit unavailable state', () => {
  assert.equal(alertLocation({ latitude: null, longitude: null }), 'Location unavailable')
  assert.equal(alertTimestamp({ created_at: 'not-a-date' }), 'Timestamp unavailable')
})
