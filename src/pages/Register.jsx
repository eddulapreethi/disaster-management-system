import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { register } from '../services/authService'

export default function Register() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const navigate = useNavigate()

  function handleSubmit(e) {
    e.preventDefault()
    register(name, email, password)
    navigate('/dashboard')
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={handleSubmit}>
        <h2 className="title">Create an account</h2>
        <p className="sub">UI-only registration for now — wire this up to a real backend auth endpoint later.</p>
        <label>Name</label>
        <input className="text-input" required value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
        <label style={{ marginTop: '.7rem' }}>Email</label>
        <input className="text-input" type="email" required value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
        <label style={{ marginTop: '.7rem' }}>Password</label>
        <input className="text-input" type="password" required value={password} onChange={e => setPassword(e.target.value)} placeholder="••••••••" />
        <button className="btn" style={{ width: '100%', marginTop: '1rem' }} type="submit">Sign up</button>
        <p className="auth-switch">Already have an account? <Link to="/login">Log in</Link></p>
      </form>
    </div>
  )
}
