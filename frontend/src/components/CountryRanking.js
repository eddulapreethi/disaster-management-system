import { createElement as h } from 'react'

export function CountryRanking({ eventsByCountry }) {
  const countries = Array.isArray(eventsByCountry)
    ? eventsByCountry.filter(item => (
      item
      && typeof item.country === 'string'
      && item.country.trim()
      && Number.isFinite(item.count)
      && item.count >= 0
    )).slice(0, 10)
    : []

  return h('div', { className: 'detailbox' },
    h('div', { className: 'sectitle' }, 'Most-recorded countries'),
    countries.length
      ? countries.map(({ country, count }) => h(
        'div',
        { className: 'kv', key: country },
        h('span', null, country),
        h('span', null, count.toLocaleString()),
      ))
      : h('p', { className: 'explain' }, 'No country-level event counts are available.'),
  )
}
