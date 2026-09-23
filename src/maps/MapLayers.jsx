// Simple legend/layer-toggle control shown alongside the Leaflet map.
// "Layers" here just filters which risk bands render as markers —
// there's a single real data source (station risk), not separate map tiles.
const LAYERS = [
  { key: 'high', label: 'High risk', color: '#d2452c' },
  { key: 'medium', label: 'Medium risk', color: '#d68b1f' },
  { key: 'low', label: 'Low risk', color: '#1f9d6b' },
]

export default function MapLayers({ active, onToggle }) {
  return (
    <div className="map-layers">
      {LAYERS.map(l => (
        <label key={l.key} className="map-layer-item">
          <input type="checkbox" checked={active[l.key]} onChange={() => onToggle(l.key)} />
          <span className="dot" style={{ background: l.color }} />
          {l.label}
        </label>
      ))}
    </div>
  )
}
