import { useEffect, useState } from 'react'
import { MapContainer, TileLayer, CircleMarker, GeoJSON, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { apiGet } from '../services/api'
import { riskBand, riskColor } from '../services/stationData'
import MapLayers from './MapLayers'
import { illustrativeMarkerRadius } from '../digitalTwin/scenarioEngine'
import {
  GEOJSON_LAYERS,
  GEOJSON_LAYER_STYLES,
  INITIAL_GEOJSON_VISIBILITY,
  parseGeoJsonFeatureCollection,
} from './geoJsonLayers'

const KOCHI_STUDY_BOUNDS = [[9.8, 76.0], [10.1, 76.5]]

function FitKochiStudyBounds({ enabled }) {
  const map = useMap()

  useEffect(() => {
    if (enabled) {
      map.fitBounds(KOCHI_STUDY_BOUNDS, { padding: [20, 20] })
    }
  }, [enabled, map])

  return null
}

function FitSelectionBounds({ bounds, enabled }) {
  const map = useMap()

  useEffect(() => {
    if (enabled && bounds) {
      map.fitBounds(bounds, { padding: [20, 20] })
    }
  }, [bounds, enabled, map])

  return null
}

function MapPointSelector({ enabled, bounds, onSelect }) {
  useMapEvents({
    click(event) {
      if (!enabled || !bounds || typeof onSelect !== 'function') return
      const { lat, lng } = event.latlng
      if (
        lat >= bounds[0][0]
        && lat <= bounds[1][0]
        && lng >= bounds[0][1]
        && lng <= bounds[1][1]
      ) {
        onSelect({ latitude: lat, longitude: lng })
      }
    },
  })

  return null
}

export default function RiskMap({
  points = [],
  selected = null,
  onSelect = () => {},
  simulationFrame = null,
  comparisonFrame = null,
  simulationCenter = null,
  selectionBounds = null,
  onSimulationCenterChange,
}) {
  const [active, setActive] = useState({ high: true, medium: true, low: true })
  const [geoActive, setGeoActive] = useState(() => ({ ...INITIAL_GEOJSON_VISIBILITY }))
  const [geoData, setGeoData] = useState({})
  const [geoLoading, setGeoLoading] = useState({})
  const [geoErrors, setGeoErrors] = useState({})
  const toggle = key => setActive(a => ({ ...a, [key]: !a[key] }))
  const visible = points.filter(point => active[riskBand(point.risk)])
  const anyGeoLayerActive = GEOJSON_LAYERS.some(layer => geoActive[layer.key])
  const isSimulationMap = Boolean(onSimulationCenterChange)
  const center = simulationCenter
    ? [simulationCenter.latitude, simulationCenter.longitude]
    : [22.5, 80]

  const loadGeoLayer = key => {
    if (geoData[key] || geoLoading[key]) return
    setGeoLoading(current => ({ ...current, [key]: true }))
    setGeoErrors(current => ({ ...current, [key]: '' }))
    apiGet(`/gis/layers/${key}`, { timeoutMs: 60000 })
      .then(parseGeoJsonFeatureCollection)
      .then(data => setGeoData(current => ({ ...current, [key]: data })))
      .catch(error => {
        setGeoErrors(current => ({
          ...current,
          [key]: error.message || 'Could not load this reference GIS layer.',
        }))
      })
      .finally(() => setGeoLoading(current => ({ ...current, [key]: false })))
  }

  const toggleGeoLayer = key => {
    const enabled = !geoActive[key]
    setGeoActive(current => ({ ...current, [key]: enabled }))
    if (enabled) loadGeoLayer(key)
  }

  return (
    <div className="card">
      <MapLayers
        active={active}
        onToggle={toggle}
        geoActive={geoActive}
        onGeoToggle={toggleGeoLayer}
        geoLoading={geoLoading}
        geoErrors={geoErrors}
        onGeoRetry={loadGeoLayer}
      />
      <MapContainer
        center={center}
        zoom={isSimulationMap ? 8 : 4.3}
        scrollWheelZoom={true}
        className="leaflet-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitKochiStudyBounds enabled={!isSimulationMap && anyGeoLayerActive} />
        <FitSelectionBounds bounds={selectionBounds} enabled={isSimulationMap} />
        <MapPointSelector
          enabled={isSimulationMap}
          bounds={selectionBounds}
          onSelect={onSimulationCenterChange}
        />
        {GEOJSON_LAYERS.map(layer => (
          geoActive[layer.key] && geoData[layer.key] && (
            <GeoJSON
              key={layer.key}
              data={geoData[layer.key]}
              style={GEOJSON_LAYER_STYLES[layer.key]}
            />
          )
        ))}
        {simulationFrame && simulationCenter && (
          <CircleMarker
            center={center}
            radius={illustrativeMarkerRadius(simulationFrame)}
            pathOptions={{
              color: '#8b5cf6',
              fillColor: '#a78bfa',
              fillOpacity: 0.22,
              weight: 3,
              dashArray: '5 4',
            }}
          >
            <Tooltip direction="top" permanent>
              Illustrative scenario symbol — not water spread
            </Tooltip>
          </CircleMarker>
        )}
        {comparisonFrame && simulationCenter && (
          <CircleMarker
            center={center}
            radius={illustrativeMarkerRadius(comparisonFrame) + 10}
            pathOptions={{
              color: '#e879f9',
              fillColor: '#e879f9',
              fillOpacity: 0.05,
              weight: 2,
              dashArray: '2 5',
            }}
          >
            <Tooltip direction="bottom" permanent>
              Comparison scenario symbol — not water spread
            </Tooltip>
          </CircleMarker>
        )}
        {visible.map(point => (
          <CircleMarker
            key={point.id}
            center={[point.lat, point.lng]}
            radius={point.id === selected?.id ? 12 : 9}
            pathOptions={{ color: riskColor(point.risk), fillColor: riskColor(point.risk), fillOpacity: 0.75, weight: 2 }}
            eventHandlers={{ click: () => onSelect(point) }}
          >
            <Tooltip direction="top">{point.name} — unverified legacy score {point.risk}</Tooltip>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
