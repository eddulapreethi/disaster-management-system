import test from 'node:test'
import assert from 'node:assert/strict'

import { searchLocations } from '../src/services/locationSearchService.js'
import { fetchLocationCoverage } from '../src/services/coverageService.js'
import {
  createEnvironmentalDataRequestSequence,
  fetchEnvironmentalData,
} from '../src/services/environmentalDataService.js'
import { predictRisk } from '../src/services/predictionService.js'
import {
  locationFromCoordinates,
  normalizeLocation,
  requestCurrentLocation,
  selectLocation,
} from '../src/services/location.js'
import { createWeatherRequestSequence, fetchOnDemandWeather } from '../src/services/weatherService.js'

function installBrowserFetch(handler) {
  const originalFetch = globalThis.fetch
  const originalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
  const requests = []
  globalThis.localStorage = { getItem: () => null }
  globalThis.fetch = async (url, options) => {
    requests.push({ url: String(url), options })
    return handler(String(url), options)
  }
  return {
    requests,
    restore() {
      globalThis.fetch = originalFetch
      if (originalStorage) Object.defineProperty(globalThis, 'localStorage', originalStorage)
      else delete globalThis.localStorage
    },
  }
}

test('current location is requested only when the explicit request helper is called', async () => {
  let called = false
  const location = await requestCurrentLocation({
    getCurrentPosition(success, _error, options) {
      called = true
      assert.equal(options.timeout, 10000)
      success({ coords: { latitude: 9.9, longitude: 76.2 } })
    },
  })

  assert.equal(called, true)
  assert.equal(location.name, 'Current location')
  assert.equal(location.latitude, 9.9)
  assert.equal(location.longitude, 76.2)
})

test('current location explains denied permission, unavailable position, and timeout', async () => {
  const cases = [
    [1, /permission was denied/i],
    [2, /location is unavailable/i],
    [3, /timed out/i],
  ]

  for (const [code, message] of cases) {
    await assert.rejects(
      requestCurrentLocation({
        getCurrentPosition(_success, failure) {
          failure({ code })
        },
      }),
      message,
    )
  }
})

test('current location reports unsupported browsers and rejects invalid coordinates', async () => {
  await assert.rejects(requestCurrentLocation(null), /does not support location access/i)
  await assert.rejects(
    requestCurrentLocation({
      getCurrentPosition(success) {
        success({ coords: { latitude: 91, longitude: 0 } })
      },
    }),
    /returned invalid location coordinates/i,
  )
  assert.throws(() => normalizeLocation({ latitude: '', longitude: 0 }), /invalid latitude/i)
  assert.throws(() => normalizeLocation({ latitude: 0, longitude: 181 }), /invalid longitude/i)
})

test('manual geocoding returns selectable named results with validated coordinates', async () => {
  const browser = installBrowserFetch(async () => new Response(JSON.stringify({
    query: 'Hyderabad',
    results: [{
      id: 1,
      name: 'Hyderabad',
      admin1: 'Telangana',
      country: 'India',
      display_name: 'Hyderabad, Telangana, India',
      latitude: 17.385,
      longitude: 78.4867,
    }],
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  try {
    const results = await searchLocations(' Hyderabad ')
    let updatedLocation = null
    const selected = selectLocation(results[0], location => { updatedLocation = location })

    assert.match(browser.requests[0].url, /\/api\/geocoding\/search\?query=Hyderabad/)
    assert.equal(selected.display_name, 'Hyderabad, Telangana, India')
    assert.deepEqual([selected.latitude, selected.longitude], [17.385, 78.4867])
    assert.deepEqual(updatedLocation, selected)
  } finally {
    browser.restore()
  }
})

test('map clicks create coordinate-only selections without reverse-geocoding', () => {
  let updatedLocation = null
  const mapPoint = locationFromCoordinates(40.7128, -74.006, 'Map selection')
  const selected = selectLocation(mapPoint, location => { updatedLocation = location })

  assert.equal(selected.display_name, 'Map selection (40.71280, -74.00600)')
  assert.equal(selected.country, null)
  assert.equal(selected.latitude, 40.7128)
  assert.equal(selected.longitude, -74.006)
  assert.deepEqual(updatedLocation, selected)
})

test('location contract accepts coordinates across continents and preserves source metadata', () => {
  const locations = [
    { latitude: 40.7128, longitude: -74.006, name: 'New York' },
    { latitude: -33.8688, longitude: 151.2093, name: 'Sydney' },
    { latitude: -1.2921, longitude: 36.8219, name: 'Nairobi' },
    { latitude: 90, longitude: 180 },
    { latitude: -90, longitude: -180 },
  ].map(normalizeLocation)

  assert.equal(locations.length, 5)
  assert.deepEqual(locations[0].geometry, { type: 'Point', coordinates: [-74.006, 40.7128] })
  assert.equal(locations[0].coordinate_reference_system, 'OGC:CRS84')
  assert.equal(locations[3].name, null)
  assert.equal(locations[3].country, null)

  const geocoded = normalizeLocation({
    name: 'Example',
    latitude: 12,
    longitude: 34,
    metadata_provider: 'open-meteo-geocoding',
    timezone: 'Etc/UTC',
    feature_code: 'PPL',
    population: 100,
  })
  assert.equal(geocoded.metadata_provider, 'open-meteo-geocoding')
  assert.deepEqual(geocoded.provider_metadata, { feature_code: 'PPL', population: 100 })
  assert.equal(geocoded.timezone, 'Etc/UTC')
})

test('weather requests use the currently selected location coordinates', async () => {
  const browser = installBrowserFetch(async url => {
    const requestUrl = new URL(url)
    const latitude = Number(requestUrl.searchParams.get('latitude'))
    const longitude = Number(requestUrl.searchParams.get('longitude'))
    return new Response(JSON.stringify({
      latitude,
      longitude,
      provider_latitude: latitude + 0.01,
      provider_longitude: longitude + 0.02,
      requested_latitude: latitude,
      requested_longitude: longitude,
      temperature_c: 20,
      humidity_percent: 50,
      precipitation_mm: 0,
      rain_mm: 0,
      wind_speed_kmh: 5,
      pressure_hpa: 1010,
      observation_time: new Date().toISOString(),
      fetched_at: new Date().toISOString(),
      source: 'open-meteo',
      freshness_status: 'READY',
      measurement_status: 'READY',
      observation_age_seconds: 0,
      max_age_seconds: 7200,
      measurement_units: { temperature_c: '°C', precipitation_mm: 'mm', wind_speed_kmh: 'km/h' },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })

  try {
    let selectedLocation = null
    selectLocation(
      { name: 'First place', latitude: 12.5, longitude: 30.25 },
      location => { selectedLocation = location },
    )
    await fetchOnDemandWeather(selectedLocation)

    selectLocation(
      { name: 'Second place', latitude: -33.9, longitude: 151.2 },
      location => { selectedLocation = location },
    )
    const secondReading = await fetchOnDemandWeather(selectedLocation)

    assert.match(browser.requests[0].url, /latitude=12\.5&longitude=30\.25/)
    assert.match(browser.requests[1].url, /latitude=-33\.9&longitude=151\.2/)
    assert.equal(secondReading.requestedLatitude, -33.9)
  } finally {
    browser.restore()
  }
})

test('weather service preserves stale and fetch provenance without calling it current', async () => {
  const observationTime = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
  const fetchedAt = new Date().toISOString()
  const browser = installBrowserFetch(async () => new Response(JSON.stringify({
    latitude: 9.93,
    longitude: 76.27,
    provider_latitude: 9.95,
    provider_longitude: 76.3,
    requested_latitude: 9.93,
    requested_longitude: 76.27,
    temperature_c: 28,
    humidity_percent: 70,
    precipitation_mm: 2,
    rain_mm: 2,
    wind_speed_kmh: 10,
    pressure_hpa: 1008,
    observation_time: observationTime,
    fetched_at: fetchedAt,
    source: 'open-meteo',
    freshness_status: 'STALE',
    freshness_message: 'Older than configured window',
    observation_age_seconds: 10800,
    max_age_seconds: 7200,
    measurement_units: { temperature_c: '°C', precipitation_mm: 'mm', wind_speed_kmh: 'km/h' },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  try {
    const reading = await fetchOnDemandWeather({ name: 'Kochi', latitude: 9.93, longitude: 76.27 })
    assert.equal(reading.freshnessStatus, 'STALE')
    assert.equal(reading.observationTime, observationTime)
    assert.equal(reading.fetchedAt, fetchedAt)
    assert.equal(reading.latitude, 9.95)
    assert.equal(reading.requestedLatitude, 9.93)
  } finally {
    browser.restore()
  }
})

test('location coverage request uses selected WGS 84 coordinates and keeps independent statuses', async () => {
  const browser = installBrowserFetch(async url => {
    const requestUrl = new URL(url)
    return new Response(JSON.stringify({
      latitude: Number(requestUrl.searchParams.get('latitude')),
      longitude: Number(requestUrl.searchParams.get('longitude')),
      coordinate_reference_system: 'OGC:CRS84',
      checked_at: new Date().toISOString(),
      providers: [
        { provider: 'Open-Meteo', capability: 'weather', status: 'UNVERIFIED' },
        { provider: 'NWDP/NWIC CWC', capability: 'hydrology', status: 'UNVERIFIED' },
        { provider: 'Local GIS', capability: 'reference_gis', status: 'UNSUPPORTED' },
      ],
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })
  })

  try {
    const coverage = await fetchLocationCoverage({
      latitude: -33.8688,
      longitude: 151.2093,
      name: 'Sydney',
    })
    assert.match(browser.requests[0].url, /\/api\/coverage\?latitude=-33\.8688&longitude=151\.2093/)
    assert.deepEqual(coverage.providers.map(item => item.status), ['UNVERIFIED', 'UNVERIFIED', 'UNSUPPORTED'])
  } finally {
    browser.restore()
  }
})

test('environmental data query uses selected coordinates and returns distinct source categories', async () => {
  const browser = installBrowserFetch(async () => new Response(JSON.stringify({
    records: [],
    sources: [
      { category: 'weather_observation', status: 'NO_MATCHING_STORED_RECORDS', matching_records: 0, count_scope: 'RETURNED_PAGE' },
      { category: 'weather_forecast', status: 'NOT_PERSISTED', matching_records: 0, count_scope: 'RETURNED_PAGE' },
      { category: 'hydrological_observation', status: 'NO_MATCHING_STORED_RECORDS', matching_records: 0, count_scope: 'RETURNED_PAGE' },
      { category: 'disaster_event_report', status: 'UNVERIFIED', matching_records: 0, count_scope: 'RETURNED_PAGE' },
      { category: 'satellite_scene_metadata', status: 'NOT_PERSISTED', matching_records: 0, count_scope: 'RETURNED_PAGE' },
      { category: 'geographic_reference_dataset', status: 'REGIONAL', matching_records: 0, count_scope: 'RETURNED_PAGE' },
    ],
    pagination: { limit: 100, offset: 0, returned_records: 0, count_scope: 'RETURNED_PAGE' },
    has_more: false,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  try {
    const result = await fetchEnvironmentalData({ latitude: -33.8688, longitude: 151.2093 })
    const requestedUrl = new URL(browser.requests[0].url)
    assert.match(requestedUrl.pathname, /\/api\/environmental-data$/)
    assert.equal(requestedUrl.searchParams.get('latitude'), '-33.8688')
    assert.equal(requestedUrl.searchParams.get('longitude'), '151.2093')
    assert.equal(requestedUrl.searchParams.get('radius_km'), '25')
    assert.equal(requestedUrl.searchParams.get('offset'), '0')
    assert.deepEqual(result.sources.map(source => source.category), [
      'weather_observation',
      'weather_forecast',
      'hydrological_observation',
      'disaster_event_report',
      'satellite_scene_metadata',
      'geographic_reference_dataset',
    ])
    assert.equal(result.sources[0].status, 'NO_MATCHING_STORED_RECORDS')
    assert.equal(result.sources[3].status, 'UNVERIFIED')
  } finally {
    browser.restore()
  }
})

test('environmental catalog forwards the requested pagination offset', async () => {
  const browser = installBrowserFetch(async () => new Response(JSON.stringify({
    records: [],
    sources: [],
    has_more: false,
    pagination: { limit: 100, offset: 100, returned_records: 0, count_scope: 'RETURNED_PAGE' },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  try {
    await fetchEnvironmentalData({ latitude: 9.9, longitude: 76.2 }, { offset: 100 })
    const requestedUrl = new URL(browser.requests[0].url)
    assert.equal(requestedUrl.searchParams.get('offset'), '100')
    assert.equal(requestedUrl.searchParams.get('limit'), '100')
  } finally {
    browser.restore()
  }
})

test('environmental request sequence prevents an older location response from replacing the newer one', () => {
  const sequence = createEnvironmentalDataRequestSequence()
  let visibleLocation = null
  const firstRequest = sequence.next()
  const secondRequest = sequence.next()

  if (sequence.isCurrent(secondRequest)) visibleLocation = 'Sydney'
  if (sequence.isCurrent(firstRequest)) visibleLocation = 'London'

  assert.equal(visibleLocation, 'Sydney')
  sequence.invalidate(secondRequest)
  assert.equal(sequence.isCurrent(secondRequest), false)
})

test('stale weather does not proceed to a prediction request', async () => {
  const browser = installBrowserFetch(async () => new Response(JSON.stringify({
    temperature_c: 20,
    precipitation_mm: 1,
    wind_speed_kmh: 5,
    observation_time: new Date(Date.now() - 3 * 60 * 60_000).toISOString(),
    fetched_at: new Date().toISOString(),
    source: 'open-meteo',
    freshness_status: 'STALE',
    freshness_message: 'Outside freshness window',
    max_age_seconds: 7200,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } }))

  try {
    await assert.rejects(
      predictRisk({ name: 'Kochi', latitude: 9.93, longitude: 76.27 }),
      /weather observation is stale/i,
    )
    assert.equal(browser.requests.length, 1)
    assert.match(browser.requests[0].url, /\/weather\/current\?/)
  } finally {
    browser.restore()
  }
})

test('weather service rejects invalid timestamps, missing measurements, and unavailable provider data', async () => {
  const base = {
    temperature_c: 20,
    precipitation_mm: 0,
    wind_speed_kmh: 5,
    observation_time: new Date().toISOString(),
    fetched_at: new Date().toISOString(),
    freshness_status: 'READY',
  }
  const replies = [
    { ...base, observation_time: 'not-a-time' },
    { ...base, temperature_c: null },
    { ...base, freshness_status: 'UNAVAILABLE' },
  ]

  for (const payload of replies) {
    const browser = installBrowserFetch(async () => new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    try {
      await assert.rejects(
        fetchOnDemandWeather({ name: 'Test', latitude: 10, longitude: 20 }),
        /weather provider/i,
      )
    } finally {
      browser.restore()
    }
  }
})

test('a late response from an earlier location cannot replace the newest weather request', () => {
  const requests = createWeatherRequestSequence()
  const oldLocationRequest = requests.next()
  const newLocationRequest = requests.next()

  assert.equal(requests.isCurrent(oldLocationRequest), false)
  assert.equal(requests.isCurrent(newLocationRequest), true)
  requests.invalidate()
  assert.equal(requests.isCurrent(newLocationRequest), false)
})
