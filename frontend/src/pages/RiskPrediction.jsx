import { useEffect, useRef, useState } from 'react'
import { predictRisk, ADJUSTABLE_FEATURES } from '../services/predictionService'
import { searchLocations } from '../services/locationSearchService'
import PredictionCard from '../components/PredictionCard'
import Loading from '../components/Loading'
import WeatherCard from '../components/WeatherCard'

const initial = Object.fromEntries(ADJUSTABLE_FEATURES.map(f => [f.key, 6]))
const DEFAULT_LOCATION = {
  id: 'kochi-default',
  name: 'Kochi',
  admin1: 'Kerala',
  admin2: 'Ernakulam',
  country: 'India',
  display_name: 'Kochi, Kerala, India',
  latitude: 9.9312,
  longitude: 76.2673,
}

export default function RiskPrediction() {
  const [selected, setSelected] = useState(DEFAULT_LOCATION)
  const [query, setQuery] = useState(DEFAULT_LOCATION.display_name)
  const [results, setResults] = useState([])
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [values, setValues] = useState(initial)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const requestIdRef = useRef(0)

  useEffect(() => {
    const trimmed = query.trim()
    if (!trimmed || trimmed.length < 2) {
      setResults([])
      setSearchLoading(false)
      setSearchError('')
      return undefined
    }

    const currentRequest = ++requestIdRef.current
    setSearchLoading(true)
    setSearchError('')
    const timeoutId = setTimeout(async () => {
      try {
        const matches = await searchLocations(trimmed)
        if (currentRequest !== requestIdRef.current) return
        setResults(matches)
        setHighlightedIndex(matches.length ? 0 : -1)
      } catch (requestError) {
        if (requestError?.name === 'AbortError') return
        if (currentRequest !== requestIdRef.current) return
        setResults([])
        setSearchError('Unable to search locations right now. Please try a broader place name or retry in a moment.')
      } finally {
        if (currentRequest === requestIdRef.current) {
          setSearchLoading(false)
        }
      }
    }, 350)

    return () => {
      clearTimeout(timeoutId)
    }
  }, [query])

  function handleLocationSelect(location) {
    if (!location || !Number.isFinite(Number(location.latitude)) || !Number.isFinite(Number(location.longitude))) {
      setSearchError('The chosen location is missing valid coordinates.')
      return
    }

    const nextLocation = {
      ...location,
      latitude: Number(location.latitude),
      longitude: Number(location.longitude),
      display_name: location.display_name || [location.name, location.admin1, location.country].filter(Boolean).join(', '),
    }
    setSelected(nextLocation)
    setQuery(nextLocation.display_name)
    setResults([])
    setSearchError('')
    setHighlightedIndex(-1)
  }

  function handleSearchKeyDown(event) {
    if (!results.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlightedIndex(index => (index + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlightedIndex(index => (index <= 0 ? results.length - 1 : index - 1))
    } else if (event.key === 'Enter' && highlightedIndex >= 0) {
      event.preventDefault()
      handleLocationSelect(results[highlightedIndex])
    } else if (event.key === 'Escape') {
      setResults([])
      setHighlightedIndex(-1)
    }
  }

  async function run() {
    setError('')
    setLoading(true)
    try {
      const weatherAwareStation = {
        ...selected,
        name: selected.display_name || selected.name,
        lat: selected.latitude,
        lng: selected.longitude,
      }
      const r = await predictRisk(values, weatherAwareStation)
      setResult(r)
    } catch (requestError) {
      setError(requestError.message || 'Could not run prediction.')
    } finally {
      setLoading(false)
    }
  }

  const canPredict = Number.isFinite(selected.latitude) && Number.isFinite(selected.longitude)

  return (
    <div>
      <h2 className="title">Risk prediction</h2>
      <p className="sub">Choose a location by city, district, state, or country. The selected coordinates are validated before being sent to the backend weather and prediction services.</p>
      <p className="explain">This project still requires a real trained flood model artifact and a compatible data schema. Without that artifact, backend predictions remain clearly labelled weather heuristics instead of genuine ML inference.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Inputs</div>

          <label htmlFor="location-search">Location search</label>
          <input
            id="location-search"
            type="text"
            value={query}
            onChange={event => setQuery(event.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search for Kochi, Hyderabad, Telangana, India…"
            autoComplete="off"
          />

          {searchLoading && <div className="explain" style={{ marginTop: '.5rem' }}>Searching supported locations…</div>}
          {searchError && <p className="error" role="alert">{searchError}</p>}

          {results.length > 0 && (
            <div className="search-results" style={{ marginTop: '.75rem' }} role="listbox" aria-label="Location search results">
              {results.map((location, index) => (
                <button
                  key={`${location.name}-${location.latitude}-${location.longitude}-${index}`}
                  type="button"
                  className="search-option"
                  onClick={() => handleLocationSelect(location)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    marginBottom: '.4rem',
                    background: highlightedIndex === index ? 'rgba(110, 145, 255, 0.12)' : 'transparent',
                    border: '1px solid rgba(255,255,255,0.15)',
                    color: 'inherit',
                    padding: '.65rem .75rem',
                    borderRadius: '.5rem',
                    cursor: 'pointer',
                  }}
                >
                  <strong>{location.name}</strong>
                  <div className="explain">{[location.admin1, location.admin2, location.country].filter(Boolean).join(', ') || 'Administrative area unavailable'}</div>
                  <div className="explain">{location.latitude.toFixed(4)}, {location.longitude.toFixed(4)}</div>
                </button>
              ))}
            </div>
          )}

          {!searchLoading && query.trim().length >= 2 && !searchError && !results.length && (
            <p className="explain" style={{ marginTop: '.75rem' }}>No supported locations matched that search. Try a broader city, district, or state name.</p>
          )}

          <div style={{ marginTop: '.9rem' }} className="formgrid">
            <div className="kv"><span>Location</span><span>{selected.display_name || selected.name}</span></div>
            <div className="kv"><span>Latitude</span><span>{selected.latitude.toFixed(4)}</span></div>
            <div className="kv"><span>Longitude</span><span>{selected.longitude.toFixed(4)}</span></div>
            <div className="kv"><span>Country</span><span>{selected.country || 'Unknown'}</span></div>
          </div>

          <div style={{ marginTop: '.8rem' }} className="formgrid">
            {ADJUSTABLE_FEATURES.map(f => (
              <div key={f.key}>
                <label>{f.label} <span className="rangeval">{values[f.key]}</span></label>
                <input type="range" min="0" max="16" value={values[f.key]} onChange={e => setValues(v => ({ ...v, [f.key]: +e.target.value }))} />
              </div>
            ))}
          </div>
          <button className="btn" onClick={run} disabled={loading || !canPredict}>{loading ? 'Running…' : 'Run prediction'}</button>
          {error && <p className="error" role="alert">{error}</p>}
        </div>

        <div>
          {loading && !result ? <div className="card"><Loading label="Running model…" /></div> : <PredictionCard result={result} title={`Prediction — ${selected.display_name || selected.name}`} />}
          <div style={{ marginTop: '1rem' }}>
            <WeatherCard station={{ name: selected.display_name || selected.name, lat: selected.latitude, lng: selected.longitude }} />
          </div>
        </div>
      </div>
    </div>
  )
}
