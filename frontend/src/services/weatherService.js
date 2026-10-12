import { apiGet } from './api'

export async function fetchLiveWeather(lat, lng) {
  const [snapshot, status] = await Promise.all([
    apiGet('/weather/latest'),
    apiGet('/weather/status'),
  ])
  const station = snapshot.observations.reduce((nearest, observation) => {
    const distance = (observation.latitude - lat) ** 2 + (observation.longitude - lng) ** 2
    return !nearest || distance < nearest.distance ? { observation, distance } : nearest
  }, null)
  if (!station || station.distance > 0.0004) {
    const error = new Error('Weather is not ready for this location yet. The backend collector is fetching its first Open-Meteo reading; retry shortly.')
    error.code = 'WEATHER_NOT_READY'
    throw error
  }

  const reading = station.observation
  const requiredMeasurements = {
    temperature_c: reading.temperature_c,
    precipitation_mm: reading.precipitation_mm,
    wind_speed_kmh: reading.wind_speed_kmh,
  }
  const missingMeasurements = Object.entries(requiredMeasurements)
    .filter(([, value]) => value == null || !Number.isFinite(Number(value)))
    .map(([name]) => name)
  if (missingMeasurements.length) {
    const error = new Error(`The stored weather observation is missing ${missingMeasurements.join(', ')}. No estimate was created.`)
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  const observationTime = new Date(reading.observation_time)
  const ageSeconds = (Date.now() - observationTime.getTime()) / 1000
  if (!Number.isFinite(ageSeconds)) {
    const error = new Error('The stored weather observation has an invalid timestamp. No estimate was created.')
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  if (ageSeconds < -300) {
    const error = new Error('The stored weather observation timestamp is more than five minutes in the future. No estimate was created.')
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  if (
    !Number.isFinite(status.max_age_seconds)
    || status.max_age_seconds <= 0
    || ageSeconds > status.max_age_seconds
  ) {
    const observedAt = observationTime.toLocaleString()
    const error = new Error(`The nearest stored weather observation is stale (observed ${observedAt}); no estimate was created.`)
    error.code = 'WEATHER_NOT_READY'
    throw error
  }
  return {
    observationId: reading.id,
    temperatureC: reading.temperature_c,
    humidityPercent: reading.humidity_percent,
    precipitationMm: reading.precipitation_mm,
    rainMm: reading.rain_mm,
    windKmh: reading.wind_speed_kmh,
    pressureHpa: reading.pressure_hpa,
    observationTime: reading.observation_time,
    fetchedAt: reading.fetched_at,
    source: reading.source,
    collector: snapshot.collector,
  }
}
