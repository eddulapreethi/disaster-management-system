import { useEffect, useState } from 'react'
import { fetchLiveWeather } from '../services/weatherService'
import Loading from './Loading'

export default function WeatherCard({ station }) {
  const [weather, setWeather] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    async function refresh() {
      if (!weather) setLoading(true)
      setError(null)
      try {
        const reading = await fetchLiveWeather(station.lat, station.lng)
        if (!cancelled) setWeather(reading)
      } catch (requestError) {
        if (!cancelled) setError(requestError.message || 'Continuously collected weather is unavailable.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    refresh()
    const interval = setInterval(refresh, 5 * 60_000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [station.lat, station.lng])

  return (
    <div className="card weather-card">
      <div className="sectitle">Open-Meteo weather — {station.name}</div>
      {loading && <Loading label="Fetching live weather…" />}
      {error && <div className="explain">{error}</div>}
      {weather && !loading && !error && (
        <>
          <div className="formgrid">
            <div className="kv"><span>Temperature</span><span>{weather.temperatureC ?? '—'}°C</span></div>
            <div className="kv"><span>Current precipitation</span><span>{weather.precipitationMm ?? '—'} mm</span></div>
            <div className="kv"><span>Rain</span><span>{weather.rainMm ?? '—'} mm</span></div>
            <div className="kv"><span>Humidity</span><span>{weather.humidityPercent ?? '—'}%</span></div>
            <div className="kv"><span>Wind speed</span><span>{weather.windKmh ?? '—'} km/h</span></div>
            <div className="kv"><span>Pressure</span><span>{weather.pressureHpa ?? '—'} hPa</span></div>
          </div>
          <p className="explain">Source: {weather.source || 'Open-Meteo'}.</p>
          <p className="explain">Provider observation: {weather.observationTime ? new Date(weather.observationTime).toLocaleString() : 'unknown'} · Fetched by backend: {weather.fetchedAt ? new Date(weather.fetchedAt).toLocaleString() : 'unknown'}.</p>
          <p className="explain">Weather was fetched on demand for the selected coordinates; this is provider data, not a local sensor observation.</p>
        </>
      )}
    </div>
  )
}
