import { useEffect, useRef, useState } from 'react'
import {
  createEnvironmentalDataRequestSequence,
  environmentalSourceStatusPresentation,
  fetchEnvironmentalData,
  getEnvironmentalDataNextOffset,
  mergeEnvironmentalDataPages,
} from '../services/environmentalDataService'

const CATEGORY_LABELS = {
  weather_observation: 'Stored weather observations',
  weather_forecast: 'On-demand current weather (not stored here)',
  hydrological_observation: 'Hydrological observations',
  disaster_event_report: 'Unverified application reports (withheld)',
  satellite_scene_metadata: 'Satellite scene metadata',
  geographic_reference_dataset: 'Geographic reference data',
}

function displayTime(record) {
  if (record.observation_time) return `Observed ${record.observation_time}`
  if (record.event_time) return `Event time ${record.event_time}`
  if (record.reported_at) return `Reported ${record.reported_at}; occurrence time unknown`
  if (record.fetched_at) return `Fetched ${record.fetched_at}`
  return 'Timestamp unavailable'
}

function canonicalTimeSummary(timestamps) {
  const parts = []
  if (timestamps.source_timestamp_raw) parts.push(`Source timestamp ${timestamps.source_timestamp_raw}`)
  if (timestamps.timezone_assumption) parts.push(`timezone assumption: ${timestamps.timezone_assumption}`)
  if (timestamps.observation_time_utc) parts.push(`UTC time ${timestamps.observation_time_utc}`)
  if (timestamps.acquisition_time_utc) parts.push(`acquired ${timestamps.acquisition_time_utc}`)
  if (timestamps.retrieval_time_utc) parts.push(`retrieved ${timestamps.retrieval_time_utc}`)
  return parts.join(' · ') || 'Source timestamp metadata unavailable'
}

export default function EnvironmentalDataSummary({ location }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const requestSequence = useRef(null)
  const activeRequestId = useRef(null)
  if (requestSequence.current === null) {
    requestSequence.current = createEnvironmentalDataRequestSequence()
  }

  useEffect(() => {
    const requestId = requestSequence.current.next()
    activeRequestId.current = requestId
    if (!location) {
      setData(null)
      setError('')
      setLoading(false)
      return () => requestSequence.current.invalidate(requestId)
    }

    setData(null)
    setError('')
    setLoading(true)
    setLoadingMore(false)
    fetchEnvironmentalData(location, { offset: 0 })
      .then(result => {
        setData(current => requestSequence.current.isCurrent(requestId) ? result : current)
      })
      .catch(requestError => {
        setError(current => requestSequence.current.isCurrent(requestId)
          ? requestError.message || 'Stored environmental records could not be loaded.'
          : current)
      })
      .finally(() => {
        setLoading(current => requestSequence.current.isCurrent(requestId) ? false : current)
      })
    return () => requestSequence.current.invalidate(requestId)
  }, [location?.latitude, location?.longitude])

  async function loadMore() {
    const requestId = activeRequestId.current
    const nextOffset = getEnvironmentalDataNextOffset(data)
    if (!location || nextOffset === null || loadingMore || !requestSequence.current.isCurrent(requestId)) return

    setError('')
    setLoadingMore(true)
    try {
      const result = await fetchEnvironmentalData(location, { offset: nextOffset })
      const merged = mergeEnvironmentalDataPages(data, result)
      setData(current => requestSequence.current.isCurrent(requestId) ? merged : current)
    } catch (requestError) {
      setError(current => requestSequence.current.isCurrent(requestId)
        ? requestError.message || 'Additional stored records could not be loaded.'
        : current)
    } finally {
      setLoadingMore(current => requestSequence.current.isCurrent(requestId) ? false : current)
    }
  }

  const nextOffset = getEnvironmentalDataNextOffset(data)

  return (
    <section className="detailbox" aria-label="Environmental data for selected location">
      <div className="sectitle">Environmental data and event records</div>
      <p className="explain">This catalog queries stored records only. It does not check upstream provider coverage or determine whether a hazard is present or absent.</p>
      {loading && <p role="status">Checking stored data near this location…</p>}
      {error && <p className="error" role="alert">Stored-data query failed: {error}</p>}
      {data && (
        <>
          {data.sources.map(source => {
            const presentation = environmentalSourceStatusPresentation(source.status)
            return (
              <div className="kv" key={source.category}>
                <span>
                  {CATEGORY_LABELS[source.category] || source.category}
                  <small className="explain" style={{ display: 'block' }}>{source.details}</small>
                </span>
                <span className="explain">
                  <span className={`pill ${presentation.tone}`}>{presentation.label}</span>
                  <small className="explain" style={{ display: 'block' }}>
                    {source.matching_records} matching record(s) · returned page only
                  </small>
                </span>
              </div>
            )
          })}
          {data.records.map(record => (
            <div className="detailbox" key={`${record.category}-${record.record_id}`}>
              <strong>{record.provider} · {record.measurement_category || record.hazard || 'event report'}</strong>
              <div className="explain">{displayTime(record)}</div>
              <div className="explain">
                Quality: {record.quality_status} · Freshness: {record.freshness_status}
              </div>
              {record.validation_findings.map((finding, index) => (
                <div className="explain" key={`${record.record_id}-finding-${index}`}>{finding}</div>
              ))}
              {record.canonical_record && (
                <div className="detailbox" aria-label="Canonical environmental data contract">
                  <strong>
                    Canonical contract v{record.canonical_record.contract_version}
                    {' · '}{record.canonical_record.record_type}
                    {' · '}{record.canonical_record.quality_status}
                  </strong>
                  {record.canonical_record.payload.measurement_basis === 'model_derived' && (
                    <div className="explain">Model-derived current estimate; not a direct local station measurement.</div>
                  )}
                  <div className="explain">{canonicalTimeSummary(record.canonical_record.timestamps)}</div>
                  {record.canonical_record.validation_errors.map((finding, index) => (
                    <div className="explain" key={`${record.record_id}-canonical-finding-${index}`}>{finding}</div>
                  ))}
                  {record.canonical_record.payload.measurements?.map(measurement => (
                    <div className="kv" key={measurement.name}>
                      <span>{measurement.name} · source</span>
                      <span>
                        {measurement.source_value === null || measurement.source_value === undefined
                          ? 'Unavailable'
                          : `${measurement.source_value}${measurement.source_unit ? ` ${measurement.source_unit}` : ''}`}
                        {' → '}
                        {measurement.normalized_value === null || measurement.normalized_value === undefined
                          ? 'Normalized value unavailable'
                          : `${measurement.normalized_value}${measurement.normalized_unit ? ` ${measurement.normalized_unit}` : ''}`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {Object.entries(record.values).map(([name, value]) => (
                <div className="kv" key={name}>
                  <span>{name}</span>
                  <span>{value === null || value === undefined ? 'Unavailable' : `${value}${record.units[name] ? ` ${record.units[name]}` : ''}`}</span>
                </div>
              ))}
            </div>
          ))}
          {data.pagination && (
            <p className="explain">
              Query page at offset {data.pagination.offset} returned {data.pagination.returned_records} record(s);
              {` ${data.records.length} record(s) loaded across displayed pages.`}
              {data.has_more ? ' More stored records are available.' : ' No further stored records are indicated by this query.'}
            </p>
          )}
          {data.records.length === 0 && (
            <p className="explain">No stored records were returned on this page. This does not establish provider-wide availability or the absence of a hazard.</p>
          )}
          {data.has_more && nextOffset === null && (
            <p className="explain">The API offset limit has been reached. Additional stored records may exist but cannot be requested with the current bounded pagination contract.</p>
          )}
          {nextOffset !== null && (
            <button type="button" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? 'Loading more records…' : 'Load more stored records'}
            </button>
          )}
          <p className="explain">
            Application reports are withheld because ownership and visibility are not modeled. Weather, hydrology, event, satellite, and GIS data are distinct; a missing source is not inferred from another category.
          </p>
        </>
      )}
      {!location && <p className="explain">Select a location to query nearby stored observations.</p>}
    </section>
  )
}
