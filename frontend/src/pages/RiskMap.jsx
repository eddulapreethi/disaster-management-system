import { useState } from 'react'
import RiskMapView from '../maps/RiskMap'
import { stations, riskBand } from '../services/stationData'

export default function RiskMapPage() {
  const [selected, setSelected] = useState(stations[0])
  const reco = (s) =>
    s.risk >= 65
      ? 'High risk: pre-position rescue teams and medical supplies, alert low-lying settlements, and prepare evacuation routes.'
      : s.risk >= 45
      ? 'Moderate risk: increase monitoring frequency, brief local response teams, and check drainage/flood barriers.'
      : 'Low risk: routine monitoring is sufficient; no special action required.'

  return (
    <div>
      <h2 className="title">Regional risk map</h2>
      <p className="sub">Live map of monitored regions. Click a marker for details and recommended actions.</p>
      <RiskMapView selected={selected} onSelect={setSelected} />
      {selected && (
        <div className="detailbox">
          <h4>{selected.name}</h4>
          <div style={{ color: 'var(--ink2)', fontSize: '.8rem', marginBottom: '.5rem' }}>{selected.region}</div>
          <div className="kv"><span>Risk score</span><span className={`pill ${riskBand(selected.risk) === 'medium' ? 'med' : riskBand(selected.risk)}`}>{selected.risk}/100</span></div>
          <div className="kv"><span>24h rainfall</span><span>{selected.rain} mm</span></div>
          <div className="kv"><span>River level</span><span>{selected.river}% of danger mark</span></div>
          <div className="kv"><span>Soil saturation</span><span>{selected.soil}%</span></div>
          <div className="kv"><span>Population exposed</span><span>{selected.pop}M</span></div>
          <div className="reco">{reco(selected)}</div>
        </div>
      )}
    </div>
  )
}
