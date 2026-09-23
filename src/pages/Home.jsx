import { Link } from 'react-router-dom'
import { getCurrentUser } from '../services/authService'

const FEATURES = [
  ['🤖', 'AI Risk Prediction', 'Trained ML model estimates flood probability from environmental and infrastructure factors.'],
  ['🔍', 'Explainable AI', 'SHAP shows exactly which factors drove each prediction.'],
  ['🗺', 'GIS Risk Map', 'Live map of monitored regions with real coordinates.'],
  ['🧪', 'Digital Twin', 'Simulate what-if scenarios and see projected impact.'],
  ['🧠', 'AI Recommendations', 'Actionable guidance based on predicted risk levels.'],
  ['🚑', 'Resource Optimization', 'Suggested emergency resource allocation per region.'],
]

export default function Home() {
  const user = getCurrentUser()
  return (
    <div className="home-hero">
      <h1 className="home-title">Predict. Explain. Respond.</h1>
      <p className="home-sub">
        DisasterGuard AI combines weather, hydrological, and infrastructure data with
        machine learning to predict disaster risk, explain each prediction, and support
        faster emergency decisions.
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
