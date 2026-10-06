export default function AlertCard({ alert }) {
  const severe = alert.severity === 'high' || alert.severity === 'critical'
  return (
    <div className={`alert-card ${severe ? 'high' : 'medium'}`}>
      <div className="alert-card-top">
        <span className={`pill ${severe ? 'high' : 'med'}`}>{alert.severity}</span>
        <span className="alert-card-region">{alert.region}</span>
      </div>
      <p className="alert-card-msg">{alert.message}</p>
      <div className="alert-card-time">{new Date(alert.issuedAt).toLocaleString()}</div>
    </div>
  )
}
