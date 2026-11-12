import { apiGet } from './api.js'

export async function searchLocations(query, signal) {
  const trimmed = (query || '').trim()
  if (!trimmed || trimmed.length < 2) return []

  const payload = await apiGet(`/geocoding/search?query=${encodeURIComponent(trimmed)}&limit=8`, { signal })
  if (!Array.isArray(payload?.results)) return []
  return payload.results.map(result => ({
    ...result,
    metadata_provider: payload.provider || null,
  }))
}
