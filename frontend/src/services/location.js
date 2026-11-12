function coordinateNumber(value, label, minimum, maximum) {
  if (
    (typeof value !== 'number' && typeof value !== 'string')
    || String(value).trim() === ''
  ) {
    throw new Error(`Selected location has an invalid ${label}.`)
  }
  const coordinate = Number(value)
  if (!Number.isFinite(coordinate) || coordinate < minimum || coordinate > maximum) {
    throw new Error(`Selected location has an invalid ${label}.`)
  }
  return coordinate
}

export function normalizeLocation(location) {
  if (!location || typeof location !== 'object') {
    throw new Error('Choose a location with valid coordinates.')
  }
  const latitude = coordinateNumber(location.latitude, 'latitude', -90, 90)
  const longitude = coordinateNumber(location.longitude, 'longitude', -180, 180)
  const name = typeof location.name === 'string' && location.name.trim()
    ? location.name.trim()
    : null
  const admin1 = location.admin1 || location.region || null
  const displayName = String(
    location.display_name
    || [name, admin1, location.admin2, location.country].filter(Boolean).join(', ')
    || `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`,
  )
  const providerMetadata = {
    ...(location.provider_metadata && typeof location.provider_metadata === 'object'
      ? location.provider_metadata
      : {}),
  }
  for (const key of ['feature_code', 'population', 'elevation_m']) {
    if (location[key] != null) providerMetadata[key] = location[key]
  }

  return {
    id: location.id ?? null,
    name,
    admin1,
    admin2: location.admin2 || null,
    country: location.country || null,
    region: admin1,
    timezone: location.timezone || null,
    display_name: displayName,
    latitude,
    longitude,
    coordinate_reference_system: 'OGC:CRS84',
    geometry: { type: 'Point', coordinates: [longitude, latitude] },
    metadata_provider: location.metadata_provider || location.provider || null,
    provider_metadata: providerMetadata,
  }
}

export function selectLocation(location, onChange) {
  const selectedLocation = normalizeLocation(location)
  onChange?.(selectedLocation)
  return selectedLocation
}

export function locationFromCoordinates(latitude, longitude, name = 'Map selection') {
  const validLatitude = coordinateNumber(latitude, 'latitude', -90, 90)
  const validLongitude = coordinateNumber(longitude, 'longitude', -180, 180)
  return normalizeLocation({
    name,
    display_name: `${name} (${validLatitude.toFixed(5)}, ${validLongitude.toFixed(5)})`,
    latitude: validLatitude,
    longitude: validLongitude,
  })
}

export function requestCurrentLocation(geolocation = globalThis.navigator?.geolocation) {
  if (!geolocation || typeof geolocation.getCurrentPosition !== 'function') {
    return Promise.reject(new Error('This browser does not support location access. Search for a place or enter coordinates instead.'))
  }

  return new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      position => {
        try {
          resolve(locationFromCoordinates(
            position?.coords?.latitude,
            position?.coords?.longitude,
            'Current location',
          ))
        } catch {
          reject(new Error('Your browser returned invalid location coordinates. Search for a place or enter coordinates instead.'))
        }
      },
      error => {
        if (error?.code === 1) {
          reject(new Error('Location permission was denied. Allow location access in your browser settings or choose a place manually.'))
        } else if (error?.code === 2) {
          reject(new Error('Your current location is unavailable. Check your device location settings or choose a place manually.'))
        } else if (error?.code === 3) {
          reject(new Error('Finding your current location timed out. Try again or choose a place manually.'))
        } else {
          reject(new Error('Could not determine your current location. Choose a place manually.'))
        }
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    )
  })
}
