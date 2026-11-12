import { apiGet } from './api.js'
import { normalizeLocation } from './location.js'

const SOURCE_STATUSES = new Set([
  'AVAILABLE',
  'PARTIAL',
  'STALE',
  'ERROR',
  'UNVERIFIED',
  'NO_MATCHING_STORED_RECORDS',
  'NOT_PERSISTED',
  'REGIONAL',
])

const CANONICAL_RECORD_TYPES = new Set([
  'observation',
  'forecast',
  'warning',
  'historical_event',
  'satellite_acquisition',
  'gis_reference',
])

export function environmentalSourceStatusPresentation(status) {
  if (status === 'AVAILABLE') return { label: 'AVAILABLE', tone: 'low' }
  if (status === 'STALE' || status === 'PARTIAL') return { label: status, tone: 'med' }
  if (status === 'ERROR') return { label: 'ERROR', tone: 'high' }
  if (status === 'NO_MATCHING_STORED_RECORDS') {
    return { label: 'NO MATCHING STORED RECORDS', tone: '' }
  }
  return { label: status, tone: '' }
}

export function validateEnvironmentalDataPage(data, expectedOffset) {
  if (
    !data
    || !Array.isArray(data.records)
    || !Array.isArray(data.sources)
    || typeof data.has_more !== 'boolean'
    || !data.pagination
    || !Number.isInteger(data.pagination.limit)
    || data.pagination.limit < 1
    || data.pagination.limit > 1000
    || data.pagination.offset !== expectedOffset
    || !Number.isInteger(data.pagination.returned_records)
    || data.pagination.returned_records !== data.records.length
    || data.pagination.returned_records > data.pagination.limit
    || data.pagination.count_scope !== 'RETURNED_PAGE'
    || (data.has_more && data.records.length === 0)
  ) {
    throw new Error('Stored-data response had missing or inconsistent pagination metadata.')
  }

  const recordCounts = new Map()
  const recordIds = new Set()
  for (const record of data.records) {
    if (!record || typeof record.category !== 'string' || !Number.isInteger(record.record_id)) {
      throw new Error('Stored-data response contained an invalid record identity.')
    }
    if (record.canonical_record !== undefined && record.canonical_record !== null) {
      const canonical = record.canonical_record
      if (
        canonical.contract_version !== '1.0'
        || !CANONICAL_RECORD_TYPES.has(canonical.record_type)
        || typeof canonical.source?.provider !== 'string'
        || typeof canonical.payload?.kind !== 'string'
        || canonical.payload.kind !== canonical.record_type
        || !canonical.geography
        || !canonical.timestamps
        || !Array.isArray(canonical.validation_errors)
      ) {
        throw new Error('Stored-data response contained an invalid canonical record.')
      }
      if (
        Array.isArray(canonical.payload.measurements)
        && canonical.payload.measurements.some(measurement => (
          !measurement
          || typeof measurement.name !== 'string'
          || (
            measurement.normalized_value !== null
            && measurement.normalized_value !== undefined
            && (typeof measurement.normalized_value !== 'number' || !Number.isFinite(measurement.normalized_value))
          )
        ))
      ) {
        throw new Error('Stored-data response contained an invalid canonical measurement.')
      }
    }
    const identity = `${record.category}-${record.record_id}`
    if (recordIds.has(identity)) {
      throw new Error('Stored-data response contained a duplicate record identity.')
    }
    recordIds.add(identity)
    recordCounts.set(record.category, (recordCounts.get(record.category) || 0) + 1)
  }

  const sourceCategories = new Set()
  for (const source of data.sources) {
    if (
      !source
      || typeof source.category !== 'string'
      || sourceCategories.has(source.category)
      || !SOURCE_STATUSES.has(source.status)
      || !Number.isInteger(source.matching_records)
      || source.matching_records < 0
      || source.count_scope !== 'RETURNED_PAGE'
      || source.matching_records !== (recordCounts.get(source.category) || 0)
      || (source.status === 'NO_MATCHING_STORED_RECORDS' && source.matching_records !== 0)
    ) {
      throw new Error('Stored-data response contained inconsistent page-scoped source counts or status.')
    }
    sourceCategories.add(source.category)
  }
  if ([...recordCounts.keys()].some(category => !sourceCategories.has(category))) {
    throw new Error('Stored-data response omitted a source count for a returned record category.')
  }
  return data
}

export function mergeEnvironmentalDataPages(current, next) {
  const existingIds = new Set(current.records.map(record => `${record.category}-${record.record_id}`))
  if (next.records.some(record => existingIds.has(`${record.category}-${record.record_id}`))) {
    throw new Error('Stored-data pagination returned a duplicate record; the next page was not added.')
  }
  return { ...next, records: [...current.records, ...next.records] }
}

export function getEnvironmentalDataNextOffset(data) {
  if (!data?.has_more || !data.pagination) return null
  const nextOffset = data.pagination.offset + data.pagination.returned_records
  return nextOffset <= 10000 ? nextOffset : null
}

export async function fetchEnvironmentalData(location, { offset = 0, ...options } = {}) {
  const selectedLocation = normalizeLocation(location)
  const query = new URLSearchParams({
    latitude: String(selectedLocation.latitude),
    longitude: String(selectedLocation.longitude),
    radius_km: '25',
    limit: '100',
    offset: String(offset),
  })
  const result = await apiGet(`/environmental-data?${query}`, options)
  return validateEnvironmentalDataPage(result, offset)
}

export function createEnvironmentalDataRequestSequence() {
  let sequence = 0
  return {
    next() {
      sequence += 1
      return sequence
    },
    isCurrent(requestId) {
      return sequence === requestId
    },
    invalidate(requestId) {
      if (sequence === requestId) sequence += 1
    },
  }
}
