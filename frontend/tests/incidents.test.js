import test from 'node:test'
import assert from 'node:assert/strict'

import {
  buildIncidentQuery,
  fetchIncidents,
  getIncidentNextOffset,
  mergeIncidentPages,
  reviewIncident,
  submitIncident,
  updateIncident,
  validateIncidentPage,
} from '../src/services/incidentService.js'

function incident(id, overrides = {}) {
  return {
    id,
    title: `Incident ${id}`,
    hazard_category: 'flood',
    description: 'Community-submitted report description.',
    latitude: 0,
    longitude: 180,
    incident_time: '2026-11-12T10:00:00Z',
    incident_timezone: 'UTC',
    submitted_at: '2026-11-12T11:00:00Z',
    status: 'pending',
    source: 'community_report',
    provenance: { submission_method: 'authenticated_community_report' },
    can_edit: true,
    can_review: false,
    ...overrides,
  }
}

function page(records, { offset = 0, total = records.length, limit = 2 } = {}) {
  return {
    records,
    pagination: { offset, limit, returned_records: records.length, total_matching_records: total },
    has_more: offset + records.length < total,
  }
}

test('incident query preserves hazard, status, UTC dates and pagination', () => {
  const query = new URLSearchParams(buildIncidentQuery({
    hazard_category: 'earthquake',
    verification_status: 'verified',
    start_date: '2026-11-01',
    end_date: '2026-11-12',
  }, { limit: 25, offset: 50 }))

  assert.equal(query.get('hazard_category'), 'earthquake')
  assert.equal(query.get('verification_status'), 'verified')
  assert.equal(query.get('start_time'), '2026-11-01T00:00:00Z')
  assert.equal(query.get('end_time'), '2026-11-12T23:59:59.999Z')
  assert.equal(query.get('limit'), '25')
  assert.equal(query.get('offset'), '50')
})

test('incident response validates global coordinates, statuses and private-field exclusion', () => {
  const global = incident(1, { latitude: -90, longitude: -180, status: 'verified' })
  assert.equal(validateIncidentPage(page([global]), 0).records[0], global)
  assert.throws(() => validateIncidentPage(page([incident(2, { latitude: 90.1 })]), 0), /invalid or private/)
  assert.throws(() => validateIncidentPage(page([incident(3, { status: 'official' })]), 0), /invalid or private/)
  assert.throws(() => validateIncidentPage(page([incident(4, { reporter_id: 7 })]), 0), /invalid or private/)
  assert.throws(() => validateIncidentPage(page([incident(5, { evidence_metadata: [] })]), 0), /invalid or private/)
})

test('incident pagination advances by returned records and rejects malformed or duplicate pages', () => {
  const first = validateIncidentPage(page([incident(1), incident(2)], { total: 3 }), 0)
  assert.equal(getIncidentNextOffset(first), 2)
  const second = validateIncidentPage(page([incident(3)], { offset: 2, total: 3 }), 2)
  assert.deepEqual(mergeIncidentPages(first, second).records.map(item => item.id), [1, 2, 3])
  assert.equal(getIncidentNextOffset(mergeIncidentPages(first, second)), null)
  assert.throws(() => validateIncidentPage(page([incident(1)], { offset: 2, total: 3 }), 0), /inconsistent/)
  assert.throws(() => mergeIncidentPages(first, validateIncidentPage(page([incident(2)], { offset: 2, total: 3 }), 2)), /duplicate/)
})

test('incident API methods use authenticated backend paths and preserve separate review operations', async () => {
  const previousFetch = globalThis.fetch
  const previousLocalStorage = globalThis.localStorage
  const calls = []
  globalThis.localStorage = { getItem: () => 'test-token', removeItem: () => {} }
  globalThis.fetch = async (url, options) => {
    calls.push({ url: String(url), options })
    return new Response(JSON.stringify(page([incident(1)])), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }
  try {
    await fetchIncidents({}, { limit: 10, offset: 0 })
    await submitIncident({ hazard_category: 'flood' })
    await updateIncident(1, { title: 'Edited title' })
    await reviewIncident(1, { status: 'verified' })
    assert.match(calls[0].url, /\/api\/incidents\?/)
    assert.match(calls[0].options.headers.get('Authorization'), /^Bearer /)
    assert.equal(calls[1].options.method, 'POST')
    assert.equal(calls[2].options.method, 'PATCH')
    assert.match(calls[3].url, /\/api\/incidents\/1\/reviews$/)
    assert.equal(calls[3].options.method, 'POST')
  } finally {
    globalThis.fetch = previousFetch
    globalThis.localStorage = previousLocalStorage
  }
})

test('incident UI remains separate from legacy risk markers and states community-report limits', async () => {
  const { readFile } = await import('node:fs/promises')
  const [pageSource, mapSource, routesSource, sidebarSource] = await Promise.all([
    readFile(new URL('../src/pages/Incidents.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/maps/IncidentMap.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/App.jsx', import.meta.url), 'utf8'),
    readFile(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8'),
  ])
  assert.match(pageSource, /not official observations or emergency warnings/)
  assert.match(pageSource, /an empty result does\s*not mean no disaster exists/)
  assert.match(pageSource, /not upload files/)
  assert.match(mapSource, /center=\{\[record\.latitude, record\.longitude\]\}/)
  assert.doesNotMatch(mapSource, /riskBand|riskColor|MapLayers/)
  assert.match(routesSource, /path="\/incidents"/)
  assert.match(sidebarSource, /Incident reports/)
})
