import { useEffect } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from 'react-leaflet'

import { magnitudeMarkerRadius } from '../services/earthquakeEventService'

const WORLD_VIEW = [20, 0]

function normalizeLongitude(longitude) {
  const normalized = ((longitude + 180) % 360 + 360) % 360 - 180
  return normalized === -180 && longitude > 0 ? 180 : normalized
}

function toQueryBounds(bounds) {
  const rawWest = bounds.getWest()
  const rawEast = bounds.getEast()
  const south = bounds.getSouth()
  const north = bounds.getNorth()
  const longitudeSpan = rawEast - rawWest
  if (
    !Number.isFinite(longitudeSpan)
    || longitudeSpan <= 0
    || longitudeSpan > 30
    || south < -90
    || north > 90
    || north - south <= 0
    || north - south > 20
  ) {
    return null
  }
  return {
    west: normalizeLongitude(rawWest),
    south,
    east: normalizeLongitude(rawEast),
    north,
  }
}

function TrackMapArea({ location, onMapAreaChange }) {
  const map = useMap()
  useMapEvents({
    moveend() {
      onMapAreaChange(toQueryBounds(map.getBounds()))
    },
    zoomend() {
      onMapAreaChange(toQueryBounds(map.getBounds()))
    },
  })

  useEffect(() => {
    if (location) {
      map.setView([location.latitude, location.longitude], 5)
    }
  }, [location?.latitude, location?.longitude, map])

  useEffect(() => {
    onMapAreaChange(toQueryBounds(map.getBounds()))
  }, [map, onMapAreaChange])

  return null
}

function formatTime(value) {
  return value instanceof Date && Number.isFinite(value.getTime())
    ? value.toLocaleString()
    : 'Unavailable'
}

export default function EarthquakeEventMap({
  events,
  selectedEventId,
  onSelectEvent,
  location,
  onMapAreaChange,
}) {
  const center = location ? [location.latitude, location.longitude] : WORLD_VIEW

  return (
    <div className="card earthquake-map-card">
      <div className="sectitle">USGS ComCat event locations</div>
      <p className="explain">
        Reported catalog events only. Marker size loosely follows reported magnitude for display; it is not a
        calibrated measure of damage, impact, or risk.
      </p>
      <div className="earthquake-map-legend">
        <span className="earthquake-marker-sample small" aria-hidden="true" />
        <span>smaller reported magnitude</span>
        <span className="earthquake-marker-sample large" aria-hidden="true" />
        <span>larger reported magnitude</span>
      </div>
      <MapContainer
        center={center}
        zoom={location ? 5 : 2}
        scrollWheelZoom
        className="leaflet-map earthquake-leaflet-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <TrackMapArea location={location} onMapAreaChange={onMapAreaChange} />
        {events.map(event => (
          <CircleMarker
            key={event.id}
            center={[event.latitude, event.longitude]}
            radius={selectedEventId === event.id
              ? magnitudeMarkerRadius(event.magnitude) + 2
              : magnitudeMarkerRadius(event.magnitude)}
            pathOptions={{
              color: selectedEventId === event.id ? '#0a5a66' : '#286c8e',
              fillColor: '#55a6c2',
              fillOpacity: 0.75,
              weight: selectedEventId === event.id ? 3 : 2,
            }}
            eventHandlers={{ click: () => onSelectEvent(event.id) }}
          >
            <Popup>
              <strong>{event.title || event.place || `USGS event ${event.id}`}</strong>
              <br />
              Magnitude: {event.magnitude ?? 'Unavailable'}{event.magnitudeType ? ` ${event.magnitudeType}` : ''}
              <br />
              Event time: {formatTime(event.eventTime)}
              <br />
              Review status: {event.reviewStatus || 'Unavailable'}
              {event.sourceUrl && (
                <>
                  <br />
                  <a href={event.sourceUrl} target="_blank" rel="noreferrer">USGS source event</a>
                </>
              )}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
