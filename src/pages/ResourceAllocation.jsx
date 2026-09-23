import { stations, riskBand } from '../services/stationData'

// Simple rule-based resource estimator: scales suggested units with risk score
// and exposed population. Replace with a real optimization service once
// resource-optimization/ exists on the backend.
function estimateResources(s) {
  const factor = s.risk / 100
  return {
    rescueBoats: Math.round(2 + factor * 18 * Math.sqrt(s.pop)),
    medicalTeams: Math.round(1 + factor * 6 * Math.sqrt(s.pop)),
    shelters: Math.round(1 + factor * 10 * Math.sqrt(s.pop)),
    reliefKits: Math.round((factor * s.pop * 1000) / 4),
  }
}

export default function ResourceAllocation() {
  const sorted = [...stations].sort((a, b) => b.risk - a.risk)
  return (
    <div>
      <h2 className="title">Resource allocation</h2>
      <p className="sub">Suggested emergency resource levels per region, scaled by risk score and exposed population.</p>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Region</th><th>Risk</th><th>Rescue boats</th><th>Medical teams</th><th>Shelters</th><th>Relief kits</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(s => {
              const r = estimateResources(s)
              return (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td><span className={`pill ${riskBand(s.risk) === 'medium' ? 'med' : riskBand(s.risk)}`}>{s.risk}</span></td>
                  <td>{r.rescueBoats}</td>
                  <td>{r.medicalTeams}</td>
                  <td>{r.shelters}</td>
                  <td>{r.reliefKits.toLocaleString()}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
