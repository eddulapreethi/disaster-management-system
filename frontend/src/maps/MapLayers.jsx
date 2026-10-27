import { GEOJSON_LAYERS } from './geoJsonLayers'

// Simple legend/layer-toggle control shown alongside the Leaflet map.
const RISK_LAYERS = [
  { key: 'high', label: 'High risk', color: '#d2452c' },
  { key: 'medium', label: 'Medium risk', color: '#d68b1f' },
  { key: 'low', label: 'Low risk', color: '#1f9d6b' },
]

export default function MapLayers({
  active,
  onToggle,
  geoActive,
  onGeoToggle,
  geoLoading,
  geoErrors,
  onGeoRetry,
}) {
  return (
    <div>
      <div className="map-layers" aria-label="Risk marker filters">
        {RISK_LAYERS.map(layer => (
          <label key={layer.key} className="map-layer-item">
            <input type="checkbox" checked={active[layer.key]} onChange={() => onToggle(layer.key)} />
            <span className="dot" style={{ background: layer.color }} />
            {layer.label}
          </label>
        ))}
      </div>
      <fieldset className="gis-layer-controls">
        <legend>Reference GIS layers — not flood predictions</legend>
        <div className="gis-layer-list">
          {GEOJSON_LAYERS.map(layer => (
            <div className="gis-layer-row" key={layer.key}>
              <label className="map-layer-item">
                <input
                  type="checkbox"
                  checked={geoActive[layer.key]}
                  onChange={() => onGeoToggle(layer.key)}
                />
                {layer.label}
                {layer.heavy && <span className="gis-layer-heavy"> (load on demand)</span>}
              </label>
              {geoLoading[layer.key] && <span role="status">Loading…</span>}
              {geoErrors[layer.key] && (
                <div className="gis-layer-error" role="alert">
                  <span>{geoErrors[layer.key]}</span>
                  <button type="button" onClick={() => onGeoRetry(layer.key)}>Retry</button>
                </div>
              )}
            </div>
          ))}
        </div>
        <p className="gis-layer-attribution">
          Recorded sources: © OpenStreetMap contributors (ODbL) for OSM-derived layers; HydroSHEDS for watersheds.
          Confirm applicable terms before redistribution. These layers are reference geography only.
        </p>
      </fieldset>
    </div>
  )
}
