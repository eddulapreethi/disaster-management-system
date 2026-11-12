import { createElement as h } from 'react'

export function CountryRanking({ eventsByCountry, datasets = [] }) {
  const countries = Array.isArray(eventsByCountry)
    ? eventsByCountry.filter(item => (
      item
      && typeof item.country === 'string'
      && item.country.trim()
      && Number.isFinite(item.count)
      && item.count >= 0
    )).slice(0, 10)
    : []
  const dateRanges = datasets
    .map(dataset => dataset.date_coverage)
    .filter(range => (
      range
      && typeof range.start === 'string'
      && /^\d{4}-\d{2}-\d{2}$/.test(range.start)
      && typeof range.end === 'string'
      && /^\d{4}-\d{2}-\d{2}$/.test(range.end)
    ))
  const sortedStarts = dateRanges.map(range => range.start).sort()
  const sortedEnds = dateRanges.map(range => range.end).sort()
  const startDate = sortedStarts[0]
  const endDate = sortedEnds[sortedEnds.length - 1]

  return h('div', { className: 'detailbox' },
    h('div', { className: 'sectitle' }, 'Reported event counts by country'),
    h('p', { className: 'explain' },
      `Supplied EM-DAT extracts${startDate && endDate ? ` · parsed start-date span ${startDate}–${endDate}` : ''}. Not a complete global disaster ranking or live surveillance.`,
    ),
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
