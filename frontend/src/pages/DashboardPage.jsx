import { useState } from 'react'
import Dashboard from '../components/Dashboard'
import WeatherCard from '../components/WeatherCard'
import { stations } from '../services/stationData'

export default function DashboardPage() {
  const [selected, setSelected] = useState(stations[0])
  return (
    <div>
      <h2 className="title">Situation overview</h2>
      <p className="sub">Aggregated risk across {stations.length} monitored regions. Click a region for live weather.</p>
      <Dashboard selected={selected} onSelect={setSelected} />
      <div style={{ marginTop: '1rem' }}>
        <WeatherCard station={selected} />
      </div>
    </div>
  )
}
