import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiGet, apiPost } from '../services/api'

export default function Recommendations() {
  const [recommendation, setRecommendation] = useState(null)
  const [hasPrediction, setHasPrediction] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    async function load() {
      try {
        let prediction = null
        try {
          prediction = JSON.parse(sessionStorage.getItem('disasterguard_latest_prediction') || 'null')
        } catch {
          prediction = null
        }
        if (!prediction) {
          const history = await apiGet('/predictions')
          const latest = history[0]
          if (latest) {
            prediction = {
              disaster_type: latest.disaster_type,
              risk_score: latest.risk_score,
              risk_level: latest.risk_level,
              risk_band: latest.risk_level,
              top_contributions: [],
            }
          }
        }
        if (!active) return
        setHasPrediction(Boolean(prediction))
        if (!prediction) return
        const simulation = JSON.parse(sessionStorage.getItem('disasterguard_last_simulation') || 'null')
        const result = await apiPost('/recommendations', { prediction, simulation })
        if (active) setRecommendation(result)
      } catch (requestError) {
        if (active) setError(requestError.message || 'Could not generate recommendations.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [])

  return (
    <div>
      <h2 className="title">AI emergency recommendations</h2>
      <p className="sub">Guidance is generated from your latest saved prediction and, when available, your latest simulation.</p>
      {loading && <div className="card">Generating recommendations...</div>}
      {error && <div className="card" role="alert">{error}</div>}
      {!loading && !error && !hasPrediction && <div className="card">Run a prediction before requesting recommendations. <Link to="/risk-prediction">Open risk prediction</Link></div>}
      {recommendation && (
        <div className="card">
          <div className="sectitle">{recommendation.summary}</div>
          {recommendation.simulation_summary && <p>{recommendation.simulation_summary}</p>}
          {recommendation.top_factors.length > 0 && <>
            <div className="sectitle">Model factors</div>
            {recommendation.top_factors.map(factor => <div className="kv" key={factor.feature}><span>{factor.label}</span><span>{factor.direction} ({factor.contribution.toFixed(3)})</span></div>)}
          </>}
          <div className="sectitle" style={{ marginTop: '1rem' }}>Recommended actions</div>
          <ul>{recommendation.recommendations.map((item, index) => <li key={index}>{item}</li>)}</ul>
          <p className="explain">{recommendation.disclaimer}</p>
        </div>
      )}
    </div>
  )
}
