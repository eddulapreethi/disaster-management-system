import { Link, useNavigate } from 'react-router-dom'
import { getCurrentUser, logout } from '../services/authService'

export default function Navbar({ backendOnline, theme, onToggleTheme }) {
  const navigate = useNavigate()
  const user = getCurrentUser()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="brand">
          <div className="mark">
            <svg viewBox="0 0 24 24" fill="none">
              <path d="M12 2L3 6v6c0 5 4 8.5 9 10 5-1.5 9-5 9-10V6l-9-4z" stroke="white" strokeWidth="1.6" />
              <path d="M9 12l2 2 4-4" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="brandname">DisasterGuard AI</div>
            <div className="brandsub">Predictive analytics &amp; decision support</div>
          </div>
        </Link>

        <span className={`statuspill ${backendOnline ? 'on' : 'off'}`}>
          {backendOnline === null ? 'checking…' : backendOnline ? '● backend online' : '● backend offline'}
        </span>

        {user ? (
          <div className="navbar-user">
            <span className="navbar-email">{user.email}</span>
            <button className="btn-outline" onClick={handleLogout}>Log out</button>
          </div>
        ) : (
          <div className="navbar-user">
            <Link className="btn-outline" to="/login">Log in</Link>
            <Link className="btn" to="/register">Sign up</Link>
          </div>
        )}
        <button className="themebtn" onClick={onToggleTheme} title="Toggle theme">◐</button>
      </div>
    </header>
  )
}
