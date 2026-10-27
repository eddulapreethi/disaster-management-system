import { useEffect, useReducer, useState } from 'react'
import RiskMap from '../maps/RiskMap'
import {
  compareScenarios,
  createScenario,
  createTimelineState,
  isWithinStudyArea,
  SCENARIO_LIMITS,
  SCENARIO_PRESETS,
  STUDY_AREA,
  timelineReducer,
  validateScenarioInputs,
} from '../digitalTwin/scenarioEngine'

const INITIAL_INPUTS = {
  rainfallIntensityMmPerHour: '20',
  durationHours: '6',
  initialRiverLevelM: '',
}

function formatted(value, digits = 1) {
  return Number.isFinite(value) ? value.toFixed(digits) : '—'
}

export default function Simulation() {
  const [inputs, setInputs] = useState(INITIAL_INPUTS)
  const [presetDescription, setPresetDescription] = useState(SCENARIO_PRESETS.moderate.assumption)
  const [focus, setFocus] = useState(STUDY_AREA.defaultFocus)
  const [studyAreaMode, setStudyAreaMode] = useState('full')
  const [primary, setPrimary] = useState(null)
  const [comparison, setComparison] = useState(null)
  const [timeline, dispatchTimeline] = useReducer(
    timelineReducer,
    undefined,
    () => createTimelineState(),
  )
  const [speed, setSpeed] = useState(1)
  const [errors, setErrors] = useState({})

  useEffect(() => {
    if (!timeline.isPlaying) return undefined
    const timer = window.setInterval(
      () => dispatchTimeline({ type: 'tick' }),
      1000 / speed,
    )
    return () => window.clearInterval(timer)
  }, [speed, timeline.isPlaying])

  const currentFrame = primary?.frames[timeline.frameIndex] || null
  const currentComparisonFrame = comparison && currentFrame
    ? comparison.frames[Math.round(currentFrame.progress * (comparison.frames.length - 1))]
    : null
  const comparisonMetrics = primary && comparison
    ? compareScenarios(primary, comparison, timeline.frameIndex)
    : null
  const currentValidation = validateScenarioInputs(inputs)
  const controlsDifferFromPrimary = Boolean(
    primary
    && (
      !currentValidation.valid
      || Object.keys(primary.inputs).some(
        field => primary.inputs[field] !== currentValidation.values[field],
      )
    ),
  )

  function applyPreset(presetKey) {
    const preset = SCENARIO_PRESETS[presetKey]
    setInputs(current => ({
      ...current,
      rainfallIntensityMmPerHour: String(preset.rainfallIntensityMmPerHour),
      durationHours: String(preset.durationHours),
    }))
    setPresetDescription(preset.assumption)
    setErrors({})
  }

  function validateInputs() {
    const validation = validateScenarioInputs(inputs)
    setErrors(validation.errors)
    return validation
  }

  function runPrimaryScenario() {
    const validation = validateInputs()
    if (!validation.valid) return
    try {
      const scenario = createScenario({
        name: 'Scenario A',
        inputs: validation.values,
        focus,
      })
      setPrimary(scenario)
      setComparison(null)
      dispatchTimeline({ type: 'load', frames: scenario.frames })
    } catch (error) {
      setErrors({ focus: error.message })
    }
  }

  function runComparisonScenario() {
    const validation = validateInputs()
    if (!validation.valid) return
    try {
      setComparison(createScenario({
        name: 'Scenario B',
        inputs: validation.values,
        focus,
      }))
    } catch (error) {
      setErrors({ focus: error.message })
    }
  }

  function changeFocus(nextFocus) {
    if (!isWithinStudyArea(nextFocus.latitude, nextFocus.longitude)) return
    setFocus(nextFocus)
    setStudyAreaMode('focus')
    setPrimary(null)
    setComparison(null)
    setErrors(validateScenarioInputs(inputs).errors)
    dispatchTimeline({ type: 'reset' })
  }

  function changeStudyAreaMode(mode) {
    setStudyAreaMode(mode)
    if (mode === 'full') setFocus(STUDY_AREA.defaultFocus)
    setPrimary(null)
    setComparison(null)
    setErrors(validateScenarioInputs(inputs).errors)
    dispatchTimeline({ type: 'reset' })
  }

  function updateInput(field, value) {
    setInputs(current => ({ ...current, [field]: value }))
    setErrors(current => ({ ...current, [field]: undefined }))
    setPresetDescription('Custom illustrative input; not an observed or forecast rainfall value.')
  }

  const durationLabel = currentFrame
    ? `${formatted(currentFrame.elapsedHours, 2)} / ${formatted(primary.inputs.durationHours, 1)} hours`
    : 'No scenario run'

  return (
    <section className="digital-twin">
      <header className="digital-twin-header">
        <div>
          <h2 className="title">Digital Twin · Stage 1 demonstrator</h2>
          <p className="sub">
            Explore deterministic rainfall what-if inputs within the Kochi GIS study area.
            This local visualization does not retrieve weather or hydrology data.
          </p>
        </div>
        <span className="twin-status">Flood prediction: NOT_READY</span>
      </header>

      <div className="twin-warning" role="note">
        <strong>Stage 1 illustrative scenario only — not a validated flood forecast or emergency-warning system.</strong>
        <span>It does not calculate flood depth, water extent, arrival time, risk probability, or trigger alerts.</span>
      </div>

      <div className="twin-layout">
        <section className="twin-map-column" aria-label="Kochi study area map">
          <div className="card twin-map-card">
            <div className="sectitle">Kochi study area · reference geography</div>
            <div className="twin-map-legend" aria-label="Map legend">
              <span><i className="twin-legend-symbol primary" /> Scenario A symbol</span>
              {comparison && <span><i className="twin-legend-symbol comparison" /> Scenario B symbol</span>}
              <span>Symbol size is illustrative intensity only, not a geographic area.</span>
            </div>
            <RiskMap
              simulationFrame={currentFrame}
              comparisonFrame={currentComparisonFrame}
              simulationCenter={focus}
              selectionBounds={STUDY_AREA.bounds}
              onSimulationCenterChange={changeFocus}
            />
            <p className="twin-map-help">
              Select a focus point by clicking inside the packaged Kochi coverage. Existing GIS layers are reference data only.
              Available assets cover Kochi only; other regions are not supported here.
            </p>
            <div className="twin-focus" aria-live="polite">
              Focus point: {focus.latitude.toFixed(5)}, {focus.longitude.toFixed(5)}
              {studyAreaMode === 'full' ? ' · Kochi study-area mode' : ' · map-selected focus mode'}
            </div>
          </div>

          <section className="card twin-results" aria-labelledby="twin-results-title">
            <h3 className="sectitle" id="twin-results-title">Scenario results · illustrative inputs only</h3>
            {controlsDifferFromPrimary && (
              <p className="twin-field-help" role="status">
                Current controls differ from Scenario A. Results remain bound to the last valid run until Scenario A is run again.
              </p>
            )}
            {!primary ? (
              <p className="twin-empty">Run Scenario A to generate a deterministic sequence of demonstration frames.</p>
            ) : (
              <>
                <div className="twin-metrics-grid">
                  <div className="twin-metric">
                    <span>Rainfall input</span>
                    <strong>{formatted(primary.inputs.rainfallIntensityMmPerHour, 0)} mm/hour</strong>
                  </div>
                  <div className="twin-metric">
                    <span>Scenario duration</span>
                    <strong>{formatted(primary.inputs.durationHours, 1)} hours</strong>
                  </div>
                  <div className="twin-metric">
                    <span>Current frame elapsed</span>
                    <strong>{durationLabel}</strong>
                  </div>
                  <div className="twin-metric">
                    <span>Illustrative accumulated rainfall input</span>
                    <strong>{formatted(currentFrame.scenarioRainfallAccumulatedMm, 1)} mm</strong>
                  </div>
                  <div className="twin-metric">
                    <span>Initial river level</span>
                    <strong>
                      {primary.inputs.initialRiverLevelM === null
                        ? 'Not supplied'
                        : `${formatted(primary.inputs.initialRiverLevelM, 2)} m (user supplied)`}
                    </strong>
                  </div>
                </div>
                <p className="twin-limit-note">
                  Accumulated rainfall is only the entered rate multiplied by elapsed scenario time.
                  The optional river level is context only and does not drive the map visualization.
                  No affected area or flood metrics are calculated.
                </p>
              </>
            )}
          </section>

          {primary && comparison && comparisonMetrics && (
            <section className="card twin-results" aria-labelledby="twin-comparison-title">
              <h3 className="sectitle" id="twin-comparison-title">Scenario comparison · same elapsed-time fraction</h3>
              <div className="twin-metrics-grid">
                <div className="twin-metric">
                  <span>Scenario A input rate · duration</span>
                  <strong>
                    {formatted(primary.inputs.rainfallIntensityMmPerHour, 0)} mm/hour · {formatted(primary.inputs.durationHours, 1)} hours
                  </strong>
                </div>
                <div className="twin-metric">
                  <span>Scenario B input rate · duration</span>
                  <strong>
                    {formatted(comparison.inputs.rainfallIntensityMmPerHour, 0)} mm/hour · {formatted(comparison.inputs.durationHours, 1)} hours
                  </strong>
                </div>
                <div className="twin-metric">
                  <span>Scenario A accumulated input</span>
                  <strong>{formatted(comparisonMetrics.firstAccumulatedRainfallMm, 1)} mm</strong>
                </div>
                <div className="twin-metric">
                  <span>Scenario B accumulated input</span>
                  <strong>{formatted(comparisonMetrics.secondAccumulatedRainfallMm, 1)} mm</strong>
                </div>
                <div className="twin-metric">
                  <span>B minus A</span>
                  <strong>{comparisonMetrics.differenceMm >= 0 ? '+' : ''}{formatted(comparisonMetrics.differenceMm, 1)} mm</strong>
                </div>
                <div className="twin-metric">
                  <span>Relative input change</span>
                  <strong>
                    {comparisonMetrics.relativeChangePercent === null
                      ? 'Undefined (Scenario A is zero)'
                      : `${comparisonMetrics.relativeChangePercent >= 0 ? '+' : ''}${formatted(comparisonMetrics.relativeChangePercent, 1)}%`}
                  </strong>
                </div>
              </div>
            </section>
          )}
        </section>

        <aside className="twin-controls-column">
          <section className="card twin-control-card">
            <h3 className="sectitle">Scenario controls</h3>
            <label htmlFor="twin-study-area">Study area</label>
            <select
              id="twin-study-area"
              value={studyAreaMode}
              onChange={event => changeStudyAreaMode(event.target.value)}
            >
              <option value="full">Full Kochi GIS coverage · center focus</option>
              <option value="focus">Map-selected focus point within Kochi</option>
            </select>
            <p className="twin-field-help">Both modes use only the same documented Kochi GIS coverage. Full coverage selects its bounding-box center; focus mode lets you click a point. Neither represents a hydrologic catchment.</p>

            <div className="twin-presets" role="group" aria-label="Illustrative rainfall presets">
              <span className="twin-group-label">Illustrative presets</span>
              {Object.entries(SCENARIO_PRESETS).map(([key, preset]) => (
                <button key={key} type="button" className="twin-preset" onClick={() => applyPreset(key)}>
                  {preset.label}
                </button>
              ))}
            </div>
            <p className="twin-field-help" aria-live="polite">{presetDescription}</p>

            <label htmlFor="twin-rainfall">Rainfall intensity (mm/hour)</label>
            <input
              id="twin-rainfall"
              type="number"
              min={SCENARIO_LIMITS.rainfallIntensityMmPerHour.min}
              max={SCENARIO_LIMITS.rainfallIntensityMmPerHour.max}
              step="1"
              value={inputs.rainfallIntensityMmPerHour}
              onChange={event => updateInput('rainfallIntensityMmPerHour', event.target.value)}
              aria-invalid={Boolean(errors.rainfallIntensityMmPerHour)}
              aria-describedby={errors.rainfallIntensityMmPerHour ? 'twin-rainfall-error' : 'twin-rainfall-help'}
            />
            <p className="twin-field-help" id={errors.rainfallIntensityMmPerHour ? 'twin-rainfall-error' : 'twin-rainfall-help'}>
              Range 0–300 mm/hour. {errors.rainfallIntensityMmPerHour || 'Scenario input only; not a measured value.'}
            </p>

            <label htmlFor="twin-duration">Scenario duration (hours)</label>
            <input
              id="twin-duration"
              type="number"
              min={SCENARIO_LIMITS.durationHours.min}
              max={SCENARIO_LIMITS.durationHours.max}
              step="1"
              value={inputs.durationHours}
              onChange={event => updateInput('durationHours', event.target.value)}
              aria-invalid={Boolean(errors.durationHours)}
              aria-describedby={errors.durationHours ? 'twin-duration-error' : 'twin-duration-help'}
            />
            <p className="twin-field-help" id={errors.durationHours ? 'twin-duration-error' : 'twin-duration-help'}>
              Range 1–72 hours. {errors.durationHours || 'Elapsed-time sequence for this demonstration.'}
            </p>

            <label htmlFor="twin-river-level">Initial river-water level (m, optional)</label>
            <input
              id="twin-river-level"
              type="number"
              min={SCENARIO_LIMITS.initialRiverLevelM.min}
              max={SCENARIO_LIMITS.initialRiverLevelM.max}
              step="0.1"
              placeholder="Leave blank if unknown"
              value={inputs.initialRiverLevelM}
              onChange={event => updateInput('initialRiverLevelM', event.target.value)}
              aria-invalid={Boolean(errors.initialRiverLevelM)}
              aria-describedby="twin-river-level-help"
            />
            <p className="twin-field-help" id="twin-river-level-help">
              Range 0–30 m. No verified gauge reading is available here; any entry is user-specified and illustrative.
              {errors.initialRiverLevelM ? ` ${errors.initialRiverLevelM}` : ''}
            </p>

            {errors.focus && <p className="twin-error" role="alert">{errors.focus}</p>}
            <div className="twin-actions">
              <button type="button" className="btn" onClick={runPrimaryScenario}>Run Scenario A</button>
              <button
                type="button"
                className="btn twin-secondary-button"
                onClick={runComparisonScenario}
                disabled={!primary}
              >
                {comparison ? 'Replace Scenario B' : 'Run comparison Scenario B'}
              </button>
            </div>
            {!primary && <p className="twin-field-help">Correct the values above and run a scenario to enable playback and comparison.</p>}
          </section>

          <section className="card twin-control-card" aria-labelledby="twin-playback-title">
            <h3 className="sectitle" id="twin-playback-title">Timeline & playback</h3>
            <div className="twin-actions twin-playback-actions">
              <button type="button" onClick={() => dispatchTimeline({ type: 'play' })} disabled={!primary || timeline.isPlaying}>Play</button>
              <button type="button" onClick={() => dispatchTimeline({ type: 'pause' })} disabled={!timeline.isPlaying}>Pause</button>
              <button type="button" onClick={() => dispatchTimeline({ type: 'reset' })} disabled={!primary}>Reset</button>
            </div>
            <label htmlFor="twin-timeline">Frame</label>
            <input
              id="twin-timeline"
              type="range"
              min="0"
              max={Math.max(0, (primary?.frames.length || 1) - 1)}
              step="1"
              value={primary ? timeline.frameIndex : 0}
              disabled={!primary}
              onChange={event => dispatchTimeline({ type: 'seek', frameIndex: event.target.value })}
              aria-label="Simulation timeline frame"
            />
            <p className="twin-field-help" aria-live="polite">
              Frame {primary ? timeline.frameIndex + 1 : 0} / {primary?.frames.length || 0}
              {currentFrame ? ` · ${formatted(currentFrame.elapsedHours, 2)} elapsed hours` : ''}
            </p>
            <label htmlFor="twin-speed">Playback speed ({speed}×)</label>
            <input
              id="twin-speed"
              type="range"
              min="0.25"
              max="4"
              step="0.25"
              value={speed}
              onChange={event => setSpeed(Number(event.target.value))}
              aria-label="Simulation playback speed"
            />
          </section>
        </aside>
      </div>
    </section>
  )
}
