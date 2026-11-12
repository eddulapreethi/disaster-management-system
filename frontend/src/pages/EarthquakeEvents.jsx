import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import EarthquakeEventMap from '../maps/EarthquakeEventMap'
import LocationSearchField from '../components/LocationSearchField'
import {
  createRequestSequence,
  fetchEarthquakeEvents,
  getEarthquakeRequestError,
} from '../services/earthquakeEventService'
import { useSelectedLocation } from '../services/LocationContext'

function utcDate(value) {
  return value.toISOString().slice(0, 10)
}

function initialFilters() {
  const now = new Date()
  const start = new Date(now.getTime() - 7 * 86400000)
  return {
    startDate: utcDate(start),
    endDate: utcDate(now),
    minMagnitude: '',
    maxMagnitude: '',
    reviewStatus: '',
  }
}

function displayTime(value) {
  return value instanceof Date && Number.isFinite(value.getTime())
    ? value.toLocaleString()
    : 'Unavailable'
}

function EarthquakeDetails({ event }) {
  if (!event) {
    return <div className="detailbox">Select a marker to view event details and source provenance.</div>
  }

  return (
    <section className="detailbox earthquake-detail" aria-label="Selected earthquake event details">
      <h3>{event.title || event.place || `USGS event ${event.id}`}</h3>
      <div className="kv"><span>Source</span><span>USGS ComCat</span></div>
      <div className="kv">
        <span>Magnitude</span>
        <span>{event.magnitude == null ? 'Unavailable' : `${event.magnitude}${event.magnitudeType ? ` ${event.magnitudeType}` : ''}`}</span>
      </div>
      <div className="kv"><span>Event/origin time</span><span>{displayTime(event.eventTime)}</span></div>
      <div className="kv"><span>Source update time</span><span>{displayTime(event.sourceUpdatedAt)}</span></div>
      <div className="kv"><span>Retrieved at</span><span>{displayTime(event.retrievalTime)}</span></div>
      <div className="kv"><span>Depth</span><span>{event.depthKm == null ? 'Unavailable' : `${event.depthKm} km`}</span></div>
      <div className="kv"><span>Provider review status</span><span>{event.reviewStatus || 'Unavailable'}</span></div>
      <div className="kv"><span>Network / source code</span><span>{[event.network, event.sourceCode].filter(Boolean).join(' / ') || 'Unavailable'}</span></div>
      <div className="kv"><span>Coordinates · WGS 84</span><span>{event.latitude.toFixed(4)}, {event.longitude.toFixed(4)}</span></div>
      <div className="kv"><span>Source record ID</span><span>{event.id}</span></div>
      <div className="kv"><span>Attribution</span><span>{event.attribution}</span></div>
      <div className="kv">
        <span>Redistribution terms</span>
        <span>{event.licenseUsageStatus === 'UNKNOWN' ? 'Not verified' : event.licenseUsageStatus}</span>
      </div>
      {event.sourceUrl && (
        <p><a href={event.sourceUrl} target="_blank" rel="noreferrer">Open this event at USGS</a></p>
      )}
      <p className="explain">
        Provider review status is source metadata, not confirmation of damage or disaster impact. This event is not a
        prediction, warning, risk score, or community incident report.
      </p>
    </section>
  )
}

export default function EarthquakeEvents() {
  const { selectedLocation, setSelectedLocation } = useSelectedLocation()
  const [filters, setFilters] = useState(initialFilters)
  const [mapArea, setMapArea] = useState(null)
  const [queryArea, setQueryArea] = useState(null)
  const [result, setResult] = useState(null)
  const [selectedEventId, setSelectedEventId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [refreshVersion, setRefreshVersion] = useState(0)
  const requestSequence = useRef(null)
  if (requestSequence.current === null) requestSequence.current = createRequestSequence()

  const onMapAreaChange = useCallback(area => setMapArea(area), [])
  const selectedEvent = useMemo(
    () => result?.events.find(event => event.id === selectedEventId) || null,
    [result, selectedEventId],
  )

  useEffect(() => {
    if (!queryArea) return undefined

    const requestId = requestSequence.current.next()
    let active = true
    setLoading(true)
    setError('')
    setResult(null)
    setSelectedEventId(null)
    const timer = setTimeout(async () => {
      try {
        const nextResult = await fetchEarthquakeEvents(filters, queryArea)
        if (!active || !requestSequence.current.isCurrent(requestId)) return
        setResult(nextResult)
        setSelectedEventId(nextResult.events[0]?.id || null)
      } catch (requestError) {
        if (!active || !requestSequence.current.isCurrent(requestId)) return
        setResult(null)
        setSelectedEventId(null)
        setError(getEarthquakeRequestError(requestError))
      } finally {
        if (active && requestSequence.current.isCurrent(requestId)) setLoading(false)
      }
    }, 250)

    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [filters, queryArea, refreshVersion])

  function updateFilter(key, value) {
    setFilters(current => ({ ...current, [key]: value }))
  }

  function refreshArea() {
    if (!mapArea) {
      setError('Zoom and pan the map to a bounded area (at most 30° by 20°), then refresh.')
      return
    }
    setError('')
    setQueryArea({ ...mapArea })
    setRefreshVersion(version => version + 1)
  }

  function handleLocationChange(location) {
    setSelectedLocation(location)
    setQueryArea(null)
    setResult(null)
    setSelectedEventId(null)
    setError('')
  }

  return (
    <div className="earthquake-events-page">
      <h2 className="title">USGS earthquake events</h2>
      <p className="sub">
        On-demand, bounded ComCat event catalog results for any global map area. These are reported historical
        earthquake events, not predictions, warnings, impact assessments, or uniformly complete global coverage.
        No matching records do not establish that no earthquake occurred.
      </p>

      <section className="card earthquake-controls" aria-label="Earthquake event filters">
        <h3 className="sectitle">Area and event filters</h3>
        <LocationSearchField
          value={selectedLocation}
          onChange={handleLocationChange}
          label="Search for a global map center (optional)"
          showMap={false}
        />
        <p className="explain">
          Pan and zoom the map to a small area. The service accepts at most 30° longitude by 20° latitude and a
          maximum 30-day time range; no unrestricted world query is made.
        </p>
        <div className="earthquake-filter-grid">
          <div>
            <label htmlFor="earthquake-start-date">Start date (UTC)</label>
            <input id="earthquake-start-date" className="text-input" type="date" value={filters.startDate} onChange={event => updateFilter('startDate', event.target.value)} />
          </div>
          <div>
            <label htmlFor="earthquake-end-date">End date (UTC)</label>
            <input id="earthquake-end-date" className="text-input" type="date" value={filters.endDate} onChange={event => updateFilter('endDate', event.target.value)} />
          </div>
          <div>
            <label htmlFor="earthquake-min-magnitude">Minimum magnitude (optional)</label>
            <input id="earthquake-min-magnitude" className="text-input" type="number" min="-10" max="10" step="any" value={filters.minMagnitude} onChange={event => updateFilter('minMagnitude', event.target.value)} />
          </div>
          <div>
            <label htmlFor="earthquake-max-magnitude">Maximum magnitude (optional)</label>
            <input id="earthquake-max-magnitude" className="text-input" type="number" min="-10" max="10" step="any" value={filters.maxMagnitude} onChange={event => updateFilter('maxMagnitude', event.target.value)} />
          </div>
          <div>
            <label htmlFor="earthquake-review-status">Provider review status</label>
            <select id="earthquake-review-status" className="text-input" value={filters.reviewStatus} onChange={event => updateFilter('reviewStatus', event.target.value)}>
              <option value="">All statuses</option>
              <option value="automatic">Automatic</option>
              <option value="reviewed">Reviewed</option>
            </select>
          </div>
        </div>
        <button className="btn" type="button" onClick={refreshArea} disabled={loading}>
          {loading ? 'Loading events…' : 'Refresh events for current map area'}
        </button>
        {loading && <p role="status">Querying the authenticated backend…</p>}
        {error && <p className="error" role="alert">{error}</p>}
      </section>

      <EarthquakeEventMap
        events={result?.events || []}
        selectedEventId={selectedEventId}
        onSelectEvent={setSelectedEventId}
        location={selectedLocation}
        onMapAreaChange={onMapAreaChange}
      />

      {result?.dataStatus === 'NO_MATCHING_EVENTS' && (
        <div className="card earthquake-empty" role="status">
          No matching USGS catalog events were returned for this area and filter set. This is not evidence that no
          earthquake occurred. The backend does not assess freshness; the query was retrieved at {displayTime(result.retrievedAt)}.
          Query bounds: {queryArea.west.toFixed(2)}, {queryArea.south.toFixed(2)} to {queryArea.east.toFixed(2)}, {queryArea.north.toFixed(2)}.
        </div>
      )}
      {result?.dataStatus === 'AVAILABLE' && (
        <div className="card earthquake-result-status" role="status">
          {result.events.length} event{result.events.length === 1 ? '' : 's'} returned by USGS ComCat. Event time and
          retrieval time are separate. Backend freshness status: {result.freshnessStatus || 'Unavailable'}; no
          independent freshness assessment is performed.
          <div>Retrieved at: {displayTime(result.retrievedAt)}</div>
          <div>
            Query bounds: {queryArea.west.toFixed(2)}, {queryArea.south.toFixed(2)} to {queryArea.east.toFixed(2)}, {queryArea.north.toFixed(2)}.
          </div>
        </div>
      )}
      <EarthquakeDetails event={selectedEvent} />
    </div>
  )
}
