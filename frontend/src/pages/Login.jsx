import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login } from '../services/authService'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/dashboard')
    } catch (requestError) {
      setError(requestError.message || 'Unable to log in.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h2 className="title">Log in</h2>
        <p className="sub">Log in to your DisasterGuard account.</p>
        <label>Email</label>
        <input className="text-input" type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        <label style={{ marginTop: '.7rem' }}>Password</label>
        <input className="text-input" type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
        {error && <p role="alert" className="error">{error}</p>}
        <button className="btn" style={{ width: '100%', marginTop: '1rem' }} type="submit" disabled={loading}>{loading ? 'Logging in...' : 'Log in'}</button>
        <p className="auth-switch">No account? <Link to="/register">Sign up</Link></p>
      </form>
    </div>
  )
}
