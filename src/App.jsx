import { useEffect, useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Navbar from './components/Navbar'
import Sidebar from './components/Sidebar'
import Home from './pages/Home'
import Login from './pages/Login'
import Register from './pages/Register'
import DashboardPage from './pages/DashboardPage'
import RiskPrediction from './pages/RiskPrediction'
import RiskMapPage from './pages/RiskMap'
import Simulation from './pages/Simulation'
import Recommendations from './pages/Recommendations'
import ResourceAllocation from './pages/ResourceAllocation'
import Alerts from './pages/Alerts'
import { isAuthenticated } from './services/authService'
import { checkBackend } from './services/api'

function ProtectedRoute({ children }) {
  return isAuthenticated() ? children : <Navigate to="/login" replace />
}

export default function App() {
  const [theme, setTheme] = useState(null)
  const [backendOnline, setBackendOnline] = useState(null)

  useEffect(() => {
    checkBackend().then(setBackendOnline)
    const interval = setInterval(() => checkBackend().then(setBackendOnline), 15000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (theme) document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  return (
    <BrowserRouter>
      <div className="app">
        <Navbar backendOnline={backendOnline} theme={theme} onToggleTheme={() => setTheme(t => (t === 'dark' ? 'light' : 'dark'))} />
        <div className="app-body">
          {isAuthenticated() && <Sidebar />}
          <main>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="/dashboard" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
              <Route path="/risk-prediction" element={<ProtectedRoute><RiskPrediction /></ProtectedRoute>} />
              <Route path="/risk-map" element={<ProtectedRoute><RiskMapPage /></ProtectedRoute>} />
              <Route path="/simulation" element={<ProtectedRoute><Simulation /></ProtectedRoute>} />
              <Route path="/recommendations" element={<ProtectedRoute><Recommendations /></ProtectedRoute>} />
              <Route path="/resource-allocation" element={<ProtectedRoute><ResourceAllocation /></ProtectedRoute>} />
              <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </main>
        </div>
        <footer>Connected to FastAPI backend at {import.meta.env.VITE_API_BASE || 'http://localhost:8000'} — falls back to an offline estimate if unreachable.</footer>
      </div>
    </BrowserRouter>
  )
}
