import { useEffect, useState } from 'react'
import { fetchLocationCoverage } from '../services/coverageService'

function statusClass(status) {
  if (status === 'SUPPORTED') return 'low'
  if (status === 'STALE') return 'med'
  if (status === 'UNAVAILABLE') return 'high'
  return ''
}

export default function LocationCoverage({ location }) {
  const [coverage, setCoverage] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let active = true
    if (!location) {
      setCoverage(null)
      setError('')
      setLoading(false)
      return () => { active = false }
    }

    setCoverage(null)
    setError('')
    setLoading(true)
    fetchLocationCoverage(location)
      .then(result => {
        if (active) setCoverage(result)
      })
      .catch(requestError => {
        if (active) setError(requestError.message || 'Provider coverage could not be checked.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [location?.latitude, location?.longitude])

  return (
    <section className="detailbox" aria-label="Location-specific provider coverage">
      <div className="sectitle">Source coverage for this location</div>
      {loading && <p role="status">Checking configured source coverage…</p>}
      {error && <p className="error" role="alert">Coverage unavailable: {error}</p>}
      {coverage && (
        <>
          {coverage.providers.map(provider => (
            <div className="kv" key={`${provider.provider}-${provider.capability}-${provider.product}`}>
              <span>
                {provider.provider} · {provider.capability}
                <small className="explain" style={{ display: 'block' }}>{provider.scope}</small>
                <small className="explain" style={{ display: 'block' }}>{provider.details}</small>
              </span>
              <span className={`pill ${statusClass(provider.status)}`}>{provider.status}</span>
            </div>
          ))}
          <p className="explain">
            These statuses describe configured source scope, not a live provider coverage check. On-demand weather results are separate; reference GIS and regional hydrology do not establish hazard prediction availability.
          </p>
        </>
      )}
    </section>
  )
}
