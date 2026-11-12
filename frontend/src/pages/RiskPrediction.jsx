import { useState } from 'react'
import { predictRisk } from '../services/predictionService'
import PredictionCard from '../components/PredictionCard'
import Loading from '../components/Loading'
import WeatherCard from '../components/WeatherCard'
import LocationCoverage from '../components/LocationCoverage'
import EnvironmentalDataSummary from '../components/EnvironmentalDataSummary'
import SatelliteSceneCard from '../components/SatelliteSceneCard'
import LocationSearchField from '../components/LocationSearchField'
import { useSelectedLocation } from '../services/LocationContext'

export default function RiskPrediction() {
  const { selectedLocation, setSelectedLocation } = useSelectedLocation()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!selectedLocation) return
    setError('')
    setLoading(true)
    try {
      const r = await predictRisk(selectedLocation)
      setResult(r)
    } catch (requestError) {
      setError(requestError.message || 'Could not run prediction.')
    } finally {
      setLoading(false)
    }
  }

  const canPredict = Boolean(selectedLocation)
    && Number.isFinite(selectedLocation.latitude)
    && selectedLocation.latitude >= -90
    && selectedLocation.latitude <= 90
    && Number.isFinite(selectedLocation.longitude)
    && selectedLocation.longitude >= -180
    && selectedLocation.longitude <= 180

  return (
    <div>
      <h2 className="title">Risk prediction</h2>
      <p className="sub">Flood prediction remains unavailable until validated model readiness is established. No hazard-specific prediction capability is currently validated; selecting a location does not make one available.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Inputs</div>
          <LocationSearchField value={selectedLocation} onChange={location => {
            setSelectedLocation(location)
            setResult(null)
            setError('')
          }} label="Search for a city or place" />

          <div style={{ marginTop: '.9rem' }} className="formgrid">
            <div className="kv"><span>Selected place</span><span>{selectedLocation?.display_name || 'No location selected'}</span></div>
            <div className="kv"><span>Latitude</span><span>{selectedLocation ? selectedLocation.latitude.toFixed(5) : '—'}</span></div>
            <div className="kv"><span>Longitude</span><span>{selectedLocation ? selectedLocation.longitude.toFixed(5) : '—'}</span></div>
            <div className="kv"><span>Country</span><span>{selectedLocation?.country || 'Not identified for this selection'}</span></div>
          </div>
          <div style={{ marginTop: '.9rem' }}>
            <LocationCoverage location={selectedLocation} />
          </div>

          <p className="explain">The 20 model inputs are not shown as sliders: their units and data sources are not validated, so manually selected values would not be meaningful model features.</p>
          <button className="btn" onClick={run} disabled={loading || !canPredict}>{loading ? 'Checking prediction readiness…' : 'Request flood prediction'}</button>
          {error && <p className="error" role="alert">{error}</p>}
        </div>

        <div>
          {loading && !result ? <div className="card"><Loading label="Checking flood-prediction readiness…" /></div> : <PredictionCard result={result} title={`Estimate — ${selectedLocation?.display_name || 'selected location'}`} />}
          <div style={{ marginTop: '1rem' }}>
            {selectedLocation
              ? <WeatherCard location={selectedLocation} />
              : <div className="card explain">Select a place to request its current weather.</div>}
          </div>
          <div style={{ marginTop: '1rem' }}>
            <EnvironmentalDataSummary location={selectedLocation} />
          </div>
          <div style={{ marginTop: '1rem' }}>
            <SatelliteSceneCard
              key={selectedLocation ? `${selectedLocation.latitude}:${selectedLocation.longitude}` : 'no-location'}
              location={selectedLocation}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
