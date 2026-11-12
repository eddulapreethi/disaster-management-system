import test from 'node:test'
import assert from 'node:assert/strict'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

import { CountryRanking } from '../src/components/CountryRanking.js'

test('country ranking renders the backend country/count object-array response', () => {
  const markup = renderToStaticMarkup(createElement(CountryRanking, {
    eventsByCountry: [
      { country: 'China', count: 635 },
      { country: 'United States of America', count: 623 },
    ],
    datasets: [
      { date_coverage: { start: '2000-01-03', end: '2021-12-30' } },
      { date_coverage: { start: '1999-02-01', end: '2025-01-14' } },
    ],
  }))

  assert.match(markup, /Reported event counts by country/)
  assert.match(markup, /Supplied EM-DAT extracts/)
  assert.match(markup, /1999-02-01–2025-01-14/)
  assert.match(markup, /Not a complete global disaster ranking/)
  assert.match(markup, /China/)
  assert.match(markup, /635/)
  assert.match(markup, /United States of America/)
  assert.match(markup, /623/)
  assert.doesNotMatch(markup, /\[object Object\]/)
})

test('country ranking handles empty and malformed entries without inventing values', () => {
  const markup = renderToStaticMarkup(createElement(CountryRanking, {
    eventsByCountry: [
      { country: '', count: 10 },
      { country: 'Missing count' },
      null,
    ],
  }))

  assert.match(markup, /No country-level event counts are available/)
  assert.doesNotMatch(markup, /\[object Object\]/)
})
