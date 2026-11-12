import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildEarthquakeEventQuery,
  createRequestSequence,
  fetchEarthquakeEvents,
  getEarthquakeRequestError,
  magnitudeMarkerRadius,
  normalizeEarthquakeResponse,
} from '../src/services/earthquakeEventService.js'

const filters = {
  startDate: '2026-11-01',
  endDate: '2026-11-12',
  minMagnitude: '3.5',
  maxMagnitude: '7',
  reviewStatus: 'reviewed',
}
const bbox = { west: -15, south: 35, east: 15, north: 55 }

function canonicalEvent(overrides = {}) {
  return {
    contract_version: '1.0',
    record_type: 'historical_event',
    hazard_type: 'earthquake',
    source: {
      provider: 'USGS ComCat',
      source_record_id: 'us7000abcd',
      source_url: 'https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd',
      attribution: 'U.S. Geological Survey (USGS) ComCat',
      source_metadata: {
        net: 'us',
        code: '7000abcd',
        source_updated_at_utc: '2026-11-12T10:00:00Z',
      },
    },
    timestamps: {
      event_time_utc: '2026-11-11T09:30:00Z',
      retrieval_time_utc: '2026-11-12T12:00:00Z',
    },
    geography: {
      source_coordinates: { latitude: 45.25, longitude: 12.5 },
    },
    payload: {
      kind: 'historical_event',
      event_name: 'M 4.2 - test event',
      event_description: 'test region',
      event_attributes: {
        provider_event_id: 'us7000abcd',
        review_status: 'reviewed',
        network: 'us',
        source_code: '7000abcd',
        magnitude: 4.2,
        magnitude_type: 'mb',
        depth_km: 8.4,
        source_updated_at_utc: '2026-11-12T10:00:00Z',
      },
    },
    ...overrides,
  }
}

function response(records = [canonicalEvent()], overrides = {}) {
  return {
    provider: 'USGS ComCat',
    attribution: 'U.S. Geological Survey (USGS) ComCat',
    retrieved_at: '2026-11-12T12:00:00Z',
    freshness_status: 'NOT_ASSESSED',
    license_usage_status: 'UNKNOWN',
    license_usage_details: 'Contributor and product redistribution terms have not been verified.',
    data_status: records.length ? 'AVAILABLE' : 'NO_MATCHING_EVENTS',
    returned_events: records.length,
    records,
    ...overrides,
  }
}

test('normalizes canonical v1 event fields and preserves separate event, update and retrieval times', () => {
  const result = normalizeEarthquakeResponse(response())
  const [event] = result.events
  assert.equal(result.provider, 'USGS ComCat')
  assert.equal(event.id, 'us7000abcd')
  assert.equal(event.latitude, 45.25)
  assert.equal(event.longitude, 12.5)
  assert.equal(event.magnitude, 4.2)
  assert.equal(event.magnitudeType, 'mb')
  assert.equal(event.depthKm, 8.4)
  assert.equal(event.reviewStatus, 'reviewed')
  assert.equal(event.eventTime.toISOString(), '2026-11-11T09:30:00.000Z')
  assert.equal(event.sourceUpdatedAt.toISOString(), '2026-11-12T10:00:00.000Z')
  assert.equal(event.retrievalTime.toISOString(), '2026-11-12T12:00:00.000Z')
  assert.equal(event.sourceUrl, 'https://earthquake.usgs.gov/earthquakes/eventpage/us7000abcd')
})

test('empty result is distinct from malformed response and does not imply no earthquake occurred', () => {
  const result = normalizeEarthquakeResponse(response([], { data_status: 'NO_MATCHING_EVENTS' }))
  assert.equal(result.dataStatus, 'NO_MATCHING_EVENTS')
  assert.deepEqual(result.events, [])
  assert.throws(() => normalizeEarthquakeResponse(response([], { data_status: 'AVAILABLE' })), /inconsistent/)
  assert.throws(() => normalizeEarthquakeResponse({ provider: 'USGS ComCat' }), /incomplete or inconsistent/)
})

test('incomplete optional event values remain unavailable while invalid mandatory geometry is rejected', () => {
  const event = canonicalEvent()
  event.payload.event_attributes = {}
  event.timestamps.retrieval_time_utc = null
  event.source.source_url = 'javascript:alert(1)'
  const normalized = normalizeEarthquakeResponse(response([event])).events[0]
  assert.equal(normalized.magnitude, null)
  assert.equal(normalized.depthKm, null)
  assert.equal(normalized.reviewStatus, null)
  assert.equal(normalized.sourceUrl, null)
  assert.equal(normalized.retrievalTime.toISOString(), '2026-11-12T12:00:00.000Z')

  const invalid = canonicalEvent()
  invalid.geography.source_coordinates = { latitude: 91, longitude: 12 }
  assert.throws(() => normalizeEarthquakeResponse(response([invalid])), /invalid event record/)
})

test('builds exact bounded backend parameters for date, magnitude and review filters', () => {
  const query = new URLSearchParams(buildEarthquakeEventQuery({ ...filters, ...bbox }))
  assert.equal(query.get('west'), '-15')
  assert.equal(query.get('south'), '35')
  assert.equal(query.get('east'), '15')
  assert.equal(query.get('north'), '55')
  assert.equal(query.get('start_time'), '2026-11-01T00:00:00Z')
  assert.ok(Date.parse(query.get('end_time')) <= Date.now())
  assert.match(query.get('end_time'), /^2026-11-12T/)
  assert.equal(query.get('min_magnitude'), '3.5')
  assert.equal(query.get('max_magnitude'), '7')
  assert.equal(query.get('review_status'), 'reviewed')
  assert.equal(query.get('limit'), '100')
})

test('supports bounded antimeridian query bounds and rejects broad world requests', () => {
  const query = new URLSearchParams(buildEarthquakeEventQuery({
    ...filters,
    west: 170,
    south: -5,
    east: -175,
    north: 10,
  }))
  assert.equal(query.get('west'), '170')
  assert.equal(query.get('east'), '-175')
  assert.throws(
    () => buildEarthquakeEventQuery({ ...filters, west: -180, east: 180, south: -90, north: 90 }),
    /no wider than 30/,
  )
  assert.throws(
    () => buildEarthquakeEventQuery({ ...filters, ...bbox, startDate: '2026-10-01' }),
    /30 days or less/,
  )
  assert.throws(
    () => buildEarthquakeEventQuery({ ...filters, ...bbox, minMagnitude: '8', maxMagnitude: '4' }),
    /must not exceed/,
  )
})

test('authenticated API service sends only the bounded event path and normalizes results', async () => {
  const previousFetch = globalThis.fetch
  const previousLocalStorage = globalThis.localStorage
  const calls = []
  globalThis.localStorage = { getItem: () => 'test-token', removeItem: () => {} }
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options })
    return new Response(JSON.stringify(response()), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    const result = await fetchEarthquakeEvents(filters, bbox)
    assert.equal(result.events.length, 1)
    assert.match(calls[0].url, /\/api\/earthquake-events\?/)
    assert.equal(calls[0].options.headers.get('Authorization'), 'Bearer test-token')
    assert.match(calls[0].url, /review_status=reviewed/)
  } finally {
    globalThis.fetch = previousFetch
    globalThis.localStorage = previousLocalStorage
  }
})

test('maps unavailable and authorization responses to safe user-facing messages', () => {
  assert.match(getEarthquakeRequestError({ status: 401 }), /session is not authorized/)
  assert.match(getEarthquakeRequestError({ status: 403 }), /session is not authorized/)
  assert.match(getEarthquakeRequestError({ status: 503, message: 'raw provider detail' }), /currently unavailable/)
  assert.doesNotMatch(getEarthquakeRequestError({ status: 503, message: 'raw provider detail' }), /raw provider detail/)
  assert.match(getEarthquakeRequestError(new Error('Choose a date range of 30 days or less.')), /could not be loaded/)
})

test('authenticated API errors are sanitized before display', async () => {
  const previousFetch = globalThis.fetch
  const previousLocalStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'test-token', removeItem: () => {} }
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'upstream stack trace and URL' }), {
    status: 503,
    statusText: 'Service Unavailable',
    headers: { 'Content-Type': 'application/json' },
  })
  try {
    await assert.rejects(
      fetchEarthquakeEvents(filters, bbox).catch(error => {
        throw new Error(getEarthquakeRequestError(error))
      }),
      /currently unavailable/,
    )
  } finally {
    globalThis.fetch = previousFetch
    globalThis.localStorage = previousLocalStorage
  }
})

test('latest request sequencing prevents an older response from replacing newer filters', () => {
  const sequence = createRequestSequence()
  const olderRequest = sequence.next()
  const newerRequest = sequence.next()
  assert.equal(sequence.isCurrent(olderRequest), false)
  assert.equal(sequence.isCurrent(newerRequest), true)
})

test('magnitude marker radius is bounded and does not imply a damage score', () => {
  assert.equal(magnitudeMarkerRadius(null), 6)
  assert.ok(magnitudeMarkerRadius(9) > magnitudeMarkerRadius(2))
  assert.ok(magnitudeMarkerRadius(100) <= 13)
})

test('page remains separate from incident and risk map layers and uses selected global location', async () => {
  const { readFile } = await import('node:fs/promises')
  const [page, map, routes, sidebar, incidents] = await Promise.all([
    readFile(new URL('../src/pages/EarthquakeEvents.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/maps/EarthquakeEventMap.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/App.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/pages/Incidents.jsx', import.meta.url), 'utf8'),
  ])
  assert.match(page, /useSelectedLocation/)
  assert.match(page, /No matching records do not establish that no earthquake occurred/)
  assert.match(page, /Retrieved at:/)
  assert.match(page, /Retrieved at<\/span>/)
  assert.match(page, /isCurrent\(requestId\)/)
  assert.match(page, /Provider review status/)
  assert.match(page, /Open this event at USGS/)
  assert.match(map, /center=\{\[event\.latitude, event\.longitude\]\}/)
  assert.match(routes, /path="\/earthquake-events"/)
  assert.match(sidebar, /Earthquake events/)
  assert.match(incidents, /Community incident reporting/)
})
