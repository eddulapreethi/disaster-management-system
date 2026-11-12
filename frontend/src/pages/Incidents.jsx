import { useEffect, useMemo, useState } from 'react'
import IncidentMap from '../maps/IncidentMap'
import LocationSearchField from '../components/LocationSearchField'
import { getCurrentUser } from '../services/authService'
import { useSelectedLocation } from '../services/LocationContext'
import {
  INCIDENT_HAZARDS,
  INCIDENT_STATUSES,
  fetchIncident,
  fetchIncidentAnalytics,
  fetchIncidents,
  getIncidentNextOffset,
  mergeIncidentPages,
  reviewIncident,
  submitIncident,
  updateIncident,
} from '../services/incidentService'

const LOCAL_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'

function localDateTimeValue() {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}

function IncidentComposer({ selectedLocation, setSelectedLocation, onSubmitted }) {
  const [title, setTitle] = useState('')
  const [hazard, setHazard] = useState('flood')
  const [description, setDescription] = useState('')
  const [latitude, setLatitude] = useState(selectedLocation?.latitude ?? '')
  const [longitude, setLongitude] = useState(selectedLocation?.longitude ?? '')
  const [incidentTime, setIncidentTime] = useState(localDateTimeValue)
  const [timezone, setTimezone] = useState(LOCAL_TIME_ZONE)
  const [fileName, setFileName] = useState('')
  const [mediaType, setMediaType] = useState('')
  const [sizeBytes, setSizeBytes] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (selectedLocation) {
      setLatitude(selectedLocation.latitude)
      setLongitude(selectedLocation.longitude)
    }
  }, [selectedLocation?.latitude, selectedLocation?.longitude])

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    const hasEvidence = Boolean(fileName || mediaType || sizeBytes)
    if (hasEvidence && (!fileName || !mediaType || sizeBytes === '')) {
      setError('Provide the evidence file name, media type, and size together, or leave all three blank.')
      return
    }
    setSaving(true)
    const evidence = hasEvidence
      ? [{
          file_name: fileName,
          media_type: mediaType,
          size_bytes: Number(sizeBytes),
        }]
      : []
    try {
      await submitIncident({
        title,
        hazard_category: hazard,
        description,
        latitude: Number(latitude),
        longitude: Number(longitude),
        incident_time: incidentTime,
        incident_timezone: timezone,
        evidence_metadata: evidence,
      })
      setTitle('')
      setDescription('')
      setFileName('')
      setMediaType('')
      setSizeBytes('')
      onSubmitted()
    } catch (requestError) {
      setError(requestError.message || 'The incident report could not be submitted.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="card incident-form" onSubmit={handleSubmit}>
      <h3 className="sectitle">Submit a community incident report</h3>
      <p className="explain">
        Reports begin as pending and are not official observations or emergency warnings. Your title, description,
        hazard, time, and coordinates are visible to signed-in users; do not include personal or contact details.
        Evidence is metadata only—this form does not upload files.
      </p>
      <label>Short title</label>
      <input className="text-input" minLength={3} maxLength={160} required value={title} onChange={event => setTitle(event.target.value)} />
      <label>Hazard category</label>
      <select className="text-input" value={hazard} onChange={event => setHazard(event.target.value)}>
        {INCIDENT_HAZARDS.map(item => <option key={item} value={item}>{item}</option>)}
      </select>
      <label>Description (10–4000 characters)</label>
      <textarea className="text-input" minLength={10} maxLength={4000} required rows={4} value={description} onChange={event => setDescription(event.target.value)} />
      <LocationSearchField
        value={selectedLocation}
        onChange={location => {
          setSelectedLocation(location)
          setLatitude(location.latitude)
          setLongitude(location.longitude)
        }}
        label="Search for a place (optional)"
      />
      <div className="incident-coordinate-grid">
        <div><label>Latitude · WGS 84</label><input className="text-input" type="number" step="any" min="-90" max="90" required value={latitude} onChange={event => setLatitude(event.target.value)} /></div>
        <div><label>Longitude · WGS 84</label><input className="text-input" type="number" step="any" min="-180" max="180" required value={longitude} onChange={event => setLongitude(event.target.value)} /></div>
      </div>
      <label>Incident date and time (local)</label>
      <input className="text-input" type="datetime-local" required value={incidentTime} onChange={event => setIncidentTime(event.target.value)} />
      <label>Incident timezone (IANA)</label>
      <input className="text-input" required value={timezone} onChange={event => setTimezone(event.target.value)} placeholder="e.g. Europe/London" />
      <fieldset className="incident-evidence">
        <legend>Optional evidence metadata (no file upload)</legend>
        <div className="incident-coordinate-grid">
          <div><label>File name</label><input className="text-input" maxLength={180} value={fileName} onChange={event => setFileName(event.target.value)} /></div>
          <div><label>Media type</label><input className="text-input" maxLength={100} value={mediaType} onChange={event => setMediaType(event.target.value)} placeholder="image/jpeg" /></div>
        </div>
        <label>File size in bytes</label>
        <input className="text-input" type="number" min="0" max="25000000" value={sizeBytes} onChange={event => setSizeBytes(event.target.value)} />
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <button className="btn" type="submit" disabled={saving}>{saving ? 'Submitting…' : 'Submit report for review'}</button>
    </form>
  )
}

function IncidentCard({ incident, onUpdated }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(incident.title)
  const [description, setDescription] = useState(incident.description)
  const [reviewNote, setReviewNote] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [detail, setDetail] = useState(null)

  async function toggleDetails() {
    if (detail) {
      setDetail(null)
      return
    }
    setBusy(true)
    setError('')
    try {
      setDetail(await fetchIncident(incident.id))
    } catch (requestError) {
      setError(requestError.message || 'Private report details could not be loaded.')
    } finally {
      setBusy(false)
    }
  }
  async function saveEdit(event) {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await updateIncident(incident.id, { title, description })
      setEditing(false)
      onUpdated()
    } catch (requestError) {
      setError(requestError.message || 'Report changes could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  async function submitReview(status) {
    setBusy(true)
    setError('')
    try {
      const updated = await reviewIncident(incident.id, { status, note: reviewNote || undefined })
      setDetail(updated)
      setReviewNote('')
      onUpdated()
    } catch (requestError) {
      setError(requestError.message || 'The review decision could not be saved.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="card incident-card">
      <div className="incident-card-heading">
        <strong>{incident.title}</strong>
        <span className={`pill ${incident.status === 'verified' ? 'low' : incident.status === 'rejected' ? 'high' : 'med'}`}>
          {incident.status.replace('_', ' ')}
        </span>
      </div>
      <div className="incident-meta">{incident.hazard_category} · {incident.incident_time} ({incident.incident_timezone})</div>
      <div className="incident-meta">WGS 84: {incident.latitude}, {incident.longitude} · submitted {incident.submitted_at}</div>
      {editing ? (
        <form onSubmit={saveEdit}>
          <label>Title</label>
          <input className="text-input" minLength={3} maxLength={160} required value={title} onChange={event => setTitle(event.target.value)} />
          <label>Description</label>
          <textarea className="text-input" minLength={10} maxLength={4000} required rows={3} value={description} onChange={event => setDescription(event.target.value)} />
          <button className="btn" type="submit" disabled={busy}>Save changes</button>
          <button className="btn-outline" type="button" onClick={() => setEditing(false)}>Cancel</button>
        </form>
      ) : <p className="incident-description">{incident.description}</p>}
      {incident.can_edit && !editing && <button className="btn-outline" type="button" onClick={() => setEditing(true)}>Edit pending report</button>}
      {incident.can_view_private && (
        <button className="btn-outline" type="button" onClick={toggleDetails} disabled={busy}>
          {detail ? 'Hide private details' : 'View private evidence and review history'}
        </button>
      )}
      {detail && (
        <div className="incident-review">
          <strong>Evidence metadata (no uploaded files)</strong>
          {detail.evidence_metadata.length === 0
            ? <p className="incident-meta">No evidence metadata supplied.</p>
            : detail.evidence_metadata.map((item, index) => (
              <p className="incident-meta" key={`${item.file_name}-${index}`}>
                {item.file_name} · {item.media_type} · {item.size_bytes} bytes
              </p>
            ))}
          <strong>Review history</strong>
          {detail.review_history.length === 0
            ? <p className="incident-meta">No review decision has been recorded.</p>
            : detail.review_history.map((review, index) => (
              <p className="incident-meta" key={`${review.reviewer_id}-${review.created_at}-${index}`}>
                {review.reviewer_name} · {review.previous_status} → {review.new_status} · {review.created_at}
                {review.note ? ` · ${review.note}` : ''}
              </p>
            ))}
        </div>
      )}
      {incident.can_review && (
        <div className="incident-review">
          <label>Reviewer note (required for rejection or needs review)</label>
          <textarea className="text-input" maxLength={1000} rows={2} value={reviewNote} onChange={event => setReviewNote(event.target.value)} />
          <div className="incident-review-actions">
            <button type="button" className="btn" disabled={busy} onClick={() => submitReview('verified')}>Mark verified</button>
            <button type="button" className="btn-outline" disabled={busy} onClick={() => submitReview('needs_review')}>Needs review</button>
            <button type="button" className="btn-outline" disabled={busy} onClick={() => submitReview('rejected')}>Reject report</button>
          </div>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </article>
  )
}

export default function Incidents() {
  const { selectedLocation, setSelectedLocation } = useSelectedLocation()
  const [filters, setFilters] = useState({ hazard_category: '', verification_status: '', start_date: '', end_date: '' })
  const [page, setPage] = useState(null)
  const [analytics, setAnalytics] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const isReviewer = getCurrentUser()?.role === 'reviewer'

  const analyticsFilters = useMemo(() => ({
    hazard_category: filters.hazard_category,
    start_date: filters.start_date,
    end_date: filters.end_date,
  }), [filters.hazard_category, filters.start_date, filters.end_date])

  useEffect(() => {
    let active = true
    setLoading(true)
    setError('')
    Promise.all([
      fetchIncidents(filters, { limit: 100, offset: 0 }),
      fetchIncidentAnalytics(analyticsFilters),
    ]).then(([incidentPage, summary]) => {
      if (!active) return
      setPage(incidentPage)
      setAnalytics(summary)
      setSelectedId(incidentPage.records[0]?.id ?? null)
    }).catch(requestError => {
      if (active) setError(requestError.message || 'Incident reports could not be loaded.')
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [filters, analyticsFilters, refresh])

  const records = page?.records || []
  const nextOffset = getIncidentNextOffset(page)

  async function loadMore() {
    if (nextOffset === null || loadingMore) return
    setLoadingMore(true)
    setError('')
    try {
      const next = await fetchIncidents(filters, { limit: 100, offset: nextOffset })
      setPage(current => mergeIncidentPages(current, next))
    } catch (requestError) {
      setError(requestError.message || 'More reports could not be loaded.')
    } finally {
      setLoadingMore(false)
    }
  }

  function updateFilter(key, value) {
    setFilters(current => ({ ...current, [key]: value }))
  }

  return (
    <div>
      <h2 className="title">Community incident reporting</h2>
      <p className="sub">
        A user-submitted situational-awareness feed for global WGS 84 locations. Reports are not official observations,
        emergency warnings, or proof of conditions beyond the report. Data coverage is incomplete; an empty result does
        not mean no disaster exists. This view contains incident reports only—not weather, satellite, historical-event,
        forecast, or prediction layers.
      </p>
      <IncidentComposer
        selectedLocation={selectedLocation}
        setSelectedLocation={setSelectedLocation}
        onSubmitted={() => setRefresh(value => value + 1)}
      />
      <section className="card incident-analytics" aria-label="Descriptive incident report analytics">
        <div className="sectitle">Descriptive report counts</div>
        <p className="explain">{analytics?.disclaimer || 'Counts describe submitted reports, not hazard rates or forecasts.'}</p>
        {analytics && (
          <>
            <div className="incident-count-grid">
              <div><strong>{analytics.total_reports}</strong><span>matching reports</span></div>
              <div><strong>{analytics.records_without_verified_region}</strong><span>without verified country/region</span></div>
            </div>
            <div className="incident-count-list">
              {[...analytics.by_hazard.map(item => ({ ...item, group: 'Hazard' })),
                ...analytics.by_status.map(item => ({ ...item, group: 'Status' }))].map(item => (
                <span key={`${item.group}-${item.key}`}>{item.group}: {item.key} — {item.count}</span>
              ))}
            </div>
            <div className="incident-count-list" aria-label="Daily incident report counts in UTC">
              {analytics.by_day.map(item => <span key={item.date}>UTC {item.date} — {item.count} report(s)</span>)}
            </div>
          </>
        )}
      </section>
      <section className="card incident-filters" aria-label="Incident report filters">
        <div className="incident-coordinate-grid">
          <div><label>Hazard</label><select className="text-input" value={filters.hazard_category} onChange={event => updateFilter('hazard_category', event.target.value)}>
            <option value="">All hazards</option>{INCIDENT_HAZARDS.map(item => <option key={item} value={item}>{item}</option>)}
          </select></div>
          <div><label>Verification status</label><select className="text-input" value={filters.verification_status} onChange={event => updateFilter('verification_status', event.target.value)}>
            <option value="">All visible statuses</option>{INCIDENT_STATUSES.map(item => <option key={item} value={item}>{item.replace('_', ' ')}</option>)}
          </select></div>
          <div><label>From date (UTC)</label><input className="text-input" type="date" value={filters.start_date} onChange={event => updateFilter('start_date', event.target.value)} /></div>
          <div><label>To date (UTC)</label><input className="text-input" type="date" value={filters.end_date} onChange={event => updateFilter('end_date', event.target.value)} /></div>
        </div>
        <button className="btn-outline" type="button" onClick={() => setFilters({ hazard_category: '', verification_status: '', start_date: '', end_date: '' })}>Clear filters</button>
      </section>
      {loading && <div className="card" role="status">Loading incident reports…</div>}
      {error && <div className="card error" role="alert">{error}</div>}
      {!loading && !error && records.length === 0 && (
        <div className="card">No incident reports match these filters. This does not mean no disaster exists.</div>
      )}
      {!loading && !error && records.length > 0 && (
        <>
          <IncidentMap records={records} selectedId={selectedId} onSelect={setSelectedId} />
          <div className="incident-record-list">
            {records.map(incident => (
              <IncidentCard key={incident.id} incident={incident} onUpdated={() => setRefresh(value => value + 1)} />
            ))}
          </div>
          <p className="explain">
            Showing {page.pagination.returned_records} of {page.pagination.total_matching_records} matching reports.
            {page.has_more ? ' More reports are available.' : ''}
          </p>
          {nextOffset !== null && <button className="btn" type="button" onClick={loadMore} disabled={loadingMore}>{loadingMore ? 'Loading…' : 'Load more reports'}</button>}
        </>
      )}
      {isReviewer && <p className="explain">Reviewer actions are enabled for reports not submitted by your own account. Every decision is recorded with reviewer identity and time.</p>}
    </div>
  )
}
