import { apiPost } from './api.js'
import { fetchOnDemandWeather } from './weatherService.js'

export async function predictRisk(location) {
  const weather = await fetchOnDemandWeather(location)
  if (weather.freshnessStatus !== 'READY') {
    throw new Error('The weather observation is stale; no estimate was created.')
  }
  const rainfall = weather.rainMm ?? weather.precipitationMm
  if (rainfall == null || weather.temperatureC == null || weather.windKmh == null) {
    throw new Error('The current weather response is missing rainfall, temperature, or wind; no estimate was created.')
  }

  const data = await apiPost('/predictions', {
    disaster_type: 'flood',
    latitude: station.lat,
    longitude: station.lng,
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
