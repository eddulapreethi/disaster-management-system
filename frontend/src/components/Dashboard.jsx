import { stations, riskBand } from '../services/stationData'
import RiskCard from './RiskCard'

export default function Dashboard({ selected, onSelect }) {
  const avg = Math.round(stations.reduce((a, s) => a + s.risk, 0) / stations.length)
  const highCount = stations.filter(s => s.risk >= 65).length
  const top = [...stations].sort((a, b) => b.risk - a.risk)[0]

  return (
    <div>
      <div className="grid cards4">
        <div className="card stat">
          <div className="label">National risk index</div>
          <div className="num">{avg}<span style={{ fontSize: '1rem', color: 'var(--ink2)' }}>/100</span></div>
          <div className={`delta pill ${riskBand(avg) === 'medium' ? 'med' : riskBand(avg)}`}>{riskBand(avg)} concern</div>
        </div>
        <div className="card stat">
          <div className="label">Regions at high risk</div>
          <div className="num">{highCount}</div>
          <div className="delta" style={{ color: 'var(--ink2)' }}>of {stations.length} monitored</div>
        </div>
        <div className="card stat">
          <div className="label">Active stations</div>
          <div className="num">{stations.length}</div>
          <div className="delta" style={{ color: 'var(--ink2)' }}>reporting normally</div>
        </div>
        <div className="card stat">
          <div className="label">Highest priority</div>
          <div className="num" style={{ fontSize: '1.15rem', fontFamily: 'Space Grotesk' }}>{top.name}</div>
          <div className={`delta pill ${riskBand(top.risk) === 'medium' ? 'med' : riskBand(top.risk)}`}>score {top.risk}</div>
        </div>
      </div>

      <div className="sectitle" style={{ marginTop: '1.2rem' }}>Monitored regions</div>
      <div className="riskcard-grid">
        {stations.map(s => (
          <RiskCard key={s.id} station={s} selected={selected?.id === s.id} onClick={() => onSelect(s)} />
        ))}
      </div>
    </div>
  )
}
