// Base fetch wrapper for the FastAPI backend.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const TOKEN_KEY = 'disasterguard_access_token'
const USER_KEY = 'disasterguard_user'

function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
  sessionStorage.removeItem('disasterguard_latest_prediction')
  sessionStorage.removeItem('disasterguard_last_simulation')
}

function endpointUrl(path) {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return normalized === '/' ? `${API_BASE}/` : `${API_BASE}/api${normalized}`
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(endpointUrl(path), {
    signal: AbortSignal.timeout(8000),
    ...options,
    headers,
  })
  if (!response.ok) {
    const normalizedPath = path.replace(/^\/+/, '')
    if (response.status === 401 && !normalizedPath.startsWith('auth/')) {
      clearSession()
      if (window.location.pathname !== '/login') {
        window.location.replace('/login')
      }
    }

    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      detail = payload.detail || detail
    } catch {
      // Keep the HTTP status when the response isn't JSON.
    }
    const error = new Error(detail)
    error.status = response.status
    throw error
  }
  if (response.status === 204) return null
  return response.json()
}

export function apiGet(path, opts = {}) {
  return request(path, opts)
}

export function apiPost(path, body, opts = {}) {
  return request(path, { ...opts, method: 'POST', body: JSON.stringify(body) })
}

export async function checkBackend() {
  try {
    await apiGet('/')
    return true
  } catch {
    return false
  }
}
