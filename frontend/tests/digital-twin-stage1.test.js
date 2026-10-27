import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

import {
  compareScenarios,
  createScenario,
  createTimelineState,
  FRAME_COUNT,
  illustrativeMarkerRadius,
  isWithinStudyArea,
  SCENARIO_PRESETS,
  STUDY_AREA,
  timelineReducer,
  validateScenarioInputs,
} from '../src/digitalTwin/scenarioEngine.js'
import {
  GEOJSON_LAYERS,
  GEOJSON_LAYER_STYLES,
  INITIAL_GEOJSON_VISIBILITY,
} from '../src/maps/geoJsonLayers.js'

const focus = { latitude: 9.95, longitude: 76.25 }

function scenario(name, rainfallIntensityMmPerHour, durationHours, initialRiverLevelM = null) {
  return createScenario({
    name,
    inputs: { rainfallIntensityMmPerHour, durationHours, initialRiverLevelM },
    focus,
  })
}

test('scenario inputs enforce finite values and documented bounds while allowing unknown river level', () => {
  assert.equal(validateScenarioInputs({
    rainfallIntensityMmPerHour: '0',
    durationHours: '1',
    initialRiverLevelM: '',
  }).valid, true)
  assert.equal(validateScenarioInputs({
    rainfallIntensityMmPerHour: '300',
    durationHours: '72',
    initialRiverLevelM: '30',
  }).valid, true)
  for (const invalid of [' ', 'NaN', 'Infinity', '-1', '301']) {
    assert.equal(validateScenarioInputs({
      rainfallIntensityMmPerHour: invalid,
      durationHours: '6',
      initialRiverLevelM: '',
    }).valid, false)
  }
  assert.equal(validateScenarioInputs({
    rainfallIntensityMmPerHour: '10',
    durationHours: '0',
    initialRiverLevelM: '',
  }).valid, false)
  assert.equal(validateScenarioInputs({
    rainfallIntensityMmPerHour: '10',
    durationHours: '6',
    initialRiverLevelM: '31',
  }).valid, false)
})

test('same inputs create identical, bounded frames and changed inputs change scenario outputs', () => {
  const first = scenario('Scenario A', 20, 6)
  const repeated = scenario('Scenario A', 20, 6)
  const changed = scenario('Scenario A', 50, 6)

  assert.deepEqual(first.frames, repeated.frames)
  assert.equal(first.frames.length, FRAME_COUNT)
  assert.equal(first.frames[0].scenarioRainfallAccumulatedMm, 0)
  assert.equal(first.frames.at(-1).scenarioRainfallAccumulatedMm, 120)
  assert.equal(changed.frames.at(-1).scenarioRainfallAccumulatedMm, 300)
  assert.ok(illustrativeMarkerRadius(changed.frames.at(-1)) > illustrativeMarkerRadius(first.frames.at(-1)))
  assert.ok(illustrativeMarkerRadius(changed.frames.at(-1)) <= 26)
})

test('optional initial river level is context only and missing values stay missing', () => {
  const scenarioWithoutLevel = scenario('Scenario A', 10, 2)
  const scenarioWithLevel = scenario('Scenario B', 10, 2, 4.2)

  assert.equal(scenarioWithoutLevel.inputs.initialRiverLevelM, null)
  assert.equal(scenarioWithLevel.inputs.initialRiverLevelM, 4.2)
  assert.deepEqual(scenarioWithoutLevel.frames, scenarioWithLevel.frames)
})

test('focus point must be within the documented Kochi GIS bounds', () => {
  assert.deepEqual(STUDY_AREA.bounds, [[9.8, 76.0], [10.1, 76.5]])
  assert.equal(isWithinStudyArea(9.95, 76.25), true)
  assert.equal(isWithinStudyArea(9.7, 76.25), false)
  assert.equal(isWithinStudyArea(Number.NaN, 76.25), false)
  assert.throws(
    () => createScenario({
      name: 'Outside area',
      inputs: { rainfallIntensityMmPerHour: 10, durationHours: 3 },
      focus: { latitude: 40, longitude: 80 },
    }),
    /inside the Kochi GIS study area/,
  )
})

test('scenario comparison calculates input differences and handles a zero baseline', () => {
  const first = scenario('A', 10, 2, 3)
  const second = scenario('B', 20, 4, 4)
  const metrics = compareScenarios(first, second, FRAME_COUNT - 1)

  assert.equal(metrics.firstAccumulatedRainfallMm, 20)
  assert.equal(metrics.secondAccumulatedRainfallMm, 80)
  assert.equal(metrics.differenceMm, 60)
  assert.equal(metrics.relativeChangePercent, 300)
  assert.equal(metrics.initialRiverLevelDifferenceM, 1)

  const zeroBaseline = compareScenarios(scenario('Zero', 0, 3), second, Number.NaN)
  assert.equal(zeroBaseline.relativeChangePercent, null)
  assert.equal(zeroBaseline.firstAccumulatedRainfallMm, 0)
})

test('timeline supports play, pause, reset, bounded scrubbing, and automatic stop', () => {
  const frames = scenario('A', 5, 3).frames
  let state = createTimelineState(frames)

  state = timelineReducer(state, { type: 'play' })
  assert.equal(state.isPlaying, true)
  state = timelineReducer(state, { type: 'tick' })
  assert.equal(state.frameIndex, 1)
  state = timelineReducer(state, { type: 'pause' })
  assert.equal(state.isPlaying, false)
  assert.equal(timelineReducer(state, { type: 'tick' }).frameIndex, 1)

  state = timelineReducer(state, { type: 'seek', frameIndex: 1000 })
  assert.equal(state.frameIndex, frames.length - 1)
  state = timelineReducer(state, { type: 'play' })
  assert.equal(state.frameIndex, 0)
  while (state.isPlaying) state = timelineReducer(state, { type: 'tick' })
  assert.equal(state.frameIndex, frames.length - 1)

  state = timelineReducer(state, { type: 'reset' })
  assert.equal(state.frameIndex, 0)
  assert.equal(state.isPlaying, false)
})

test('missing scenarios and invalid timeline values fail safely without fabricated defaults', () => {
  const emptyTimeline = createTimelineState()
  assert.deepEqual(timelineReducer(emptyTimeline, { type: 'play' }), emptyTimeline)
  assert.deepEqual(timelineReducer(emptyTimeline, { type: 'seek', frameIndex: 2 }), emptyTimeline)
  assert.equal(compareScenarios(null, null, 0), null)
  assert.equal(illustrativeMarkerRadius(null), 12)
  assert.throws(
    () => createScenario({
      name: '',
      inputs: { rainfallIntensityMmPerHour: 10, durationHours: 3 },
      focus,
    }),
    /Scenario name cannot be empty/,
  )
})

test('presets explicitly remain illustrative and existing GIS overlays stay compatible', () => {
  assert.match(SCENARIO_PRESETS.low.assumption, /Illustrative input/)
  assert.match(SCENARIO_PRESETS.moderate.assumption, /Illustrative input/)
  assert.equal(GEOJSON_LAYERS.length, 6)
  assert.deepEqual(
    GEOJSON_LAYERS.map(layer => layer.key),
    Object.keys(INITIAL_GEOJSON_VISIBILITY),
  )
  assert.deepEqual(Object.keys(GEOJSON_LAYER_STYLES).sort(), GEOJSON_LAYERS.map(layer => layer.key).sort())
  assert.equal(Object.values(INITIAL_GEOJSON_VISIBILITY).every(value => value === false), true)
})

test('operational flood forecast and emergency warning claims are not part of this engine', () => {
  const generated = scenario('Scenario A', 20, 6)
  assert.equal('floodExtent' in generated, false)
  assert.equal('floodDepth' in generated, false)
  assert.equal('riskProbability' in generated, false)
  assert.equal('warning' in generated, false)
})

test('page source contains the exact required limitation and non-extent map labels', () => {
  const pageSource = readFileSync(
    new URL('../src/pages/Simulation.jsx', import.meta.url),
    'utf8',
  )
  assert.match(pageSource, /Stage 1 illustrative scenario only — not a validated flood forecast or emergency-warning system\./)
  assert.match(pageSource, /Flood prediction: NOT_READY/)
  assert.match(pageSource, /not a geographic area/)
  assert.match(pageSource, /does not calculate flood depth, water extent, arrival time/)
})
