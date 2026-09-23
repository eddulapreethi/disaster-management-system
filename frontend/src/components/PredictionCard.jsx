import { riskColor } from '../services/stationData'

export default function PredictionCard({ result, title }) {
  if (!result) return null
  const contribs = result.top_contributions || []
  const max = Math.max(...contribs.map(c => Math.abs(c.shap_contribution)), 0.001)

  return (
    <div className="card">
      <div className="sectitle">{title}{result.offline && ' (offline estimate)'}</div>
      <div className="gauge-wrap">
        <div style={{ fontFamily: 'Space Grotesk', fontSize: '2.6rem', fontWeight: 700, color: riskColor(result.risk_score) }}>
          {Math.round(result.risk_score)}
        </div>
        <span className={`pill ${result.risk_band === 'medium' ? 'med' : result.risk_band}`}>{result.risk_band} risk</span>
      </div>
      <div style={{ marginTop: '1rem' }} className="sectitle">Explainable AI — SHAP factor contributions</div>
      {contribs.map(c => (
        <div className="bar-row" key={c.feature}>
          <span className="lbl">{c.feature}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.abs(c.shap_contribution) / max * 100}%`, background: c.shap_contribution >= 0 ? 'var(--high)' : 'var(--low)' }} />
          </div>
          <span className="bar-val">{c.shap_contribution >= 0 ? '+' : ''}{c.shap_contribution.toFixed(3)}</span>
        </div>
      ))}
      <div className="explain">{result.explanation}</div>
    </div>
  )
}
