import test from 'node:test'
import assert from 'node:assert/strict'

import { alertLocation, alertTimestamp } from '../src/services/alertPresentation.js'
import { riskBand, riskColor } from '../src/services/stationData.js'
import {
  environmentalSourceStatusPresentation,
  getEnvironmentalDataNextOffset,
  mergeEnvironmentalDataPages,
  validateEnvironmentalDataPage,
} from '../src/services/environmentalDataService.js'
import {
  ASSISTANT_CONVERSATION_KEY,
  ASSISTANT_DRAFT_KEY,
  clearAssistantConversation,
  getAssistantStorage,
  INITIAL_ASSISTANT_MESSAGE,
  loadAssistantDraft,
  loadAssistantConversation,
  saveAssistantDraft,
  saveAssistantConversation,
} from '../src/services/assistantConversation.js'
import {
  createSatelliteRequestSequence,
  fetchSatelliteStatus,
  fetchSentinel2Scene,
  searchSentinel2Catalog,
} from '../src/services/satelliteService.js'

test('alert card fields match the persisted API alert schema', () => {
  const alert = {
    latitude: 9.9312,
    longitude: 76.2673,
    created_at: '2026-10-11T10:00:00Z',
  }
  assert.equal(alertLocation(alert), '9.9312, 76.2673')
  assert.equal(alertTimestamp(alert), new Date(alert.created_at).toLocaleString())
})

test('alerts without coordinates or valid timestamps render an explicit unavailable state', () => {
  assert.equal(alertLocation({ latitude: null, longitude: null }), 'Location unavailable')
  assert.equal(alertTimestamp({ created_at: 'not-a-date' }), 'Timestamp unavailable')
})

test('environmental catalog states distinguish empty, unverified, partial, stale and failed data', () => {
  assert.deepEqual(environmentalSourceStatusPresentation('NO_MATCHING_STORED_RECORDS'), {
    label: 'NO MATCHING STORED RECORDS',
    tone: '',
  })
  assert.deepEqual(environmentalSourceStatusPresentation('UNVERIFIED'), { label: 'UNVERIFIED', tone: '' })
  assert.deepEqual(environmentalSourceStatusPresentation('PARTIAL'), { label: 'PARTIAL', tone: 'med' })
  assert.deepEqual(environmentalSourceStatusPresentation('STALE'), { label: 'STALE', tone: 'med' })
  assert.deepEqual(environmentalSourceStatusPresentation('ERROR'), { label: 'ERROR', tone: 'high' })
  assert.deepEqual(environmentalSourceStatusPresentation('AVAILABLE'), { label: 'AVAILABLE', tone: 'low' })
})

test('environmental empty pages preserve no-records semantics and returned-page counts', () => {
  const page = {
    records: [],
    sources: [{
      category: 'weather_observation',
      status: 'NO_MATCHING_STORED_RECORDS',
      matching_records: 0,
      count_scope: 'RETURNED_PAGE',
    }],
    pagination: { limit: 100, offset: 0, returned_records: 0, count_scope: 'RETURNED_PAGE' },
    has_more: false,
  }
  assert.equal(validateEnvironmentalDataPage(page, 0), page)
  assert.equal(page.sources[0].status, 'NO_MATCHING_STORED_RECORDS')
})

test('environmental pages merge by returned-page offsets without duplicating records', () => {
  const first = validateEnvironmentalDataPage({
    records: [{ category: 'weather_observation', record_id: 1 }],
    sources: [{
      category: 'weather_observation',
      status: 'AVAILABLE',
      matching_records: 1,
      count_scope: 'RETURNED_PAGE',
    }],
    pagination: { limit: 1, offset: 0, returned_records: 1, count_scope: 'RETURNED_PAGE' },
    has_more: true,
  }, 0)
  const next = validateEnvironmentalDataPage({
    records: [{ category: 'weather_observation', record_id: 2 }],
    sources: [{
      category: 'weather_observation',
      status: 'AVAILABLE',
      matching_records: 1,
      count_scope: 'RETURNED_PAGE',
    }],
    pagination: { limit: 1, offset: 1, returned_records: 1, count_scope: 'RETURNED_PAGE' },
    has_more: false,
  }, first.pagination.offset + first.pagination.returned_records)
  const merged = mergeEnvironmentalDataPages(first, next)
  assert.deepEqual(merged.records.map(record => record.record_id), [1, 2])
  assert.equal(merged.pagination.offset, 1)
  assert.throws(() => mergeEnvironmentalDataPages(first, first), /duplicate record/)
  assert.equal(getEnvironmentalDataNextOffset(first), 1)
  assert.equal(getEnvironmentalDataNextOffset(next), null)
  assert.equal(getEnvironmentalDataNextOffset({
    has_more: true,
    pagination: { offset: 10000, returned_records: 100 },
  }), null)
})

test('environmental page consumer rejects missing or inconsistent pagination and source counts', () => {
  const valid = {
    records: [],
    sources: [{
      category: 'weather_observation',
      status: 'NO_MATCHING_STORED_RECORDS',
      matching_records: 0,
      count_scope: 'RETURNED_PAGE',
    }],
    pagination: { limit: 100, offset: 0, returned_records: 0, count_scope: 'RETURNED_PAGE' },
    has_more: false,
  }
  assert.throws(() => validateEnvironmentalDataPage({ ...valid, pagination: undefined }, 0), /pagination metadata/)
  assert.throws(() => validateEnvironmentalDataPage({
    ...valid,
    pagination: { ...valid.pagination, returned_records: 1 },
  }, 0), /pagination metadata/)
  assert.throws(() => validateEnvironmentalDataPage({
    ...valid,
    sources: [{ ...valid.sources[0], matching_records: 1 }],
  }, 0), /page-scoped source counts/)
})

test('environmental page consumer accepts additive canonical records and legacy records without them', () => {
  const canonicalRecord = {
    contract_version: '1.0',
    record_type: 'observation',
    source: { provider: 'Open-Meteo' },
    geography: {},
    timestamps: { observation_time_utc: '2026-11-12T10:00:00Z' },
    quality_status: 'UNVERIFIED',
    payload: {
      kind: 'observation',
      measurement_basis: 'model_derived',
      measurements: [{
        name: 'temperature_c',
        source_value: 20,
        source_unit: '°C',
        normalized_value: 20,
        normalized_unit: '°C',
      }],
    },
    validation_errors: [],
  }
  const page = {
    records: [
      { category: 'weather_observation', record_id: 1, canonical_record: canonicalRecord },
      { category: 'weather_observation', record_id: 2 },
    ],
    sources: [{
      category: 'weather_observation',
      status: 'UNVERIFIED',
      matching_records: 2,
      count_scope: 'RETURNED_PAGE',
    }],
    pagination: { limit: 10, offset: 0, returned_records: 2, count_scope: 'RETURNED_PAGE' },
    has_more: false,
  }

  assert.equal(validateEnvironmentalDataPage(page, 0), page)
})

test('environmental page consumer rejects a malformed canonical contract without rejecting legacy shape', () => {
  const page = {
    records: [{
      category: 'weather_observation',
      record_id: 1,
      canonical_record: {
        contract_version: '9.0',
        record_type: 'observation',
      },
    }],
    sources: [{
      category: 'weather_observation',
      status: 'UNVERIFIED',
      matching_records: 1,
      count_scope: 'RETURNED_PAGE',
    }],
    pagination: { limit: 10, offset: 0, returned_records: 1, count_scope: 'RETURNED_PAGE' },
    has_more: false,
  }

  assert.throws(() => validateEnvironmentalDataPage(page, 0), /invalid canonical record/)
  const legacyPage = { ...page, records: [{ category: 'weather_observation', record_id: 1 }] }
  assert.equal(validateEnvironmentalDataPage(legacyPage, 0), legacyPage)
})

test('heuristic risk bands and colors match backend score boundaries', () => {
  const cases = [
    [29.99, 'low', '#1f9d6b'],
    [30, 'medium', '#d68b1f'],
    [30.01, 'medium', '#d68b1f'],
    [59.99, 'medium', '#d68b1f'],
    [60, 'high', '#d2452c'],
    [60.01, 'high', '#d2452c'],
    [79.99, 'high', '#d2452c'],
    [80, 'high', '#d2452c'],
    [80.01, 'high', '#d2452c'],
  ]

  for (const [score, band, color] of cases) {
    assert.equal(riskBand(score), band, `score ${score}`)
    assert.equal(riskColor(score), color, `score ${score}`)
  }
})

test('assistant history persists and restores ordered roles and timestamps', () => {
  const values = new Map()
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  }
  const messages = [
    INITIAL_ASSISTANT_MESSAGE,
    { role: 'user', text: 'Question', created_at: '2026-10-27T00:00:00Z' },
    { role: 'assistant', text: 'Answer', created_at: '2026-10-27T00:00:01Z' },
  ]

  assert.equal(saveAssistantConversation(storage, messages), true)
  assert.equal(saveAssistantDraft(storage, 'Unsent question'), true)
  assert.deepEqual(loadAssistantConversation(storage), messages)
  assert.equal(loadAssistantDraft(storage), 'Unsent question')
  assert.ok(values.has(ASSISTANT_CONVERSATION_KEY))
  assert.equal(clearAssistantConversation(storage), true)
  assert.deepEqual(loadAssistantConversation(storage), [INITIAL_ASSISTANT_MESSAGE])
  assert.equal(loadAssistantDraft(storage), '')
  assert.equal(values.has(ASSISTANT_DRAFT_KEY), false)
})

test('assistant history redacts common credential formats before browser persistence', () => {
  let saved
  const storage = {
    setItem: (key, value) => { saved = value },
  }
  saveAssistantConversation(storage, [
    { role: 'user', text: 'API_KEY=examplesecret Bearer abc.def.token' },
  ])
  assert.doesNotMatch(saved, /examplesecret|abc\.def\.token/)
  assert.match(saved, /\[REDACTED\]/)
})

test('assistant history recovers safely from malformed browser storage', () => {
  const storage = { getItem: () => '{bad json' }
  assert.deepEqual(loadAssistantConversation(storage), [INITIAL_ASSISTANT_MESSAGE])
})

test('assistant history handles unavailable browser storage without crashing', () => {
  assert.equal(getAssistantStorage(), null)
  assert.deepEqual(loadAssistantConversation(null), [INITIAL_ASSISTANT_MESSAGE])
  assert.equal(saveAssistantConversation(null, []), false)
  assert.equal(loadAssistantDraft(null), '')
  assert.equal(saveAssistantDraft(null, 'Question'), false)
  assert.equal(clearAssistantConversation(null), false)
})

test('Sentinel scene service sends authenticated bounded request and parses TIFF provenance', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: key => key === 'disasterguard_access_token' ? 'test-token' : null }
  let requestUrl
  let requestOptions
  const metadata = {
    provider: 'Copernicus Data Space',
    product: 'sentinel-2-l2a',
    source_record_id: 'catalog-item',
    acquisition_time: '2026-11-10T05:42:11Z',
    catalog_fetched_at: '2026-11-12T08:30:00Z',
    process_requested_at: '2026-11-12T08:31:00Z',
    downloaded_at: '2026-11-12T08:31:03Z',
    requested_bbox: [-122.42, 37.77, -122.4, 37.79],
    cloud_coverage: 17,
    scene_match_status: 'TIME_AND_AOI_MATCHED_NOT_ITEM_PINNED',
    catalog_search_status: 'COMPLETED',
    catalog_results_status: 'RESULTS_FOUND',
    imagery_status: 'RETRIEVED',
    width: 64,
    height: 64,
  }
  globalThis.fetch = async (url, options) => {
    requestUrl = url
    requestOptions = options
    return {
      ok: true,
      status: 200,
      headers: new Headers({
        'content-type': 'image/tiff',
        'x-satellite-metadata': encodeURIComponent(JSON.stringify(metadata)),
      }),
      blob: async () => new Blob(['tiff']),
    }
  }

  try {
    const result = await fetchSentinel2Scene(
      { latitude: 37.78, longitude: -122.41 },
      { startDate: '2026-11-01', endDate: '2026-11-12', width: 64, height: 64 },
    )
    const url = new URL(requestUrl)
    assert.equal(url.pathname, '/api/satellite/scene/sentinel-2')
    assert.equal(url.searchParams.get('latitude'), '37.78')
    assert.equal(url.searchParams.get('longitude'), '-122.41')
    assert.equal(url.searchParams.get('start_date'), '2026-11-01')
    assert.equal(url.searchParams.get('width'), '64')
    assert.equal(requestOptions.headers.get('Authorization'), 'Bearer test-token')
    assert.equal(requestOptions.signal.aborted, false)
    assert.equal(result.metadata.acquisition_time, '2026-11-10T05:42:11Z')
    assert.equal(result.metadata.downloaded_at, '2026-11-12T08:31:03Z')
    assert.equal(result.metadata.scene_match_status, 'TIME_AND_AOI_MATCHED_NOT_ITEM_PINNED')
    assert.equal(await result.blob.text(), 'tiff')
  } finally {
    globalThis.fetch = originalFetch
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
})

test('satellite service separates authentication, Catalog results, and image availability', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  const requests = []
  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = async (url, options) => {
    requests.push({ url: String(url), options })
    const requestUrl = new URL(url)
    if (requestUrl.pathname.endsWith('/satellite/status')) {
      return new Response(JSON.stringify({
        service: 'Copernicus',
        authentication_status: 'AUTHENTICATED',
        catalog_search_status: 'NOT_CHECKED',
        catalog_results_status: 'NOT_CHECKED',
        imagery_status: 'NOT_CHECKED',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }
    return new Response(JSON.stringify({
      collection: 'sentinel-2-l2a',
      fetched_at: '2026-11-12T08:30:00Z',
      features: [{ id: 'catalog-item-1', acquisition_time: '2026-11-10T05:42:11Z' }],
      context: {},
      query: {},
      catalog_search_status: 'COMPLETED',
      catalog_results_status: 'RESULTS_FOUND',
      imagery_status: 'NOT_REQUESTED',
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  }

  try {
    const authentication = await fetchSatelliteStatus()
    const catalog = await searchSentinel2Catalog(
      { latitude: -33.8688, longitude: 151.2093 },
      { startDate: '2026-11-01', endDate: '2026-11-12' },
    )
    assert.equal(authentication.authentication_status, 'AUTHENTICATED')
    assert.equal(authentication.imagery_status, 'NOT_CHECKED')
    assert.equal(catalog.catalog_search_status, 'COMPLETED')
    assert.equal(catalog.catalog_results_status, 'RESULTS_FOUND')
    assert.equal(catalog.imagery_status, 'NOT_REQUESTED')
    assert.equal(catalog.features.length, 1)
    assert.equal(requests.length, 2)
    assert.match(requests[0].url, /\/api\/satellite\/status$/)
    assert.match(requests[1].url, /\/api\/satellite\/search\/sentinel-2\?/)
  } finally {
    globalThis.fetch = originalFetch
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
})

test('satellite service reports TIFF retrieval failure without treating Catalog results as imagery', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'No matching scene.' }), {
    status: 404,
    headers: { 'Content-Type': 'application/json' },
  })

  try {
    await assert.rejects(
      fetchSentinel2Scene(
        { latitude: 0, longitude: 0 },
        { startDate: '2026-02-28', endDate: '2026-03-01' },
      ),
      error => error.status === 404 && /No matching scene/.test(error.message),
    )
  } finally {
    globalThis.fetch = originalFetch
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
})

test('Sentinel scene service rejects invalid dates, response formats and metadata', async () => {
  const originalFetch = globalThis.fetch
  const originalLocalStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => null }
  try {
    await assert.rejects(
      fetchSentinel2Scene(
        { latitude: 0, longitude: 0 },
        { startDate: '2026-02-30', endDate: '2026-03-01' },
      ),
      /valid start and end date/,
    )
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'application/json' }),
      blob: async () => new Blob(['{}']),
    })
    await assert.rejects(
      fetchSentinel2Scene(
        { latitude: 0, longitude: 0 },
        { startDate: '2026-02-28', endDate: '2026-03-01' },
      ),
      /unsupported image format/,
    )
    globalThis.fetch = async () => ({
      ok: true,
      status: 200,
      headers: new Headers({ 'content-type': 'image/tiff', 'x-satellite-metadata': '%7B%7D' }),
      blob: async () => new Blob(['tiff']),
    })
    await assert.rejects(
      fetchSentinel2Scene(
        { latitude: 0, longitude: 0 },
        { startDate: '2026-02-28', endDate: '2026-03-01' },
      ),
      /metadata was invalid or incomplete/,
    )
  } finally {
    globalThis.fetch = originalFetch
    if (originalLocalStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = originalLocalStorage
  }
})

test('satellite request sequence invalidates results from previously selected locations', () => {
  const sequence = createSatelliteRequestSequence()
  const oldLocationRequest = sequence.next()
  const currentLocationRequest = sequence.next()
  assert.equal(sequence.isCurrent(oldLocationRequest), false)
  assert.equal(sequence.isCurrent(currentLocationRequest), true)
  sequence.invalidate()
  assert.equal(sequence.isCurrent(currentLocationRequest), false)
})
