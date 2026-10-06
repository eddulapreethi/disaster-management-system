import { useEffect, useState } from 'react'
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
    async function refreshReadiness() {
      try {
        const status = await apiGet('/data-readiness')
        if (active) {
          setReadiness(status)
          setReadinessError('')
        }
      } catch (requestError) {
        if (active) setReadinessError(requestError.message || 'Could not load data readiness.')
      }
    }
    refreshReadiness()
    const interval = setInterval(refreshReadiness, 60_000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  const readinessItems = readiness
    ? [
        ['Weather', readiness.sources.weather],
        ['Hydrology', readiness.sources.hydrology],
        ['GIS', readiness.sources.gis],
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
              <div className="kv" key={label}>
                <span>{label}</span>
                <span className={`pill ${item.status === 'READY' ? 'low' : item.status === 'STALE' ? 'med' : 'high'}`}>{item.status}</span>
              </div>
            ))}
          </div>
          <p className="explain">{readiness.sources.hydrology.message}</p>
          <div className="detailbox">
            <div className="kv"><span>Weather data</span><span className={`pill ${readiness.sources.weather.status === 'READY' ? 'low' : readiness.sources.weather.status === 'STALE' ? 'med' : 'high'}`}>{readiness.sources.weather.status}</span></div>
            <div className="kv"><span>Last observation</span><span>{readiness.sources.weather.last_observation ? new Date(readiness.sources.weather.last_observation).toLocaleString() : 'Unavailable'}</span></div>
            <div className="kv"><span>Last checked</span><span>{readiness.sources.weather.last_checked ? new Date(readiness.sources.weather.last_checked).toLocaleString() : 'Not checked yet'}</span></div>
            <div className="kv"><span>Source</span><span>{readiness.sources.weather.source || 'Open-Meteo'}</span></div>
            <p className="explain">{readiness.sources.weather.message} Checks run every {readiness.sources.weather.poll_interval_seconds || 60} seconds; Open-Meteo does not necessarily publish a new observation on every check.</p>
          </div>
          {readiness.sources.hydrology.sources.map(source => (
            <div className="detailbox" key={source.source}>
              <div className="kv"><span>{source.source}</span><span className={`pill ${source.status === 'READY' ? 'low' : source.status === 'STALE' ? 'med' : 'high'}`}>{source.status}</span></div>
              <div className="kv"><span>Latest observation</span><span>{source.last_observation ? new Date(source.last_observation).toLocaleString() : 'Unavailable'}</span></div>
              {source.latest_station && <div className="kv"><span>Latest station</span><span>{source.latest_station}</span></div>}
              {source.water_level != null && <div className="kv"><span>Water level</span><span>{source.water_level} m</span></div>}
              {source.rainfall != null && <div className="kv"><span>Rainfall</span><span>{source.rainfall} mm</span></div>}
              <div className="kv"><span>Last successful fetch</span><span>{source.last_fetch ? new Date(source.last_fetch).toLocaleString() : 'Not fetched yet'}</span></div>
              {source.message && <p className="explain">{source.message}</p>}
            </div>
          ))}
          <p className="explain">Status checked at {new Date(readiness.checked_at).toLocaleString()}. The collector checks on its configured interval; CWC telemetry is hourly and a new observation is not expected every minute. Data collection does not trigger predictions.</p>
        </>}
      </section>
      {loading && <div className="card">Loading prediction history...</div>}
      {error && <div className="card" role="alert">{error}</div>}
      {!loading && !error && <Dashboard predictions={predictions} selected={selected} onSelect={setSelected} />}
      {selected && <div style={{ marginTop: '1rem' }}><WeatherCard station={selected} /></div>}
    </div>
  )
}
