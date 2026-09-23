export default function AlertCard({ alert }) {
  return (
    <div className={`alert-card ${alert.severity}`}>
      <div className="alert-card-top">
        <span className={`pill ${alert.severity === 'high' ? 'high' : 'med'}`}>{alert.severity}</span>
        <span className="alert-card-region">{alert.region}</span>
      </div>
      <p className="alert-card-msg">{alert.message}</p>
      <div className="alert-card-time">{new Date(alert.issuedAt).toLocaleString()}</div>
    </div>
  )
}
