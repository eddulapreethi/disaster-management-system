// NOTE: This is a UI-only placeholder. There is no real backend authentication
// endpoint yet — it stores a fake session in localStorage so the Login/Register
// screens and protected routes work end-to-end. Wire this up to
// backend/app/api/auth.py once that exists.
const KEY = 'disasterguard_user'

export function login(email, _password) {
  const user = { email, name: email.split('@')[0] }
  localStorage.setItem(KEY, JSON.stringify(user))
  return user
}

export function register(name, email, _password) {
  const user = { email, name }
  localStorage.setItem(KEY, JSON.stringify(user))
  return user
}

export function logout() {
  localStorage.removeItem(KEY)
}

export function getCurrentUser() {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function isAuthenticated() {
  return !!getCurrentUser()
}
