import { apiGet } from './api.js'
import { normalizeLocation } from './location.js'

export async function fetchLocationCoverage(location, options = {}) {
  const selectedLocation = normalizeLocation(location)
  const query = new URLSearchParams({
    latitude: String(selectedLocation.latitude),
    longitude: String(selectedLocation.longitude),
  })
  return apiGet(`/coverage?${query}`, options)
}
