import { useEffect, useState } from 'react'
import RiskMapView from '../maps/RiskMap'
import { apiGet } from '../services/api'
import { riskBand } from '../services/stationData'

export default function RiskMapPage() {
  const [points, setPoints] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    apiGet('/gis/risk-points')
      .then(collection => {
        if (!active) return
        const mapped = collection.features.map(feature => {
          const [lng, lat] = feature.geometry.coordinates
          const properties = feature.properties || {}
          return {
            id: properties.prediction_id,
            name: properties.location_name || `Prediction ${properties.prediction_id}`,
            disasterType: properties.disaster_type,
            lat,
            lng,
            risk: properties.risk_score,
            createdAt: properties.created_at,
          }
        })
        setPoints(mapped)
        setSelected(mapped[0] || null)
      })
      .catch(requestError => {
        if (active) setError(requestError.message || 'Could not load saved risk locations.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  return (
    <div>
      <h2 className="title">Regional risk map</h2>
      <p className="sub">Saved predictions for your account. Click a marker to inspect its location and risk score.</p>
      {loading && <div className="card">Loading saved risk locations...</div>}
      {error && <div className="card" role="alert">{error}</div>}
      {!loading && !error && points.length === 0 && <div className="card">No saved predictions to map yet. Run a prediction first.</div>}
      {!loading && !error && points.length > 0 && <RiskMapView points={points} selected={selected} onSelect={setSelected} />}
      {selected && (
        <div className="detailbox">
          <h4>{selected.name}</h4>
          <div style={{ color: 'var(--ink2)', fontSize: '.8rem', marginBottom: '.5rem' }}>{selected.disasterType}</div>
          <div className="kv"><span>Risk score</span><span className={`pill ${riskBand(selected.risk) === 'medium' ? 'med' : riskBand(selected.risk)}`}>{selected.risk}/100</span></div>
          <div className="kv"><span>Coordinates</span><span>{selected.lat.toFixed(4)}, {selected.lng.toFixed(4)}</span></div>
          <div className="kv"><span>Prediction time</span><span>{new Date(selected.createdAt).toLocaleString()}</span></div>
        </div>
      )}
    </div>
  )
}
