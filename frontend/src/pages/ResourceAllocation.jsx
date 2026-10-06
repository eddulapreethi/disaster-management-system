import { useEffect, useState } from 'react'
import { apiGet, apiPost } from '../services/api'

const EMPTY_RESOURCE = {
  name: '', resource_type: 'water', quantity: '', unit: 'litres', latitude: '', longitude: '',
}
const EMPTY_DEMAND = {
  resource_type: 'water', quantity: '', unit: 'litres', latitude: '', longitude: '', priority_score: 50,
}

export default function ResourceAllocation() {
  const [resources, setResources] = useState([])
  const [resourceForm, setResourceForm] = useState(EMPTY_RESOURCE)
  const [demand, setDemand] = useState(EMPTY_DEMAND)
  const [plan, setPlan] = useState(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function refreshResources() {
    const rows = await apiGet('/resources')
    setResources(rows)
  }

  useEffect(() => {
    let active = true
    apiGet('/resources')
      .then(rows => { if (active) setResources(rows) })
      .catch(requestError => { if (active) setError(requestError.message || 'Could not load inventory.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  async function addResource(event) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      await apiPost('/resources', {
        ...resourceForm,
        quantity: Number(resourceForm.quantity),
        latitude: Number(resourceForm.latitude),
        longitude: Number(resourceForm.longitude),
      })
      setResourceForm(EMPTY_RESOURCE)
      await refreshResources()
    } catch (requestError) {
      setError(requestError.message || 'Could not add inventory.')
    } finally {
      setSaving(false)
    }
  }

  async function allocateDemand(event) {
    event.preventDefault()
    setError('')
    setSaving(true)
    try {
      const response = await apiPost('/resources/plan', {
        demands: [{
          id: 'current-request',
          ...demand,
          quantity: Number(demand.quantity),
          latitude: Number(demand.latitude),
          longitude: Number(demand.longitude),
          priority_score: Number(demand.priority_score),
        }],
      })
      setPlan(response)
      await refreshResources()
    } catch (requestError) {
      setError(requestError.message || 'Could not plan resource allocation.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <h2 className="title">Resource allocation</h2>
      <p className="sub">Plan requested supplies against saved inventory. Allocation prioritizes demand and nearby available depots.</p>
      {error && <div className="card" role="alert">{error}</div>}
      <div className="twocol">
        <form className="card" onSubmit={allocateDemand}>
          <div className="sectitle">Plan a demand</div>
          <label>Resource type</label>
          <input className="text-input" required value={demand.resource_type} onChange={event => setDemand(value => ({ ...value, resource_type: event.target.value }))} />
          <div className="formgrid">
            <div><label>Quantity</label><input className="text-input" required type="number" min="1" value={demand.quantity} onChange={event => setDemand(value => ({ ...value, quantity: event.target.value }))} /></div>
            <div><label>Unit</label><input className="text-input" value={demand.unit} onChange={event => setDemand(value => ({ ...value, unit: event.target.value }))} /></div>
            <div><label>Latitude</label><input className="text-input" required type="number" step="any" min="-90" max="90" value={demand.latitude} onChange={event => setDemand(value => ({ ...value, latitude: event.target.value }))} /></div>
            <div><label>Longitude</label><input className="text-input" required type="number" step="any" min="-180" max="180" value={demand.longitude} onChange={event => setDemand(value => ({ ...value, longitude: event.target.value }))} /></div>
          </div>
          <label>Priority score (0-100) <span className="rangeval">{demand.priority_score}</span></label>
          <input type="range" min="0" max="100" value={demand.priority_score} onChange={event => setDemand(value => ({ ...value, priority_score: event.target.value }))} />
          <button className="btn" type="submit" disabled={saving}>{saving ? 'Planning...' : 'Plan and reserve stock'}</button>
        </form>

        <form className="card" onSubmit={addResource}>
          <div className="sectitle">Add inventory</div>
          <label>Resource name</label>
          <input className="text-input" required value={resourceForm.name} onChange={event => setResourceForm(value => ({ ...value, name: event.target.value }))} />
          <div className="formgrid">
            <div><label>Type</label><input className="text-input" required value={resourceForm.resource_type} onChange={event => setResourceForm(value => ({ ...value, resource_type: event.target.value }))} /></div>
            <div><label>Quantity</label><input className="text-input" required type="number" min="0" value={resourceForm.quantity} onChange={event => setResourceForm(value => ({ ...value, quantity: event.target.value }))} /></div>
            <div><label>Unit</label><input className="text-input" required value={resourceForm.unit} onChange={event => setResourceForm(value => ({ ...value, unit: event.target.value }))} /></div>
            <div><label>Latitude</label><input className="text-input" required type="number" step="any" min="-90" max="90" value={resourceForm.latitude} onChange={event => setResourceForm(value => ({ ...value, latitude: event.target.value }))} /></div>
            <div><label>Longitude</label><input className="text-input" required type="number" step="any" min="-180" max="180" value={resourceForm.longitude} onChange={event => setResourceForm(value => ({ ...value, longitude: event.target.value }))} /></div>
          </div>
          <button className="btn" type="submit" disabled={saving}>{saving ? 'Saving...' : 'Add to inventory'}</button>
        </form>
      </div>
      {plan && (
        <div className="card">
          <div className="sectitle">Allocation plan</div>
          {plan.allocations.map(item => (
            <div className="detailbox" key={item.demand_id}>
              <div className="kv"><span>{item.resource_type}: {item.allocated}/{item.requested} {item.sources[0]?.unit || demand.unit}</span><span>Shortage: {item.shortage}</span></div>
              {item.sources.map(source => <div className="kv" key={source.resource_id}><span>{source.name}</span><span>{source.quantity} {source.unit}, {source.distance_km} km</span></div>)}
              {item.pickup_route?.stops.length > 0 && <p className="explain">Suggested pickup order: {item.pickup_route.stops.map(stop => stop.name).join(' -> ')} ({item.pickup_route.total_distance_km} km straight-line estimate).</p>}
            </div>
          ))}
          <p className="explain">{plan.note}</p>
        </div>
      )}
      <div className="card">
        <div className="sectitle">Saved inventory</div>
        {loading && <p>Loading inventory...</p>}
        {!loading && resources.length === 0 && <p>No inventory records yet. Add a resource above.</p>}
        <table>
          <thead>
            <tr>
              <th>Name</th><th>Type</th><th>Quantity</th><th>Location</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {resources.map(resource => <tr key={resource.id}><td>{resource.name}</td><td>{resource.resource_type}</td><td>{resource.quantity} {resource.unit}</td><td>{resource.latitude}, {resource.longitude}</td><td>{resource.status}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  )
}
