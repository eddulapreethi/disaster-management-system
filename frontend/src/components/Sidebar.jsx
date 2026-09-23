import { NavLink } from 'react-router-dom'

const LINKS = [
  ['/dashboard', 'Dashboard', '📊'],
  ['/risk-prediction', 'Risk Prediction', '🤖'],
  ['/risk-map', 'Risk Map', '🗺'],
  ['/simulation', 'Digital Twin', '🧪'],
  ['/recommendations', 'Recommendations', '🧠'],
  ['/resource-allocation', 'Resources', '🚑'],
  ['/alerts', 'Alerts', '🚨'],
]

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <nav>
        {LINKS.map(([to, label, icon]) => (
          <NavLink key={to} to={to} className={({ isActive }) => 'side-link' + (isActive ? ' active' : '')}>
            <span className="side-icon">{icon}</span>{label}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
