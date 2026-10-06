import { apiGet } from './api'

export async function fetchLiveWeather(lat, lng) {
  const snapshot = await apiGet('/weather/latest')
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
    collector: snapshot.collector,
  }
}
