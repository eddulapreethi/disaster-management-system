import { useState } from 'react'
import { apiPost } from '../services/api'
import { fetchLiveWeather } from '../services/weatherService'
import { stations, riskColor } from '../services/stationData'

export default function Simulation() {
  const [selected, setSelected] = useState(stations[0])
  const [disasterType, setDisasterType] = useState('flood')
  const [rainfallChange, setRainfallChange] = useState(0)
  const [windChange, setWindChange] = useState(0)
  const [temperatureChange, setTemperatureChange] = useState(0)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    setLoading(true)
    setError('')
    try {
      const weather = await fetchLiveWeather(selected.lat, selected.lng)
      const simulation = await apiPost('/simulations', {
        disaster_type: disasterType,
        rainfall_mm: weather.todayRainfallMm ?? weather.rainMm ?? 0,
        temperature_c: weather.temperatureC ?? 25,
        wind_speed_kmh: weather.windKmh ?? 0,
        rainfall_change_percent: rainfallChange,
        wind_change_percent: windChange,
        temperature_change_c: temperatureChange,
      })
      setResult(simulation)
      sessionStorage.setItem('disasterguard_last_simulation', JSON.stringify(simulation))
    } catch (requestError) {
      setError(requestError.message || 'Could not run the scenario.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2 className="title">Digital twin simulation</h2>
      <p className="sub">Run a weather what-if scenario with the Digital Twin simulation engine.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Scenario controls</div>
          <label>Location</label>
          <select value={selected.id} onChange={e => setSelected(stations.find(s => s.id === e.target.value))}>
            {stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <label style={{ marginTop: '.8rem' }}>Hazard type</label>
          <select value={disasterType} onChange={event => setDisasterType(event.target.value)}>
            <option value="flood">Flood</option>
            <option value="storm">Storm</option>
            <option value="wildfire">Wildfire</option>
          </select>
          <label style={{ marginTop: '.8rem' }}>Rainfall increase (%) <span className="rangeval">{rainfallChange}</span></label>
          <input type="range" min="-100" max="500" value={rainfallChange} onChange={event => setRainfallChange(Number(event.target.value))} />
          {(disasterType === 'storm' || disasterType === 'wildfire') && <>
            <label style={{ marginTop: '.8rem' }}>Wind increase (%) <span className="rangeval">{windChange}</span></label>
            <input type="range" min="-100" max="500" value={windChange} onChange={event => setWindChange(Number(event.target.value))} />
          </>}
          {disasterType === 'wildfire' && <>
            <label style={{ marginTop: '.8rem' }}>Temperature change (C) <span className="rangeval">{temperatureChange}</span></label>
            <input type="range" min="-20" max="40" value={temperatureChange} onChange={event => setTemperatureChange(Number(event.target.value))} />
          </>}
          <button className="btn" onClick={run} disabled={loading}>{loading ? 'Running scenario...' : 'Run scenario'}</button>
          {error && <p className="error" role="alert">{error}</p>}
        </div>
        <div className="card">
          {result && (
            <>
              <div className="sectitle">Scenario result</div>
              <div className="kv"><span>Baseline risk → simulated risk</span>
                <span className="mono">{Math.round(result.baseline_risk_score)} → <b style={{ color: riskColor(result.scenario_risk_score) }}>{Math.round(result.scenario_risk_score)}</b></span>
              </div>
              <div className="kv"><span>Risk change</span><span>{result.score_change > 0 ? '+' : ''}{result.score_change}</span></div>
              <div className="kv"><span>Projected risk level</span><span>{result.scenario_risk_level}</span></div>
              <div className="kv"><span>Baseline weather</span><span>{result.baseline_conditions.rainfall_mm} mm rain, {result.baseline_conditions.temperature_c} C, {result.baseline_conditions.wind_speed_kmh} km/h wind</span></div>
              <div className="reco">{result.note}</div>
            </>
          ) || <p>Choose scenario conditions and run a simulation.</p>}
        </div>
      </div>
    </div>
  )
}
