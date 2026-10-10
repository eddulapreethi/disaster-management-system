import { useEffect, useRef, useState } from 'react'
import { searchLocations } from '../services/locationSearchService'

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

export default function LocationSearchField({ value = DEFAULT_LOCATION, onChange, label = 'Location search' }) {
  const [query, setQuery] = useState(value?.display_name || value?.name || 'Kochi')
  const [results, setResults] = useState([])
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [searchLoading, setSearchLoading] = useState(false)
  const [searchError, setSearchError] = useState('')
  const requestIdRef = useRef(0)

  useEffect(() => {
    if (value?.display_name || value?.name) {
      setQuery(value.display_name || value.name)
    }
  }, [value])

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
    onChange?.(nextLocation)
    setResults([])
    setSearchError('')
    setHighlightedIndex(-1)
    setQuery(nextLocation.display_name)
  }

  function handleSearchKeyDown(event) {
    if (!results.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault(); setHighlightedIndex(index => (index + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault(); setHighlightedIndex(index => (index <= 0 ? results.length - 1 : index - 1))
    } else if (event.key === 'Enter' && highlightedIndex >= 0) {
      event.preventDefault(); handleLocationSelect(results[highlightedIndex])
    } else if (event.key === 'Escape') {
      setResults([]); setHighlightedIndex(-1)
    }
  }

  return (
    <>
      <label htmlFor="location-search">{label}</label>
      <input
        id="location-search"
        type="text"
        value={query}
        onChange={event => setQuery(event.target.value)}
        onKeyDown={handleSearchKeyDown}
        placeholder="Search for Kochi, Hyderabad, Telangana, Paris, Nairobi…"
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
              <div className="explain">{Number(location.latitude).toFixed(4)}, {Number(location.longitude).toFixed(4)}</div>
            </button>
          ))}
        </div>
      )}
      {!searchLoading && query.trim().length >= 2 && !searchError && !results.length && (
        <p className="explain" style={{ marginTop: '.75rem' }}>No supported locations matched that search. Try a broader city, district, or state name.</p>
      )}
    </>
  )
}
