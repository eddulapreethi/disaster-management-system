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
      <p className="sub">Saved automated estimates generated from eligible account predictions. They are not official warnings.</p>
      {loading && <div className="card">Loading alerts...</div>}
      {error && <div className="card" role="alert">{error}</div>}
      {!loading && !error && alerts.length === 0 && <div className="card">No saved alerts yet. Eligible demonstrator estimates may create an in-app alert; flood predictions remain disabled until the model and runtime feature pipeline are verified.</div>}
      <div className="alerts-grid">
        {alerts.map(a => <AlertCard key={a.id} alert={a} />)}
      </div>
    </div>
  )
}
