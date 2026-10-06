import { useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, Tooltip } from 'react-leaflet'
import { stations, riskBand, riskColor } from '../services/stationData'
import MapLayers from './MapLayers'

export default function RiskMap({ points, selected, onSelect }) {
  const [active, setActive] = useState({ high: true, medium: true, low: true })
  const toggle = key => setActive(a => ({ ...a, [key]: !a[key] }))
  const visible = points.filter(point => active[riskBand(point.risk)])

  return (
    <div className="card">
      <MapLayers active={active} onToggle={toggle} />
      <MapContainer center={[22.5, 80]} zoom={4.3} scrollWheelZoom={true} className="leaflet-map">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {visible.map(point => (
          <CircleMarker
            key={point.id}
            center={[point.lat, point.lng]}
            radius={point.id === selected?.id ? 12 : 9}
            pathOptions={{ color: riskColor(point.risk), fillColor: riskColor(point.risk), fillOpacity: 0.75, weight: 2 }}
            eventHandlers={{ click: () => onSelect(point) }}
          >
            <Tooltip direction="top">{point.name} — risk {point.risk}</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
