import { CircleMarker, MapContainer, TileLayer, Tooltip } from 'react-leaflet'

const STATUS_COLORS = {
  verified: '#16865a',
  pending: '#d68b1f',
  needs_review: '#7651b5',
  rejected: '#777777',
}

export default function IncidentMap({ records, selectedId, onSelect }) {
  return (
    <div className="card">
      <div className="sectitle">Community incident reports · global WGS 84 coordinates</div>
      <p className="explain">
        Verified reports are green; unverified reports are amber or purple. Markers are submitted community reports,
        not official observations or warnings. An empty map does not mean no disaster exists.
      </p>
      <div className="incident-map-legend" aria-label="Incident verification legend">
        {Object.entries(STATUS_COLORS).map(([status, color]) => (
          <span key={status}><i style={{ backgroundColor: color }} />{status.replace('_', ' ')}</span>
        ))}
      </div>
      <MapContainer center={[20, 0]} zoom={2} scrollWheelZoom className="leaflet-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {records.map(record => (
          <CircleMarker
            key={record.id}
            center={[record.latitude, record.longitude]}
            radius={selectedId === record.id ? 11 : 8}
            pathOptions={{
              color: STATUS_COLORS[record.status] || STATUS_COLORS.pending,
              fillColor: STATUS_COLORS[record.status] || STATUS_COLORS.pending,
              fillOpacity: 0.78,
              weight: 2,
            }}
            eventHandlers={{ click: () => onSelect(record.id) }}
          >
            <Tooltip direction="top">
              {record.hazard_category} · {record.status.replace('_', ' ')} · {record.latitude}, {record.longitude}
            </Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
