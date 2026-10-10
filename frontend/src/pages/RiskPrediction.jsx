import { useState } from 'react'
import { predictRisk } from '../services/predictionService'
import PredictionCard from '../components/PredictionCard'
import Loading from '../components/Loading'
import WeatherCard from '../components/WeatherCard'
import LocationSearchField from '../components/LocationSearchField'

const DEFAULT_LOCATION = {
  id: 'kochi-default',
  name: 'Kochi',
  admin1: 'Kerala',
  admin2: 'Ernakulam',
  country: 'India',
  display_name: 'Kochi, Kerala, India',
  latitude: 9.9312,
  longitude: 76.2673,
}

export default function RiskPrediction() {
  const [selected, setSelected] = useState(DEFAULT_LOCATION)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    setError('')
    setLoading(true)
    try {
      const weatherAwareStation = {
        ...selected,
        name: selected.display_name || selected.name,
        lat: selected.latitude,
        lng: selected.longitude,
      }
      const r = await predictRisk(weatherAwareStation)
      setResult(r)
    } catch (requestError) {
      setError(requestError.message || 'Could not run prediction.')
    } finally {
      setLoading(false)
    }
  }

  const canPredict = Number.isFinite(selected.latitude) && Number.isFinite(selected.longitude)

  return (
    <div>
      <h2 className="title">Risk prediction</h2>
      <p className="sub">Choose a location with a stored weather observation. Until a verified trained model and environmental feature pipeline are available, the backend returns only a clearly labeled demonstrator weather heuristic.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Inputs</div>
          <LocationSearchField value={selected} onChange={setSelected} label="Location search" />

          <div style={{ marginTop: '.9rem' }} className="formgrid">
            <div className="kv"><span>Location</span><span>{selected.display_name || selected.name}</span></div>
            <div className="kv"><span>Latitude</span><span>{Number(selected.latitude).toFixed(4)}</span></div>
            <div className="kv"><span>Longitude</span><span>{Number(selected.longitude).toFixed(4)}</span></div>
            <div className="kv"><span>Country</span><span>{selected.country || 'Unknown'}</span></div>
          </div>

          <p className="explain">The 20 model inputs are not shown as sliders: their units and data sources are not validated, so manually selected values would not be meaningful model features.</p>
          <button className="btn" onClick={run} disabled={loading || !canPredict}>{loading ? 'Checking stored weather…' : 'Run weather estimate'}</button>
          {error && <p className="error" role="alert">{error}</p>}
        </div>

        <div>
          {loading && !result ? <div className="card"><Loading label="Checking stored weather…" /></div> : <PredictionCard result={result} title={`Estimate — ${selected.display_name || selected.name}`} />}
          <div style={{ marginTop: '1rem' }}>
            <WeatherCard station={{ name: selected.display_name || selected.name, lat: selected.latitude, lng: selected.longitude }} />
          </div>
        </div>
      </div>
    </div>
  )
}
