import { riskBand } from '../services/stationData'
import RiskCard from './RiskCard'

export default function Dashboard({ predictions, selected, onSelect }) {
  if (!predictions.length) {
    return <div className="card">No saved predictions yet. Run a prediction to populate your dashboard.</div>
  }

  const avg = predictions.reduce((total, item) => total + item.risk, 0) / predictions.length
  const highCount = predictions.filter(item => item.risk_level === 'high' || item.risk_level === 'critical').length
  const top = [...predictions].sort((first, second) => second.risk - first.risk)[0]

  return (
    <div>
      <div className="grid cards4">
        <div className="card stat">
          <div className="label">Average saved risk</div>
          <div className="num">{avg.toLocaleString(undefined, { maximumFractionDigits: 1 })}<span style={{ fontSize: '1rem', color: 'var(--ink2)' }}>/100</span></div>
          <div className={`delta pill ${riskBand(avg) === 'medium' ? 'med' : riskBand(avg)}`}>{riskBand(avg)} concern</div>
        </div>
        <div className="card stat">
          <div className="label">Saved high-risk predictions</div>
          <div className="num">{highCount}</div>
          <div className="delta" style={{ color: 'var(--ink2)' }}>of {predictions.length} saved</div>
        </div>
        <div className="card stat">
          <div className="label">Saved predictions</div>
          <div className="num">{predictions.length}</div>
          <div className="delta" style={{ color: 'var(--ink2)' }}>for your account</div>
        </div>
        <div className="card stat">
          <div className="label">Highest priority</div>
          <div className="num" style={{ fontSize: '1.15rem', fontFamily: 'Space Grotesk' }}>{top.name}</div>
          <div className={`delta pill ${riskBand(top.risk) === 'medium' ? 'med' : riskBand(top.risk)}`}>score {top.risk}</div>
        </div>
      </div>

      <div className="sectitle" style={{ marginTop: '1.2rem' }}>Monitored regions</div>
      <div className="riskcard-grid">
        {predictions.map(prediction => (
          <RiskCard key={prediction.id} station={prediction} selected={selected?.id === prediction.id} onClick={() => onSelect(prediction)} />
        ))}
      </div>
    </div>
  )
}
