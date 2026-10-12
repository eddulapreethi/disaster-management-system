export function simulationMeasurements(weather) {
  const measurements = {
    rainfall_mm: weather.precipitationMm,
    temperature_c: weather.temperatureC,
    wind_speed_kmh: weather.windKmh,
  }
  const missing = Object.entries(measurements)
    .filter(([, value]) => typeof value !== 'number' || !Number.isFinite(value))
    .map(([name]) => name)
  if (missing.length) {
    throw new Error(`Simulation needs complete current weather observations (${missing.join(', ')} unavailable).`)
  }
  return measurements
}
