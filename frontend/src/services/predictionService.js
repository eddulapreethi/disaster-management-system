import { apiPost } from './api'
import { fetchLiveWeather } from './weatherService'

// All 20 features the trained model expects, each 0-16.
export const DEFAULT_FEATURES = {
  MonsoonIntensity: 5, TopographyDrainage: 5, RiverManagement: 5, Deforestation: 5,
  Urbanization: 5, ClimateChange: 5, DamsQuality: 5, Siltation: 5,
  AgriculturalPractices: 5, Encroachments: 5, IneffectiveDisasterPreparedness: 5,
  DrainageSystems: 5, CoastalVulnerability: 5, Landslides: 5, Watersheds: 5,
  DeterioratingInfrastructure: 5, PopulationScore: 5, WetlandLoss: 5,
  InadequatePlanning: 5, PoliticalFactors: 5,
}

export const ADJUSTABLE_FEATURES = [
  { key: 'MonsoonIntensity', label: 'Monsoon intensity' },
  { key: 'RiverManagement', label: 'River management quality', inverse: true },
  { key: 'DrainageSystems', label: 'Drainage system capacity', inverse: true },
  { key: 'Deforestation', label: 'Deforestation level' },
  { key: 'Urbanization', label: 'Urbanization pressure' },
  { key: 'Encroachments', label: 'Floodplain encroachment' },
  { key: 'ClimateChange', label: 'Climate-change stress' },
  { key: 'InadequatePlanning', label: 'Planning inadequacy' },
]

function localFallback(features) {
  const f = features
  const raw =
    f.MonsoonIntensity * 3.1 + f.Deforestation * 2.0 + f.Urbanization * 1.6 +
    f.Encroachments * 1.8 + f.ClimateChange * 1.4 + f.InadequatePlanning * 1.5 -
    f.RiverManagement * 2.2 - f.DrainageSystems * 2.4
  const score = Math.max(2, Math.min(98, Math.round(raw + 25)))
  return {
    offline: true,
    model_source: 'offline_demo',
    disaster_type: 'flood',
    flood_probability: score / 100,
    risk_score: score,
    risk_band: score >= 65 ? 'high' : score >= 45 ? 'medium' : 'low',
    explanation: `Offline demonstration estimate (${score}/100). No trained model or SHAP explanation was available.`,
    top_contributions: [],
  }
}

export async function predictRisk(partialFeatures, station) {
  const features = { ...DEFAULT_FEATURES, ...partialFeatures }
  try {
    let weather = null
    if (station?.lat != null && station?.lng != null) {
      try {
        weather = await fetchLiveWeather(station.lat, station.lng)
      } catch {
        weather = null
      }
    }
    const data = await apiPost('/predictions', {
      disaster_type: 'flood',
      latitude: station?.lat ?? 0,
      longitude: station?.lng ?? 0,
      rainfall_mm: weather?.todayRainfallMm ?? weather?.rainMm ?? 0,
      temperature_c: weather?.temperatureC ?? 25,
      wind_speed_kmh: weather?.windKmh ?? 0,
      features,
    })
    const prediction = data.prediction
    const result = {
      offline: false,
      model_source: data.model_source,
      disaster_type: prediction.disaster_type,
      flood_probability: prediction.risk_score / 100,
      risk_score: prediction.risk_score,
      risk_band: data.risk_band,
      explanation: data.explanation,
      top_contributions: data.top_contributions || [],
      recommendations: data.recommendations || [],
    }
    sessionStorage.setItem('disasterguard_latest_prediction', JSON.stringify(result))
    return result
  } catch (error) {
    if (error.status || error.code === 'WEATHER_NOT_READY') throw error
    const result = localFallback(features)
    sessionStorage.setItem('disasterguard_latest_prediction', JSON.stringify(result))
    return result
  }
}
