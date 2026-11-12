import { apiGet } from './api.js'

const MAX_LIMIT = 500
const MAX_LONGITUDE_SPAN = 30
const MAX_LATITUDE_SPAN = 20

export class EarthquakeQueryValidationError extends Error {
  constructor(message) {
    super(message)
    this.name = 'EarthquakeQueryValidationError'
  }
}

function isFiniteCoordinate(value, minimum, maximum) {
  return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
}

function validDate(value) {
  if (typeof value !== 'string' || !value.trim()) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

function optionalFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function optionalString(value) {
  return typeof value === 'string' && value.trim() ? value : null
}

function safeSourceUrl(value) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && url.hostname === 'earthquake.usgs.gov'
      ? url.toString()
      : null
  } catch {
    return null
  }
}

export function normalizeEarthquakeResponse(response) {
  if (
    !response
    || response.provider !== 'USGS ComCat'
    || !['AVAILABLE', 'NO_MATCHING_EVENTS'].includes(response.data_status)
    || !Array.isArray(response.records)
    || !Number.isInteger(response.returned_events)
    || response.returned_events !== response.records.length
  ) {
    throw new Error('The earthquake event response was incomplete or inconsistent.')
  }

  const retrievedAt = validDate(response.retrieved_at)
  if (!retrievedAt) throw new Error('The earthquake event response did not include a valid retrieval time.')
  if (
    response.freshness_status !== 'NOT_ASSESSED'
    || !['UNKNOWN', 'VERIFIED', 'UNVERIFIED', 'RESTRICTED'].includes(response.license_usage_status)
  ) {
    throw new Error('The earthquake event response contained invalid source-status metadata.')
  }

  const events = response.records.map(record => {
    const coordinates = record?.geography?.source_coordinates
    const eventAttributes = record?.payload?.event_attributes
    const sourceId = record?.source?.source_record_id
    const eventTime = validDate(record?.timestamps?.event_time_utc)

    if (
      record?.contract_version !== '1.0'
      || record?.record_type !== 'historical_event'
      || record?.hazard_type !== 'earthquake'
      || record?.source?.provider !== 'USGS ComCat'
      || (typeof sourceId !== 'string' && !Number.isInteger(sourceId))
      || !eventTime
      || !isFiniteCoordinate(coordinates?.latitude, -90, 90)
      || !isFiniteCoordinate(coordinates?.longitude, -180, 180)
      || !eventAttributes
      || typeof eventAttributes !== 'object'
      || Array.isArray(eventAttributes)
    ) {
      throw new Error('The earthquake event response contained an invalid event record.')
    }

    const magnitude = optionalFiniteNumber(eventAttributes.magnitude)
    const depthKm = optionalFiniteNumber(eventAttributes.depth_km)
    const sourceUpdatedAt = validDate(eventAttributes.source_updated_at_utc)
      || validDate(record.source.source_metadata?.source_updated_at_utc)
    const retrievalTime = validDate(record.timestamps.retrieval_time_utc) || retrievedAt

    return {
      id: String(sourceId),
      title: optionalString(record.payload.event_name),
      place: optionalString(record.payload.event_description),
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      eventTime,
      retrievalTime,
      sourceUpdatedAt,
      magnitude,
      magnitudeType: optionalString(eventAttributes.magnitude_type),
      depthKm,
      reviewStatus: optionalString(eventAttributes.review_status),
      network: optionalString(eventAttributes.network),
      sourceCode: optionalString(eventAttributes.source_code),
      sourceUrl: safeSourceUrl(record.source.source_url),
      attribution: optionalString(record.source.attribution) || response.attribution,
      licenseUsageStatus: response.license_usage_status,
      licenseUsageDetails: optionalString(response.license_usage_details),
      sourceMetadata: record.source.source_metadata && typeof record.source.source_metadata === 'object'
        ? record.source.source_metadata
        : {},
    }
  })

  if (response.data_status === 'NO_MATCHING_EVENTS' && events.length !== 0) {
    throw new Error('The earthquake event response had inconsistent empty-result metadata.')
  }
  if (response.data_status === 'AVAILABLE' && events.length === 0) {
    throw new Error('The earthquake event response had inconsistent availability metadata.')
  }

  return {
    provider: response.provider,
    attribution: response.attribution,
    retrievedAt,
    freshnessStatus: response.freshness_status,
    dataStatus: response.data_status,
    events,
  }
}

export function buildEarthquakeEventQuery({
  west,
  south,
  east,
  north,
  startDate,
  endDate,
  minMagnitude,
  maxMagnitude,
  reviewStatus,
  limit = 100,
}) {
  const values = [west, south, east, north]
  if (
    values.some(value => typeof value !== 'number' || !Number.isFinite(value))
    || !isFiniteCoordinate(west, -180, 180)
    || !isFiniteCoordinate(east, -180, 180)
    || !isFiniteCoordinate(south, -90, 90)
    || !isFiniteCoordinate(north, -90, 90)
  ) {
    throw new EarthquakeQueryValidationError('Choose a valid map area before querying earthquake events.')
  }

  const longitudeSpan = east >= west ? east - west : east + 360 - west
  const latitudeSpan = north - south
  if (
    longitudeSpan <= 0
    || longitudeSpan > MAX_LONGITUDE_SPAN
    || latitudeSpan <= 0
    || latitudeSpan > MAX_LATITUDE_SPAN
  ) {
    throw new EarthquakeQueryValidationError('Zoom to a map area no wider than 30° longitude by 20° latitude before querying.')
  }

  if (!Number.isInteger(limit) || limit < 1 || limit > MAX_LIMIT) {
    throw new EarthquakeQueryValidationError(`Result limit must be between 1 and ${MAX_LIMIT}.`)
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate || '') || !/^\d{4}-\d{2}-\d{2}$/.test(endDate || '')) {
    throw new EarthquakeQueryValidationError('Choose both a start date and an end date.')
  }
  if (startDate > endDate) throw new EarthquakeQueryValidationError('Start date must not be after end date.')
  const daySpan = (Date.parse(`${endDate}T00:00:00Z`) - Date.parse(`${startDate}T00:00:00Z`)) / 86400000
  if (!Number.isFinite(daySpan) || daySpan > 30) {
    throw new EarthquakeQueryValidationError('Choose a date range of 30 days or less.')
  }
  const todayUtc = new Date().toISOString().slice(0, 10)
  if (endDate > todayUtc) {
    throw new EarthquakeQueryValidationError('End date must not be in the future (UTC).')
  }
  const requestedEndTime = Date.parse(`${endDate}T23:59:59.999Z`)
  const endTime = new Date(Math.min(requestedEndTime, Date.now())).toISOString()

  const params = new URLSearchParams({
    west: String(west),
    south: String(south),
    east: String(east),
    north: String(north),
    start_time: `${startDate}T00:00:00Z`,
    end_time: endTime,
    limit: String(limit),
  })
  if (minMagnitude !== '' && minMagnitude != null) {
    const value = Number(minMagnitude)
    if (!Number.isFinite(value) || value < -10 || value > 10) {
      throw new EarthquakeQueryValidationError('Minimum magnitude must be between -10 and 10.')
    }
    params.set('min_magnitude', String(value))
  }
  if (maxMagnitude !== '' && maxMagnitude != null) {
    const value = Number(maxMagnitude)
    if (!Number.isFinite(value) || value < -10 || value > 10) {
      throw new EarthquakeQueryValidationError('Maximum magnitude must be between -10 and 10.')
    }
    params.set('max_magnitude', String(value))
  }
  if (
    minMagnitude !== '' && minMagnitude != null
    && maxMagnitude !== '' && maxMagnitude != null
    && Number(minMagnitude) > Number(maxMagnitude)
  ) {
    throw new EarthquakeQueryValidationError('Minimum magnitude must not exceed maximum magnitude.')
  }
  if (reviewStatus) {
    if (!['automatic', 'reviewed'].includes(reviewStatus)) {
      throw new EarthquakeQueryValidationError('Choose a valid provider review status.')
    }
    params.set('review_status', reviewStatus)
  }
  return params.toString()
}

export async function fetchEarthquakeEvents(filters, bbox, options) {
  const query = buildEarthquakeEventQuery({ ...filters, ...bbox })
  const response = await apiGet(`/earthquake-events?${query}`, options)
  return normalizeEarthquakeResponse(response)
}

export function createRequestSequence() {
  let latest = 0
  return {
    next() {
      latest += 1
      return latest
    },
    isCurrent(requestId) {
      return requestId === latest
    },
  }
}

export function magnitudeMarkerRadius(magnitude) {
  if (typeof magnitude !== 'number' || !Number.isFinite(magnitude)) return 6
  return Math.max(5, Math.min(13, 6 + magnitude * 0.8))
}

export function getEarthquakeRequestError(error) {
  if (error instanceof EarthquakeQueryValidationError) return error.message
  if (error?.status === 401 || error?.status === 403) {
    return 'Your session is not authorized to query earthquake events. Sign in again if needed.'
  }
  if (error?.status === 422) return 'The selected area or filters are outside the supported query limits.'
  if (error?.status === 502 || error?.status === 503 || error?.status === 504) {
    return 'The USGS earthquake event service is currently unavailable. Try again later.'
  }
  return 'Earthquake events could not be loaded. Check your connection and try again.'
}
