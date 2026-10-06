import { useEffect, useState } from 'react'
import { getActiveAlerts } from '../services/alertService'
import AlertCard from '../components/AlertCard'

export default function Alerts() {
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getActiveAlerts()
      .then(data => { if (active) setAlerts(data) })
      .catch(requestError => { if (active) setError(requestError.message || 'Could not load alerts.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return (
    <div>
      <h2 className="title">Emergency alerts</h2>
      <p className="sub">Saved alerts generated from predictions on your account.</p>
      {loading && <div className="card">Loading alerts...</div>}
      {error && <div className="card" role="alert">{error}</div>}
      {!loading && !error && alerts.length === 0 && <div className="card">No saved alerts yet. New alerts are created for predictions above the configured threshold.</div>}
      <div className="alerts-grid">
        {alerts.map(a => <AlertCard key={a.id} alert={a} />)}
      </div>
    </div>
  )
}
