import { apiGet } from './api.js'
import { normalizeLocation } from './location.js'

export function createWeatherRequestSequence() {
  let latestRequest = 0
  return {
    next() {
      latestRequest += 1
      return latestRequest
    },
    isCurrent(requestId) {
      return requestId === latestRequest
    },
    invalidate() {
      latestRequest += 1
    },
  }
}

export async function fetchOnDemandWeather(location) {
  const selectedLocation = normalizeLocation(location)
  const query = new URLSearchParams({
    latitude: String(selectedLocation.latitude),
    longitude: String(selectedLocation.longitude),
  })
  const reading = await apiGet(`/weather/current?${query}`)
  const requiredMeasurements = {
    temperature_c: reading.temperature_c,
    precipitation_mm: reading.precipitation_mm,
    wind_speed_kmh: reading.wind_speed_kmh,
  }
  const missingMeasurements = Object.entries(requiredMeasurements)
    .filter(([, value]) => value == null || !Number.isFinite(Number(value)))
    .map(([name]) => name)
  if (missingMeasurements.length) {
    const error = new Error(`The weather provider omitted ${missingMeasurements.join(', ')}. No estimate was created.`)
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  const observationTime = new Date(reading.observation_time)
  const ageSeconds = (Date.now() - observationTime.getTime()) / 1000
  if (!Number.isFinite(ageSeconds)) {
    const error = new Error('The weather provider returned an invalid observation timestamp. No estimate was created.')
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  if (ageSeconds < -300) {
    const error = new Error('The weather provider observation timestamp is more than five minutes in the future. No estimate was created.')
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  const freshnessStatus = reading.freshness_status
    || (ageSeconds > Number(reading.max_age_seconds) ? 'STALE' : 'READY')
  if (!['READY', 'STALE'].includes(freshnessStatus)) {
    const error = new Error('The weather provider did not return an available observation. No estimate was created.')
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  return {
    temperatureC: reading.temperature_c,
    humidityPercent: reading.humidity_percent,
    precipitationMm: reading.precipitation_mm,
    rainMm: reading.rain_mm,
    windKmh: reading.wind_speed_kmh,
    pressureHpa: reading.pressure_hpa,
    observationTime: reading.observation_time,
    fetchedAt: reading.fetched_at,
    source: reading.source,
    freshnessStatus,
    coverageStatus: reading.coverage_status
      || (freshnessStatus === 'READY' ? 'SUPPORTED' : freshnessStatus),
    freshnessMessage: reading.freshness_message || '',
    observationAgeSeconds: Number.isFinite(Number(reading.observation_age_seconds))
      ? Number(reading.observation_age_seconds)
      : Math.max(0, Math.floor(ageSeconds)),
    maxAgeSeconds: Number(reading.max_age_seconds),
    latitude: reading.provider_latitude ?? reading.latitude ?? selectedLocation.latitude,
    longitude: reading.provider_longitude ?? reading.longitude ?? selectedLocation.longitude,
    requestedLatitude: reading.requested_latitude ?? selectedLocation.latitude,
    requestedLongitude: reading.requested_longitude ?? selectedLocation.longitude,
    measurementUnits: reading.measurement_units || {},
    provenance: reading.provenance || null,
  }
}
