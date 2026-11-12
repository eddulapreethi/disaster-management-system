import { apiGet, apiPatch, apiPost } from './api.js'

export const INCIDENT_HAZARDS = [
  'flood',
  'cyclone',
  'storm',
  'wildfire',
  'heatwave',
  'drought',
  'earthquake',
  'landslide',
  'other',
]
export const INCIDENT_STATUSES = ['pending', 'verified', 'rejected', 'needs_review']

export function buildIncidentQuery(filters = {}, { limit = 100, offset = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  if (filters.hazard_category) params.set('hazard_category', filters.hazard_category)
  if (filters.verification_status) params.set('verification_status', filters.verification_status)
  if (filters.start_date) params.set('start_time', `${filters.start_date}T00:00:00Z`)
  if (filters.end_date) params.set('end_time', `${filters.end_date}T23:59:59.999Z`)
  return params.toString()
}

export function validateIncidentPage(page, expectedOffset) {
  if (!page || !Array.isArray(page.records) || !page.pagination) {
    throw new Error('Incident response is missing its records or pagination metadata.')
  }
  const { limit, offset, returned_records: returned, total_matching_records: total } = page.pagination
  if (
    !Number.isInteger(limit) || limit < 1
    || offset !== expectedOffset
    || returned !== page.records.length
    || !Number.isInteger(total) || total < returned
    || typeof page.has_more !== 'boolean'
    || page.has_more !== (offset + returned < total)
  ) {
    throw new Error('Incident response contains inconsistent pagination metadata.')
  }
  for (const incident of page.records) {
    if (
      !Number.isInteger(incident.id)
      || !INCIDENT_HAZARDS.includes(incident.hazard_category)
      || !INCIDENT_STATUSES.includes(incident.status)
      || !Number.isFinite(incident.latitude) || incident.latitude < -90 || incident.latitude > 90
      || !Number.isFinite(incident.longitude) || incident.longitude < -180 || incident.longitude > 180
      || 'reporter_id' in incident
      || 'evidence_metadata' in incident
      || 'review_history' in incident
    ) {
      throw new Error('Incident response contains invalid or private map data.')
    }
  }
  return page
}

export function getIncidentNextOffset(page) {
  if (!page?.has_more) return null
  const next = page.pagination.offset + page.pagination.returned_records
  return next < 0 || next > 10000 ? null : next
}

export function mergeIncidentPages(first, next) {
  if (next.pagination.offset !== first.pagination.offset + first.pagination.returned_records) {
    throw new Error('Incident pages are not consecutive.')
  }
  const ids = new Set(first.records.map(record => record.id))
  if (next.records.some(record => ids.has(record.id))) {
    throw new Error('Incident page contains duplicate records.')
  }
  return {
    ...next,
    records: [...first.records, ...next.records],
    pagination: {
      ...next.pagination,
      offset: 0,
      returned_records: first.records.length + next.records.length,
    },
  }
}

export async function fetchIncidents(filters, pagination) {
  const offset = pagination?.offset ?? 0
  const params = buildIncidentQuery(filters, pagination)
  return validateIncidentPage(await apiGet(`/incidents?${params}`), offset)
}

export function fetchIncidentAnalytics(filters = {}) {
  const params = new URLSearchParams()
  if (filters.hazard_category) params.set('hazard_category', filters.hazard_category)
  if (filters.start_date) params.set('start_time', `${filters.start_date}T00:00:00Z`)
  if (filters.end_date) params.set('end_time', `${filters.end_date}T23:59:59.999Z`)
  const query = params.toString()
  return apiGet(`/incidents/analytics${query ? `?${query}` : ''}`)
}

export function fetchIncident(id) {
  return apiGet(`/incidents/${id}`)
}

export function submitIncident(data) {
  return apiPost('/incidents', data)
}

export function updateIncident(id, changes) {
  return apiPatch(`/incidents/${id}`, changes)
}

export function reviewIncident(id, decision) {
  return apiPost(`/incidents/${id}/reviews`, decision)
}
