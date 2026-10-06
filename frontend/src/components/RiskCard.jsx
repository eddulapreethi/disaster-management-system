import { riskBand } from '../services/stationData'

export default function RiskCard({ station, selected, onClick }) {
  return (
    <div className={`risk-card${selected ? ' selected' : ''}`} onClick={onClick}>
      <div className="risk-card-top">
        <span className="risk-card-name">{station.name}</span>
        <span className={`pill ${riskBand(station.risk)}`}>{station.risk}</span>
      </div>
      <div className="risk-card-region">{station.region}</div>
      <div className="risk-card-meta">
        <span>{station.latitude.toFixed(3)}, {station.longitude.toFixed(3)}</span>
        <span>{station.risk_level}</span>
        <span>{new Date(station.created_at).toLocaleDateString()}</span>
      </div>
    </div>
  )
}
