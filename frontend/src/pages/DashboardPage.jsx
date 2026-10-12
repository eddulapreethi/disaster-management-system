import { useEffect, useRef, useState } from 'react'
import Dashboard from '../components/Dashboard'
import WeatherCard from '../components/WeatherCard'
import { apiGet } from '../services/api'

export default function DashboardPage() {
  const [predictions, setPredictions] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [readiness, setReadiness] = useState(null)
  const [readinessError, setReadinessError] = useState('')
  const [historicalAnalytics, setHistoricalAnalytics] = useState(null)
  const [historicalAnalyticsError, setHistoricalAnalyticsError] = useState('')
  const historicalRequestRef = useRef(false)
  const readinessRequestRef = useRef(false)

  useEffect(() => {
    let active = true
    apiGet('/predictions')
      .then(records => {
        if (!active) return
        const rows = records.map(record => ({
          ...record,
          name: `${record.disaster_type} prediction #${record.id}`,
          region: `${record.latitude.toFixed(3)}, ${record.longitude.toFixed(3)}`,
          lat: record.latitude,
          lng: record.longitude,
          risk: record.risk_score,
          rain: record.rainfall_mm,
        }))
        setPredictions(rows)
        setSelected(rows[0] || null)
      })
      .catch(requestError => { if (active) setError(requestError.message || 'Could not load predictions.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    async function refreshHistoricalAnalytics() {
      if (historicalRequestRef.current) return
      historicalRequestRef.current = true
      try {
        const analytics = await apiGet('/historical-data/analytics')
        if (active) {
          setHistoricalAnalytics(analytics)
          setHistoricalAnalyticsError('')
        }
      } catch (requestError) {
        if (active) setHistoricalAnalyticsError(requestError.message || 'Could not load historical analytics.')
      } finally {
        if (active) historicalRequestRef.current = false
      }
    }
    refreshHistoricalAnalytics()
    const interval = setInterval(refreshHistoricalAnalytics, 60_000)
    return () => {
      active = false
      historicalRequestRef.current = false
      clearInterval(interval)
    }
  }, [])

  useEffect(() => {
    let active = true
    async function refreshReadiness() {
      if (readinessRequestRef.current) return
      readinessRequestRef.current = true
      try {
        const status = await apiGet('/data-readiness')
        if (active) {
          setReadiness(status)
          setReadinessError('')
        }
      } catch (requestError) {
        if (active) setReadinessError(requestError.message || 'Could not load data readiness.')
      } finally {
        if (active) readinessRequestRef.current = false
      }
    }
    refreshReadiness()
    const interval = setInterval(refreshReadiness, 60_000)
    return () => {
      active = false
      readinessRequestRef.current = false
      clearInterval(interval)
    }
  }, [])

  const readinessItems = readiness
    ? [
        ['Weather', readiness.sources.weather],
        ['Hydrology', readiness.sources.hydrology],
        ['GIS', readiness.sources.gis],
        ['Historical data', readiness.historical_data],
        ['ML model', readiness.ml_model],
        ['Features', readiness.features],
        ['Prediction', readiness.prediction],
      ]
    : []

  return (
    <div>
      <h2 className="title">Situation overview</h2>
      <p className="sub">Summary of your saved predictions. Select a prediction to view current weather at its coordinates.</p>
      <section className="card" aria-label="Data readiness">
        <div className="sectitle">Data readiness</div>
        {readinessError && <p role="alert">{readinessError}</p>}
        {!readiness && !readinessError && <p>Checking actual source and model status...</p>}
        {readiness && <>
          <div className="formgrid">
            {readinessItems.map(([label, item]) => (
              <div key={label}>
                <div className="kv">
                  <span>{label}</span>
                  <span className={`pill ${item.status === 'READY' ? 'low' : item.status === 'STALE' ? 'med' : 'high'}`}>{item.status}</span>
                </div>
                {['GIS', 'Historical data', 'ML model', 'Features', 'Prediction'].includes(label) && item.message && <p className="explain">{item.message}</p>}
              </div>
            ))}
          </div>
          <p className="explain">{readiness.sources.hydrology.message}</p>
          <div className="detailbox">
            <div className="kv"><span>Weather data</span><span className={`pill ${readiness.sources.weather.status === 'READY' ? 'low' : readiness.sources.weather.status === 'STALE' ? 'med' : 'high'}`}>{readiness.sources.weather.status}</span></div>
            <div className="kv"><span>Last observation</span><span>{readiness.sources.weather.last_observation ? new Date(readiness.sources.weather.last_observation).toLocaleString() : 'Unavailable'}</span></div>
            <div className="kv"><span>Last checked</span><span>{readiness.sources.weather.last_checked ? new Date(readiness.sources.weather.last_checked).toLocaleString() : 'Not checked yet'}</span></div>
            <div className="kv"><span>Source</span><span>{readiness.sources.weather.source || 'Open-Meteo'}</span></div>
            <p className="explain">{readiness.sources.weather.message} Checks run every {readiness.sources.weather.poll_interval_seconds || 300} seconds; Open-Meteo does not necessarily publish a new observation on every check.</p>
          </div>
          {readiness.sources.hydrology.sources.map(source => (
            <div className="detailbox" key={source.source}>
              <div className="kv"><span>{source.source}</span><span className={`pill ${source.status === 'READY' ? 'low' : source.status === 'STALE' ? 'med' : 'high'}`}>{source.status}</span></div>
              <div className="kv"><span>Latest observation</span><span>{source.last_observation ? new Date(source.last_observation).toLocaleString() : 'Unavailable'}</span></div>
              {source.latest_station && <div className="kv"><span>Latest station</span><span>{source.latest_station}</span></div>}
              {source.station_id && <div className="kv"><span>Station ID</span><span className="mono">{source.station_id}</span></div>}
              <div className="kv"><span>Observation age</span><span>{source.observation_age_seconds == null ? 'Unavailable' : `${Math.floor(source.observation_age_seconds / 3600)}h ${Math.floor((source.observation_age_seconds % 3600) / 60)}m`}</span></div>
              {source.water_level != null && <div className="kv"><span>Water level</span><span>{source.water_level} {source.water_level_unit || 'm'}</span></div>}
              {source.rainfall != null && <div className="kv"><span>Rainfall</span><span>{source.rainfall} {source.rainfall_unit || 'mm'}</span></div>}
              <div className="kv"><span>Collection / freshness</span><span>{source.collection_status} / {source.freshness_status}</span></div>
              <div className="kv"><span>Rows scanned / fetched new / valid new / inserted new</span><span>{source.records_returned} / {source.records_received} / {source.valid_records} / {source.inserted_count}</span></div>
              <div className="kv"><span>Duplicate / parse-error rows</span><span>{source.duplicates_skipped} / {source.parse_errors}</span></div>
              <div className="kv"><span>Newer observation found</span><span>{source.newer_observation_found ? 'Yes' : 'No'}</span></div>
              <div className="kv"><span>Last successful fetch</span><span>{source.last_fetch ? new Date(source.last_fetch).toLocaleString() : 'Not fetched yet'}</span></div>
              <div className="kv"><span>Provider update frequency</span><span>{source.update_frequency}</span></div>
              {source.message && <p className="explain">{source.message}</p>}
              {source.latest_error && <p className="error" role="alert">Latest source error: {source.latest_error}</p>}
              {source.collection_status === 'SUCCESS_EMPTY_RESPONSE' && <p className="explain">The provider returned no records on the last successful request. This is distinct from a successful request that returned only already-seen records.</p>}
              {source.collection_status === 'SUCCESS_NO_NEW_DATA' && <p className="explain">Records were returned, but none had an ID newer than the saved collector cursor. Observation freshness is evaluated separately.</p>}
              {source.collection_status === 'SUCCESS_WITH_NEW_DATA' && <p className="explain">New source records were received. The latest observation can still be stale if publication is delayed.</p>}
              {source.collection_status === 'SUCCESS_DUPLICATES_ONLY' && <p className="explain">Only records already stored for this station and observation time were returned.</p>}
              {source.collection_status === 'PARSE_ERRORS' && <p className="error" role="alert">Some returned rows failed validation and were skipped; see the latest error above.</p>}
            </div>
          ))}
          <p className="explain">Status checked at {new Date(readiness.checked_at).toLocaleString()}. The collector checks on its configured interval; CWC telemetry is labeled hourly and source publication may be delayed. Data collection does not trigger predictions.</p>
        </>}
      </section>
      <section className="card" aria-label="Historical disaster analytics">
        <div className="sectitle">Historical disaster analytics</div>
        {historicalAnalyticsError && <p className="error" role="alert">{historicalAnalyticsError}</p>}
        {!historicalAnalytics && !historicalAnalyticsError && <p>Validating historical dataset manifests and computing event summaries...</p>}
        {historicalAnalytics && <>
          <p className="explain">Descriptive counts from the verified EM-DAT extracts. They summarize reported past events and impacts; they are not future probabilities, complete surveillance, or flood forecasts.</p>
          <div className="formgrid">
            <div className="detailbox">
              <div className="kv"><span>Validated hazard extracts</span><span>{historicalAnalytics.dataset_inventory.length}</span></div>
              <div className="kv"><span>Rows across extracts</span><span>{historicalAnalytics.summary.source_rows_across_extracts.toLocaleString()}</span></div>
              <div className="kv"><span>Unique event IDs</span><span>{historicalAnalytics.summary.unique_event_ids.toLocaleString()}</span></div>
              <div className="kv"><span>Flood-classified EM-DAT events</span><span>{historicalAnalytics.summary.events_by_disaster_type.Flood || 0}</span></div>
              <p className="explain">Events appearing in multiple extracts: {historicalAnalytics.summary.event_ids_present_in_multiple_extracts}</p>
            </div>
            <div className="detailbox">
              <div className="sectitle">Events by disaster type</div>
              {Object.entries(historicalAnalytics.summary.events_by_disaster_type).map(([type, count]) => (
                <div className="kv" key={type}><span>{type}</span><span>{count.toLocaleString()}</span></div>
              ))}
            </div>
          </div>
          <div className="formgrid">
            <div className="detailbox">
              <div className="sectitle">Recent event counts by start year</div>
              {Object.entries(historicalAnalytics.summary.events_by_year).slice(-10).map(([year, count]) => (
                <div className="kv" key={year}><span>{year}</span><span>{count.toLocaleString()}</span></div>
              ))}
            </div>
            <div className="detailbox">
              <div className="sectitle">Reported impacts (incomplete coverage)</div>
              {Object.entries(historicalAnalytics.summary.reported_impacts).map(([impact, values]) => (
                <div className="kv" key={impact}>
                  <span>{impact.replaceAll('_', ' ')}</span>
                  <span>{values.sum_of_reported_values.toLocaleString()} {values.unit} ({values.reported_records.toLocaleString()} reports)</span>
                </div>
              ))}
            </div>
          </div>
          <div className="sectitle" style={{ marginTop: '1rem' }}>Dataset coverage and quality</div>
          {historicalAnalytics.dataset_inventory.map(dataset => (
            <div className="detailbox" key={dataset.name}>
              <div className="kv"><span>{dataset.name}</span><span>{dataset.rows.toLocaleString()} events</span></div>
              <div className="kv"><span>Start-date coverage</span><span>{dataset.date_coverage.start || 'Unavailable'} – {dataset.date_coverage.end || 'Unavailable'}</span></div>
              <div className="kv"><span>Countries represented</span><span>{dataset.geography.unique_countries}</span></div>
              <div className="kv"><span>Rows with valid coordinates</span><span>{dataset.geography.rows_with_both_valid_coordinates} ({dataset.geography.coordinate_coverage_percent}%)</span></div>
              <div className="kv"><span>Duplicate event IDs / exact rows</span><span>{dataset.duplicate_quality.duplicate_event_id_rows} / {dataset.duplicate_quality.exact_duplicate_rows}</span></div>
              <div className="kv"><span>Source license</span><span>{dataset.license}</span></div>
            </div>
          ))}
          <div className="detailbox">
            <div className="sectitle">Most-recorded countries</div>
            {Object.entries(historicalAnalytics.summary.events_by_country).slice(0, 10).map(([country, count]) => (
              <div className="kv" key={country}><span>{country}</span><span>{count.toLocaleString()}</span></div>
            ))}
          </div>
          <p className="explain">Impact totals include only source records with reported values. Missing coordinates and impacts are retained as missing—not inferred. Historical event records do not supply verified no-flood examples or continuous flood-risk targets.</p>
        </>}
      </section>
      {loading && <div className="card">Loading prediction history...</div>}
      {error && <div className="card" role="alert">{error}</div>}
      {!loading && !error && <Dashboard predictions={predictions} selected={selected} onSelect={setSelected} />}
      {selected && <div style={{ marginTop: '1rem' }}><WeatherCard station={selected} /></div>}
    </div>
  )
}
