import { apiPost } from './api'

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
  const contribs = [
    { feature: 'MonsoonIntensity', description: 'Intensity of monsoon rainfall', shap_contribution: f.MonsoonIntensity * 0.031 },
    { feature: 'DrainageSystems', description: 'Urban drainage system capacity', shap_contribution: -f.DrainageSystems * 0.024 },
    { feature: 'RiverManagement', description: 'Quality of river channel management', shap_contribution: -f.RiverManagement * 0.022 },
    { feature: 'Deforestation', description: 'Level of deforestation in the catchment', shap_contribution: f.Deforestation * 0.020 },
    { feature: 'Encroachments', description: 'Encroachment onto floodplains/waterways', shap_contribution: f.Encroachments * 0.018 },
  ].sort((a, b) => Math.abs(b.shap_contribution) - Math.abs(a.shap_contribution))

  return {
    offline: true,
    flood_probability: score / 100,
    risk_score: score,
    risk_band: score >= 65 ? 'high' : score >= 45 ? 'medium' : 'low',
    explanation: `Offline estimate (backend not reachable): risk score ${score}/100, driven mainly by ${contribs[0].feature}.`,
    top_contributions: contribs,
  }
}

export async function predictRisk(partialFeatures) {
  const features = { ...DEFAULT_FEATURES, ...partialFeatures }
  try {
    const data = await apiPost('/predict', features)
    return { ...data, offline: false }
  } catch {
    return localFallback(features)
  }
}
