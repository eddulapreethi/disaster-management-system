import { alertLocation, alertTimestamp } from '../services/alertPresentation'

export default function AlertCard({ alert }) {
  const severe = alert.severity === 'high' || alert.severity === 'critical'
  return (
    <div className={`alert-card ${severe ? 'high' : 'medium'}`}>
      <div className="alert-card-top">
        <span className={`pill ${severe ? 'high' : 'med'}`}>{alert.severity}</span>
        <span className="alert-card-region">{alert.disaster_type} · {alertLocation(alert)}</span>
      </div>
      <h3>{alert.title}</h3>
      <p className="alert-card-msg">{alert.message}</p>
      <div className="alert-card-time">{alertTimestamp(alert)}</div>
      <p className="explain">Automated estimate, not an official warning. Follow local authority guidance.</p>
    </div>
  )
}
