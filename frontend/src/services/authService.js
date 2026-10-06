import { apiPost } from './api'

const KEY = 'disasterguard_user'
const TOKEN_KEY = 'disasterguard_access_token'

export async function login(email, password) {
  const result = await apiPost('/auth/login', { email: email.trim().toLowerCase(), password })
  const user = result.user
  localStorage.setItem(KEY, JSON.stringify(user))
  localStorage.setItem(TOKEN_KEY, result.access_token)
  return user
}

export async function register(name, email, password) {
  await apiPost('/auth/register', {
    name: name.trim(),
    email: email.trim().toLowerCase(),
    password,
  })
  return login(email, password)
}

export function logout() {
  localStorage.removeItem(KEY)
  localStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem('disasterguard_latest_prediction')
  sessionStorage.removeItem('disasterguard_last_simulation')
}

export function getCurrentUser() {
  try {
    if (!localStorage.getItem(TOKEN_KEY)) return null
    const raw = localStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function isAuthenticated() {
  return !!getCurrentUser()
}
