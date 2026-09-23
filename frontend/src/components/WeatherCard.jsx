import { useEffect, useState } from 'react'
import { fetchLiveWeather } from '../services/weatherService'
import Loading from './Loading'

export default function WeatherCard({ station }) {
  const [weather, setWeather] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchLiveWeather(station.lat, station.lng)
      .then(w => { if (!cancelled) setWeather(w) })
      .catch(() => { if (!cancelled) setError('Live weather unavailable — check your internet connection.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [station])

  return (
    <div className="card weather-card">
      <div className="sectitle">Live weather — {station.name} (Open-Meteo)</div>
      {loading && <Loading label="Fetching live weather…" />}
      {error && <div className="explain">{error}</div>}
      {weather && !loading && !error && (
        <div className="formgrid">
          <div className="kv"><span>Temperature</span><span>{weather.temperatureC ?? '—'}°C</span></div>
          <div className="kv"><span>Current precipitation</span><span>{weather.precipitationMm ?? '—'} mm</span></div>
          <div className="kv"><span>Today's rainfall</span><span>{weather.todayRainfallMm ?? '—'} mm</span></div>
          <div className="kv"><span>Wind speed</span><span>{weather.windKmh ?? '—'} km/h</span></div>
        </div>
      )}
    </div>
  )
}
