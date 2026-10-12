export function alertLocation(alert) {
  if (!Number.isFinite(alert.latitude) || !Number.isFinite(alert.longitude)) {
    return 'Location unavailable'
  }
  return `${alert.latitude.toFixed(4)}, ${alert.longitude.toFixed(4)}`
}

export function alertTimestamp(alert) {
  const date = new Date(alert.created_at)
  return Number.isNaN(date.getTime()) ? 'Timestamp unavailable' : date.toLocaleString()
}
