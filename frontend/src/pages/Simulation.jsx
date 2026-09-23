import { useEffect, useState } from 'react'
import { predictRisk } from '../services/predictionService'
import { stations, riskColor } from '../services/stationData'

export default function Simulation() {
  const [selected, setSelected] = useState(stations[0])
  const [rainBoost, setRainBoost] = useState(0)
  const [drainageDrop, setDrainageDrop] = useState(0)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    const monsoon = Math.min(16, 6 + Math.round(rainBoost / 25))
    const drainage = Math.max(0, 10 - Math.round(drainageDrop / 2))
    const r = await predictRisk({ MonsoonIntensity: monsoon, DrainageSystems: drainage })
    setResult(r)
    setLoading(false)
  }

  useEffect(() => { run() }, [rainBoost, drainageDrop, selected]) // eslint-disable-line

  const affected = result ? (selected.pop * (result.risk_score / 100) * 0.6).toFixed(2) : '—'
  const evacHrs = result ? Math.max(2, Math.round(24 - (result.risk_score / 100) * 18)) : '—'

  return (
    <div>
      <h2 className="title">Digital twin simulation</h2>
      <p className="sub">Simulate changing conditions and see the model's projected impact update live.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Scenario controls</div>
          <label>Location</label>
          <select value={selected.id} onChange={e => setSelected(stations.find(s => s.id === e.target.value))}>
            {stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <label style={{ marginTop: '.8rem' }}>Rainfall increase (mm above baseline) <span className="rangeval">{rainBoost}</span></label>
          <input type="range" min="0" max="250" value={rainBoost} onChange={e => setRainBoost(+e.target.value)} />
          <label style={{ marginTop: '.8rem' }}>Drainage degradation (%) <span className="rangeval">{drainageDrop}</span></label>
          <input type="range" min="0" max="20" value={drainageDrop} onChange={e => setDrainageDrop(+e.target.value)} />
        </div>
        <div className="card">
          {result && (
            <>
              <div className="sectitle">Projected impact {loading && '(updating…)'}</div>
              <div className="kv"><span>Baseline risk → simulated risk</span>
                <span className="mono">{selected.risk} → <b style={{ color: riskColor(result.risk_score) }}>{Math.round(result.risk_score)}</b></span>
              </div>
              <div className="kv"><span>Rainfall scenario</span><span>+{rainBoost} mm above baseline</span></div>
              <div className="kv"><span>Drainage scenario</span><span>-{drainageDrop}% capacity</span></div>
              <div className="kv"><span>Estimated population affected</span><span>{affected}M</span></div>
              <div className="kv"><span>Recommended evacuation window</span><span>{evacHrs} hours</span></div>
              <div className="reco">
                {result.risk_score >= 65
                  ? 'Trigger evacuation protocol for low-lying zones and open designated shelters.'
                  : result.risk_score >= 45
                  ? 'Issue advisory, stage rescue equipment near the region.'
                  : 'Continue routine monitoring.'}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
