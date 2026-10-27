export const STUDY_AREA = Object.freeze({
  id: 'kochi',
  label: 'Kochi GIS study area',
  bounds: Object.freeze([[9.8, 76.0], [10.1, 76.5]]),
  defaultFocus: Object.freeze({ latitude: 9.95, longitude: 76.25 }),
})

export const SCENARIO_LIMITS = Object.freeze({
  rainfallIntensityMmPerHour: Object.freeze({ min: 0, max: 300 }),
  durationHours: Object.freeze({ min: 1, max: 72 }),
  initialRiverLevelM: Object.freeze({ min: 0, max: 30 }),
})

export const SCENARIO_PRESETS = Object.freeze({
  low: Object.freeze({
    label: 'Low',
    rainfallIntensityMmPerHour: 5,
    durationHours: 3,
    assumption: 'Illustrative input: 5 mm/hour for 3 hours.',
  }),
  moderate: Object.freeze({
    label: 'Moderate',
    rainfallIntensityMmPerHour: 20,
    durationHours: 6,
    assumption: 'Illustrative input: 20 mm/hour for 6 hours.',
  }),
  high: Object.freeze({
    label: 'High',
    rainfallIntensityMmPerHour: 50,
    durationHours: 12,
    assumption: 'Illustrative input: 50 mm/hour for 12 hours.',
  }),
})

export const FRAME_COUNT = 25

function parseBoundedNumber(rawValue, field, limits, errors) {
  if (
    rawValue === null
    || rawValue === undefined
    || (typeof rawValue === 'string' && rawValue.trim() === '')
  ) {
    errors[field] = 'Enter a value.'
    return null
  }
  const value = Number(rawValue)
  if (!Number.isFinite(value)) {
    errors[field] = 'Enter a finite number.'
    return null
  }
  if (value < limits.min || value > limits.max) {
    errors[field] = `Value must be between ${limits.min} and ${limits.max}.`
    return null
  }
  return value
}

export function validateScenarioInputs(input) {
  const errors = {}
  const rainfallIntensityMmPerHour = parseBoundedNumber(
    input?.rainfallIntensityMmPerHour,
    'rainfallIntensityMmPerHour',
    SCENARIO_LIMITS.rainfallIntensityMmPerHour,
    errors,
  )
  const durationHours = parseBoundedNumber(
    input?.durationHours,
    'durationHours',
    SCENARIO_LIMITS.durationHours,
    errors,
  )
  const rawRiverLevel = input?.initialRiverLevelM
  let initialRiverLevelM = null
  if (rawRiverLevel !== '' && rawRiverLevel !== null && rawRiverLevel !== undefined) {
    initialRiverLevelM = parseBoundedNumber(
      rawRiverLevel,
      'initialRiverLevelM',
      SCENARIO_LIMITS.initialRiverLevelM,
      errors,
    )
  }
  return {
    valid: Object.keys(errors).length === 0,
    errors,
    values: {
      rainfallIntensityMmPerHour,
      durationHours,
      initialRiverLevelM,
    },
  }
}

export function isWithinStudyArea(latitude, longitude) {
  return Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= STUDY_AREA.bounds[0][0]
    && latitude <= STUDY_AREA.bounds[1][0]
    && longitude >= STUDY_AREA.bounds[0][1]
    && longitude <= STUDY_AREA.bounds[1][1]
}

export function createScenario({ name, inputs, focus }) {
  if (typeof name !== 'string' || name.trim() === '') {
    throw new TypeError('Scenario name cannot be empty.')
  }
  const validation = validateScenarioInputs(inputs)
  if (!validation.valid) {
    throw new TypeError('Scenario inputs are invalid.')
  }
  if (
    !focus
    || !isWithinStudyArea(Number(focus.latitude), Number(focus.longitude))
  ) {
    throw new TypeError('Choose a focus point inside the Kochi GIS study area.')
  }

  const { rainfallIntensityMmPerHour, durationHours, initialRiverLevelM } = validation.values
  const frames = Array.from({ length: FRAME_COUNT }, (_, index) => {
    const progress = index / (FRAME_COUNT - 1)
    const elapsedHours = durationHours * progress
    return Object.freeze({
      index,
      progress,
      elapsedHours,
      scenarioRainfallAccumulatedMm: rainfallIntensityMmPerHour * elapsedHours,
      visualIntensity:
        rainfallIntensityMmPerHour / SCENARIO_LIMITS.rainfallIntensityMmPerHour.max,
    })
  })

  return Object.freeze({
    name,
    inputs: Object.freeze(validation.values),
    focus: Object.freeze({
      latitude: Number(focus.latitude),
      longitude: Number(focus.longitude),
    }),
    frames: Object.freeze(frames),
  })
}

export function compareScenarios(first, second, frameIndex) {
  if (!first?.frames?.length || !second?.frames?.length) {
    return null
  }
  const requestedIndex = Number(frameIndex)
  const safeIndex = Number.isFinite(requestedIndex) ? Math.round(requestedIndex) : 0
  const firstFrame = first.frames[Math.min(Math.max(safeIndex, 0), first.frames.length - 1)]
  const secondIndex = Math.round(
    (firstFrame.progress ?? 0) * (second.frames.length - 1),
  )
  const secondFrame = second.frames[secondIndex]
  const firstTotal = firstFrame.scenarioRainfallAccumulatedMm
  const secondTotal = secondFrame.scenarioRainfallAccumulatedMm
  const differenceMm = secondTotal - firstTotal
  return Object.freeze({
    firstAccumulatedRainfallMm: firstTotal,
    secondAccumulatedRainfallMm: secondTotal,
    differenceMm,
    relativeChangePercent: firstTotal === 0 ? null : (differenceMm / firstTotal) * 100,
    initialRiverLevelDifferenceM:
      first.inputs.initialRiverLevelM === null || second.inputs.initialRiverLevelM === null
        ? null
        : second.inputs.initialRiverLevelM - first.inputs.initialRiverLevelM,
  })
}

export function createTimelineState(frames = []) {
  return { frames, frameIndex: 0, isPlaying: false }
}

export function timelineReducer(state, action) {
  switch (action.type) {
    case 'load':
      return createTimelineState(action.frames)
    case 'play':
      if (!state.frames.length) return state
      return {
        ...state,
        frameIndex: state.frameIndex >= state.frames.length - 1 ? 0 : state.frameIndex,
        isPlaying: true,
      }
    case 'pause':
      return { ...state, isPlaying: false }
    case 'reset':
      return { ...state, frameIndex: 0, isPlaying: false }
    case 'seek': {
      if (!state.frames.length) return state
      const requested = Number(action.frameIndex)
      const frameIndex = Number.isFinite(requested)
        ? Math.min(Math.max(Math.round(requested), 0), state.frames.length - 1)
        : state.frameIndex
      return { ...state, frameIndex, isPlaying: false }
    }
    case 'tick':
      if (!state.isPlaying || !state.frames.length) return state
      if (state.frameIndex >= state.frames.length - 1) {
        return { ...state, isPlaying: false }
      }
      return {
        ...state,
        frameIndex: state.frameIndex + 1,
        isPlaying: state.frameIndex + 1 < state.frames.length - 1,
      }
    default:
      return state
  }
}

export function illustrativeMarkerRadius(frame) {
  if (!frame || !Number.isFinite(frame.visualIntensity) || !Number.isFinite(frame.progress)) {
    return 12
  }
  return 12 + 10 * frame.visualIntensity + 4 * frame.progress
}
