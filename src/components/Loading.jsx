export default function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading-wrap">
      <span className="spinner" />
      <span className="loading-label">{label}</span>
    </div>
  )
}
