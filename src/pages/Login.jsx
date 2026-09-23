import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { login } from '../services/authService'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  function handleSubmit(e) {
    e.preventDefault()
    login(email, password)
    navigate('/dashboard')
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h2 className="title">Log in</h2>
        <p className="sub">This is a UI-only login for the prototype — no real backend auth yet.</p>
        <label>Email</label>
        <input className="text-input" type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        <label style={{ marginTop: '.7rem' }}>Password</label>
        <input className="text-input" type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
        <button className="btn" style={{ width: '100%', marginTop: '1rem' }} type="submit">Log in</button>
        <p className="auth-switch">No account? <Link to="/register">Sign up</Link></p>
      </form>
    </div>
  )
}
