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
  }))

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
