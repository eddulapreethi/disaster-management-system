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
        <span>{station.rain}mm rain</span>
        <span>{station.river}% river</span>
        <span>{station.pop}M pop</span>
      </div>
    </div>
  )
}
