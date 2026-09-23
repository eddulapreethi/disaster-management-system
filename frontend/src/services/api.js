// Base fetch wrapper for the FastAPI backend.
export const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export async function apiGet(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(4000), ...opts })
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`)
  return res.json()
}

export async function apiPost(path, body, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(4000),
    ...opts,
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}

export async function checkBackend() {
  try {
    await apiGet('/health')
    return true
  } catch {
    return false
  }
}
