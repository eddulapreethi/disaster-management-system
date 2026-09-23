import { useRef, useState } from 'react'
import { stations, riskBand } from '../services/stationData'

const QUICK = [
  "What's the current risk in Kochi?",
  'What resources should we prepare?',
  'Explain how predictions are made',
  'Which regions need evacuation planning?',
]

function botReply(q) {
  const t = q.toLowerCase()
  const found = stations.find(s => t.includes(s.name.toLowerCase()))
  if (found) {
    const band = riskBand(found.risk)
    return `${found.name} (${found.region}) is at a risk score of ${found.risk}/100 — ${band} concern. ${
      found.risk >= 65 ? 'Recommend pre-positioning rescue teams and preparing evacuation routes.'
      : found.risk >= 45 ? 'Recommend increased monitoring and briefing local response teams.'
      : 'Routine monitoring is sufficient right now.'}`
  }
  if (t.includes('resource') || t.includes('prepare'))
    return 'For regions above 65 risk: pre-position rescue boats, medical teams, and open shelters. For 45–64: stage equipment and brief response teams. See the Resources page for a per-region breakdown.'
  if (t.includes('evacu'))
    return `Regions currently needing evacuation planning: ${stations.filter(s => s.risk >= 65).map(s => s.name).join(', ') || 'none right now'}.`
  if (t.includes('explain') || t.includes('how') || t.includes('shap') || t.includes('predict'))
    return "Predictions come from an XGBoost model trained on a public flood-risk dataset. The Risk Prediction page shows each factor's real SHAP contribution."
  return 'I can help with regional risk levels, resource planning, evacuation timing, or how predictions work — try asking about a specific region.'
}

export default function Recommendations() {
  const highRisk = stations.filter(s => s.risk >= 45).sort((a, b) => b.risk - a.risk)
  const [messages, setMessages] = useState([
    { who: 'bot', text: "Ask me about regional risk levels, resource planning, or how a prediction was made." },
  ])
  const [input, setInput] = useState('')
  const logRef = useRef(null)

  function send(preset) {
    const text = preset || input.trim()
    if (!text) return
    setMessages(m => [...m, { who: 'user', text }])
    if (!preset) setInput('')
    setTimeout(() => {
      setMessages(m => [...m, { who: 'bot', text: botReply(text) }])
      requestAnimationFrame(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight })
    }, 300)
  }

  return (
    <div>
      <h2 className="title">AI emergency recommendations</h2>
      <p className="sub">Guidance generated from current risk levels. Ask the assistant for region-specific advice.</p>
      <div className="twocol">
        <div className="card">
          <div className="sectitle">Regions needing action</div>
          {highRisk.length === 0 && <div style={{ color: 'var(--ink2)', fontSize: '.85rem' }}>No regions currently above the advisory threshold.</div>}
          {highRisk.map(s => (
            <div className="detailbox" key={s.id} style={{ marginTop: '.7rem' }}>
              <h4>{s.name} <span className={`pill ${riskBand(s.risk) === 'medium' ? 'med' : riskBand(s.risk)}`}>{s.risk}</span></h4>
              <div className="reco">
                {s.risk >= 65
                  ? 'Pre-position rescue teams and medical supplies, alert low-lying settlements, prepare evacuation routes.'
                  : 'Increase monitoring frequency, brief local response teams, check drainage and flood barriers.'}
              </div>
            </div>
          ))}
        </div>

        <div className="chatwrap">
          <div className="chatlog" ref={logRef}>
            {messages.map((m, i) => <div key={i} className={`msg ${m.who}`}>{m.text}</div>)}
          </div>
          <div className="quickrow">{QUICK.map(q => <button key={q} className="qbtn" onClick={() => send(q)}>{q}</button>)}</div>
          <div className="chatinput">
            <input value={input} placeholder="Ask for recommendations…" onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
            <button className="btn" style={{ margin: 0 }} onClick={() => send()}>Send</button>
          </div>
        </div>
      </div>
    </div>
  )
}
