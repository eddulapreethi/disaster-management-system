import { useEffect, useState } from 'react'
import { predictRisk, ADJUSTABLE_FEATURES } from '../services/predictionService'
import { stations } from '../services/stationData'
import PredictionCard from '../components/PredictionCard'
import Loading from '../components/Loading'

const initial = Object.fromEntries(ADJUSTABLE_FEATURES.map(f => [f.key, 6]))

export default function RiskPrediction() {
  const [selected, setSelected] = useState(stations[0])
  const [values, setValues] = useState(initial)
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    const r = await predictRisk(values)
    setResult(r)
    setLoading(false)
  }

  useEffect(() => { run() }, []) // eslint-disable-line

  return (
    <div>
      <h2 className="title">Risk prediction</h2>
      <p className="sub">Adjust conditions and call the trained model's <code>/predict</code> endpoint for a live, explainable risk score.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Inputs</div>
          <label>Location</label>
          <select value={selected.id} onChange={e => setSelected(stations.find(s => s.id === e.target.value))}>
            {stations.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <div style={{ marginTop: '.8rem' }} className="formgrid">
            {ADJUSTABLE_FEATURES.map(f => (
              <div key={f.key}>
                <label>{f.label} <span className="rangeval">{values[f.key]}</span></label>
                <input type="range" min="0" max="16" value={values[f.key]} onChange={e => setValues(v => ({ ...v, [f.key]: +e.target.value }))} />
              </div>
            ))}
          </div>
          <button className="btn" onClick={run} disabled={loading}>{loading ? 'Running…' : 'Run prediction'}</button>
        </div>
        {loading && !result ? <div className="card"><Loading label="Running model…" /></div> : <PredictionCard result={result} title={`Prediction — ${selected.name}`} />}
      </div>
    </div>
  )
}
