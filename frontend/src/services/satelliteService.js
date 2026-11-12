import { apiGetBlob } from './api.js'
import { apiGet } from './api.js'
import { normalizeLocation } from './location.js'

export function createSatelliteRequestSequence() {
  let latestRequest = 0
  return {
    next() {
      latestRequest += 1
      return latestRequest
    },
    isCurrent(requestId) {
      return requestId === latestRequest
    },
    invalidate() {
      latestRequest += 1
    },
  }
}

function decodeMetadata(headerValue) {
  if (!headerValue) {
    throw new Error('Satellite response did not include exposed scene metadata.')
  }
  try {
    const metadata = JSON.parse(decodeURIComponent(headerValue))
    if (
      typeof metadata !== 'object'
      || metadata === null
      || typeof metadata.acquisition_time !== 'string'
      || typeof metadata.process_requested_at !== 'string'
      || typeof metadata.downloaded_at !== 'string'
      || metadata.catalog_search_status !== 'COMPLETED'
      || metadata.catalog_results_status !== 'RESULTS_FOUND'
      || metadata.imagery_status !== 'RETRIEVED'
      || !Array.isArray(metadata.requested_bbox)
      || !Number.isInteger(metadata.width)
      || !Number.isInteger(metadata.height)
    ) {
      throw new Error('missing required provenance fields')
    }
    if (
      metadata.canonical_record !== undefined
      && (
        metadata.canonical_record?.contract_version !== '1.0'
        || metadata.canonical_record?.record_type !== 'satellite_acquisition'
        || metadata.canonical_record?.payload?.kind !== 'satellite_acquisition'
      )
    ) {
      throw new Error('invalid canonical record')
    }
    return metadata
  } catch {
    throw new Error('Satellite response metadata was invalid or incomplete.')
  }
}

function validDate(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value
}

function validateDateRange(startDate, endDate) {
  if (!validDate(startDate) || !validDate(endDate)) {
    throw new Error('Choose a valid start and end date for the scene search.')
  }
  if (startDate > endDate) {
    throw new Error('Start date must be on or before end date.')
  }
}

function locationQuery(location, startDate, endDate) {
  const selectedLocation = normalizeLocation(location)
  validateDateRange(startDate, endDate)
  return new URLSearchParams({
    latitude: String(selectedLocation.latitude),
    longitude: String(selectedLocation.longitude),
    start_date: startDate,
    end_date: endDate,
  })
}

export async function fetchSatelliteStatus() {
  const status = await apiGet('/satellite/status')
  if (
    status?.authentication_status !== 'AUTHENTICATED'
    || status.catalog_search_status !== 'NOT_CHECKED'
    || status.catalog_results_status !== 'NOT_CHECKED'
    || status.imagery_status !== 'NOT_CHECKED'
  ) {
    throw new Error('Copernicus status response did not distinguish authentication from Catalog and imagery checks.')
  }
  return status
}

export async function searchSentinel2Catalog(location, { startDate, endDate } = {}) {
  const query = locationQuery(location, startDate, endDate)
  const result = await apiGet(`/satellite/search/sentinel-2?${query}`)
  if (
    !Array.isArray(result?.features)
    || result.catalog_search_status !== 'COMPLETED'
    || !['RESULTS_FOUND', 'NO_RESULTS'].includes(result.catalog_results_status)
    || result.imagery_status !== 'NOT_REQUESTED'
  ) {
    throw new Error('Sentinel-2 Catalog response did not identify search and imagery status separately.')
  }
  return result
}

export async function fetchSentinel2Scene(location, {
  startDate,
  endDate,
  width = 128,
  height = 128,
  timeoutMs = 120_000,
} = {}) {
  const selectedLocation = normalizeLocation(location)
  validateDateRange(startDate, endDate)
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 1024 || height > 1024) {
    throw new Error('Image dimensions must be between 1 and 1024 pixels.')
  }

  const query = locationQuery(selectedLocation, startDate, endDate)
  query.set('width', String(width))
  query.set('height', String(height))
  const response = await apiGetBlob(`/satellite/scene/sentinel-2?${query}`, { timeoutMs })
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.toLowerCase().startsWith('image/tiff')) {
    throw new Error('Satellite service returned an unsupported image format.')
  }
  const metadata = decodeMetadata(response.headers.get('x-satellite-metadata'))
  return { blob: response.blob, metadata }
}
