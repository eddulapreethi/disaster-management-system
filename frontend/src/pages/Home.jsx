import { Link } from 'react-router-dom'
import { getCurrentUser } from '../services/authService'

const FEATURES = [
  ['🤖', 'Experimental estimates', 'Flood prediction is unavailable; other heuristic scores are unvalidated and are not forecasts.'],
  ['🔍', 'Model explanations', 'Feature-attribution explanations are shown only when a compatible trained model is ready.'],
  ['🗺', 'Reference map', 'Saved account scores and Kochi-only reference geography; not live hazard monitoring.'],
  ['🧪', 'Illustrative scenarios', 'Explore what-if scenarios; results are not physical forecasts or observed impacts.'],
  ['🧠', 'General recommendations', 'Guidance is not based on validated location-specific predictions.'],
  ['🚑', 'Resource planning concepts', 'Explore planning concepts; recommendations are not operational allocations.'],
]

export default function Home() {
  const user = getCurrentUser()
  return (
    <div className="home-hero">
      <h1 className="home-title">Explore. Assess. Prepare.</h1>
      <p className="home-sub">
        DisasterGuard AI provides experimental decision-support tools using weather,
        regional observations, historical reports, and reference data. Data availability
        varies by location; no hazard-specific prediction capability is validated.
      </p>
      <Link className="btn btn-lg" to={user ? '/dashboard' : '/register'}>
        {user ? 'Go to dashboard' : 'Get started'}
      </Link>

      <div className="grid cards4" style={{ marginTop: '2.2rem' }}>
        {FEATURES.map(([icon, title, desc]) => (
          <div className="card" key={title}>
            <div style={{ fontSize: '1.4rem' }}>{icon}</div>
            <div className="sectitle" style={{ marginTop: '.4rem' }}>{title}</div>
            <div style={{ fontSize: '.82rem', color: 'var(--ink2)', lineHeight: 1.5 }}>{desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
