import { apiGet } from './api'

export async function searchLocations(query, signal) {
  const trimmed = (query || '').trim()
  if (!trimmed || trimmed.length < 2) return []

  const payload = await apiGet(`/geocoding/search?query=${encodeURIComponent(trimmed)}&limit=8`, { signal })
  return Array.isArray(payload?.results) ? payload.results : []
}
