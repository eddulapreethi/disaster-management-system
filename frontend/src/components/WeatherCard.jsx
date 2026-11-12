import { useEffect, useRef, useState } from 'react'
import { createWeatherRequestSequence, fetchOnDemandWeather } from '../services/weatherService'
import Loading from './Loading'

function formatTimestamp(value) {
  if (!value) return 'Unavailable'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Invalid provider timestamp' : parsed.toLocaleString()
}

export default function WeatherCard({ location }) {
  const [weather, setWeather] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const requestSequence = useRef(null)
  if (!requestSequence.current) requestSequence.current = createWeatherRequestSequence()

  useEffect(() => {
    let cancelled = false
    setWeather(null)
    setLoading(true)
    async function refresh() {
      const requestId = requestSequence.current.next()
      setError(null)
      try {
        const reading = await fetchOnDemandWeather(location)
        if (!cancelled && requestSequence.current.isCurrent(requestId)) setWeather(reading)
      } catch (requestError) {
        if (!cancelled && requestSequence.current.isCurrent(requestId)) {
          setError(requestError.message || 'Open-Meteo weather is unavailable.')
        }
      } finally {
        if (!cancelled && requestSequence.current.isCurrent(requestId)) setLoading(false)
      }
    }
    refresh()
    const interval = setInterval(refresh, 5 * 60_000)
    return () => {
      cancelled = true
      requestSequence.current.invalidate()
      clearInterval(interval)
    }
  }, [location?.latitude, location?.longitude])

  const units = weather?.measurementUnits || {}
  const freshnessStatus = weather?.freshnessStatus || 'UNAVAILABLE'
  const freshnessClass = freshnessStatus === 'READY' ? 'low' : freshnessStatus === 'STALE' ? 'med' : 'high'

  return (
    <div className="card weather-card">
      <div className="sectitle">Open-Meteo weather — {location?.display_name || location?.name}</div>
      {loading && <Loading label="Requesting provider weather…" />}
      {error && <div className="error" role="alert">Weather unavailable: {error}</div>}
      {error && <div className="kv"><span>Weather source coverage for this point</span><span className="pill high">UNAVAILABLE</span></div>}
      {weather && !loading && !error && (
        <>
          <div className="kv">
            <span>Weather source coverage for this point</span>
            <span className={`pill ${weather.coverageStatus === 'SUPPORTED' ? 'low' : weather.coverageStatus === 'STALE' ? 'med' : 'high'}`}>{weather.coverageStatus}</span>
          </div>
          <div className="kv">
            <span>Observation freshness</span>
            <span className={`pill ${freshnessClass}`}>{freshnessStatus}</span>
          </div>
          {freshnessStatus === 'STALE' && (
            <p className="error" role="status">{weather.freshnessMessage || 'The provider timestamp is outside the configured freshness window. Values below are stale, not current.'}</p>
          )}
          <div className="formgrid">
            <div className="kv"><span>Temperature</span><span>{weather.temperatureC ?? '—'} {units.temperature_c || '°C'}</span></div>
            <div className="kv"><span>Precipitation</span><span>{weather.precipitationMm ?? '—'} {units.precipitation_mm || 'mm'}</span></div>
            <div className="kv"><span>Rain</span><span>{weather.rainMm ?? '—'} {units.rain_mm || 'mm'}</span></div>
            <div className="kv"><span>Humidity</span><span>{weather.humidityPercent ?? '—'} {units.humidity_percent || '%'}</span></div>
            <div className="kv"><span>Wind speed</span><span>{weather.windKmh ?? '—'} {units.wind_speed_kmh || 'km/h'}</span></div>
            <div className="kv"><span>Pressure</span><span>{weather.pressureHpa ?? '—'} {units.pressure_hpa || 'hPa'}</span></div>
          </div>
          <p className="explain">Source: {weather.source || 'Open-Meteo'}.</p>
          <p className="explain">Provider observation time: {formatTimestamp(weather.observationTime)} · Backend fetch time: {formatTimestamp(weather.fetchedAt)}.</p>
          <p className="explain">
            Selected coordinates: {weather.requestedLatitude?.toFixed(5)}, {weather.requestedLongitude?.toFixed(5)}.
            {' '}Provider grid coordinates: {weather.latitude?.toFixed(5)}, {weather.longitude?.toFixed(5)}.
          </p>
          <p className="explain">Fetched on demand from a weather provider; this is not a local sensor reading. Weather alone does not establish river levels or flood conditions.</p>
        </>
      )}
    </div>
  )
}
