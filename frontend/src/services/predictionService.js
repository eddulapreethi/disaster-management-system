import { apiPost } from './api'
import { fetchLiveWeather } from './weatherService'

export async function predictRisk(station) {
  if (station?.lat == null || station?.lng == null) {
    throw new Error('Select a location with valid coordinates before requesting a weather estimate.')
  }
  const weather = await fetchLiveWeather(station.lat, station.lng)
  const rainfall = weather.rainMm ?? weather.precipitationMm
  if (rainfall == null || weather.temperatureC == null || weather.windKmh == null) {
    throw new Error('A stored weather observation is missing rainfall, temperature, or wind; no estimate was created.')
  }

  const data = await apiPost('/predictions', {
    disaster_type: 'flood',
    latitude: station.lat,
    longitude: station.lng,
    weather_observation_id: weather.observationId,
    rainfall_mm: rainfall,
    temperature_c: weather.temperatureC,
    wind_speed_kmh: weather.windKmh,
  })
  const prediction = data.prediction
  const result = {
    offline: false,
    model_source: data.model_source,
    model_version: data.model_version,
    target_value: data.target_value,
    target_interpretation: data.target_interpretation,
    disaster_type: prediction.disaster_type,
    risk_score: prediction.risk_score,
    risk_band: data.risk_band,
    explanation: data.explanation,
    top_contributions: data.top_contributions || [],
    recommendations: data.recommendations || [],
    input_provenance: data.input_provenance,
    input_observation: prediction,
  }
  sessionStorage.setItem('disasterguard_latest_prediction', JSON.stringify(result))
  return result
}
