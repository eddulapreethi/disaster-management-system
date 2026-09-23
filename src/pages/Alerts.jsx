import { getActiveAlerts } from '../services/alertService'
import AlertCard from '../components/AlertCard'

export default function Alerts() {
  const alerts = getActiveAlerts()
  return (
    <div>
      <h2 className="title">Emergency alerts</h2>
      <p className="sub">Auto-generated from regions currently at or above the moderate-risk threshold.</p>
      {alerts.length === 0 && <div className="card">No active alerts right now.</div>}
      <div className="alerts-grid">
        {alerts.map(a => <AlertCard key={a.id} alert={a} />)}
      </div>
    </div>
  )
}
