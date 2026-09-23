// Real integration with Open-Meteo (https://open-meteo.com) — free, no API key.
// Used to pull live rainfall/temperature for a station's coordinates.
const OPEN_METEO_URL = 'https://api.open-meteo.com/v1/forecast'

export async function fetchLiveWeather(lat, lng) {
  const params = new URLSearchParams({
    latitude: lat,
    longitude: lng,
    current: 'temperature_2m,precipitation,rain,wind_speed_10m',
    daily: 'precipitation_sum',
    timezone: 'auto',
  })
  const res = await fetch(`${OPEN_METEO_URL}?${params.toString()}`, { signal: AbortSignal.timeout(5000) })
  if (!res.ok) throw new Error(`Open-Meteo request failed: ${res.status}`)
  const data = await res.json()
  return {
    temperatureC: data.current?.temperature_2m ?? null,
    precipitationMm: data.current?.precipitation ?? null,
    rainMm: data.current?.rain ?? null,
    windKmh: data.current?.wind_speed_10m ?? null,
    todayRainfallMm: data.daily?.precipitation_sum?.[0] ?? null,
    fetchedAt: data.current?.time ?? null,
  }
}
