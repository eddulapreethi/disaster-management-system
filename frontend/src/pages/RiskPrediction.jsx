import { useState } from 'react'
import { predictRisk, ADJUSTABLE_FEATURES } from '../services/predictionService'
import PredictionCard from '../components/PredictionCard'
import Loading from '../components/Loading'
import WeatherCard from '../components/WeatherCard'
import LocationSearchField from '../components/LocationSearchField'

const initial = Object.fromEntries(ADJUSTABLE_FEATURES.map(f => [f.key, 6]))
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
  const [values, setValues] = useState(initial)
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
      const r = await predictRisk(values, weatherAwareStation)
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
      <p className="sub">Choose a location by city, district, state, or country. The selected coordinates are validated before being sent to the backend weather and prediction services.</p>
      <p className="explain">This project still requires a real trained flood model artifact and a compatible data schema. Without that artifact, backend predictions remain clearly labelled weather heuristics instead of genuine ML inference.</p>
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

          <div style={{ marginTop: '.8rem' }} className="formgrid">
            {ADJUSTABLE_FEATURES.map(f => (
              <div key={f.key}>
                <label>{f.label} <span className="rangeval">{values[f.key]}</span></label>
                <input type="range" min="0" max="16" value={values[f.key]} onChange={e => setValues(v => ({ ...v, [f.key]: +e.target.value }))} />
              </div>
            ))}
          </div>
          <button className="btn" onClick={run} disabled={loading || !canPredict}>{loading ? 'Running…' : 'Run prediction'}</button>
          {error && <p className="error" role="alert">{error}</p>}
        </div>

        <div>
          {loading && !result ? <div className="card"><Loading label="Running model…" /></div> : <PredictionCard result={result} title={`Prediction — ${selected.display_name || selected.name}`} />}
          <div style={{ marginTop: '1rem' }}>
            <WeatherCard station={{ name: selected.display_name || selected.name, lat: selected.latitude, lng: selected.longitude }} />
          </div>
        </div>
      </div>
    </div>
  )
}
