import { apiGet } from './api'

export async function fetchLiveWeather(lat, lng) {
  const validNumber = value => (
    (typeof value === 'number' || typeof value === 'string')
    && String(value).trim() !== ''
    && Number.isFinite(Number(value))
  )
  const latitude = Number(lat)
  const longitude = Number(lng)
  if (!validNumber(lat) || !validNumber(lng)
    || latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
    throw new Error('Select a location with valid latitude and longitude coordinates.')
  }
  const query = new URLSearchParams({ latitude: String(latitude), longitude: String(longitude) })
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
  }
}
