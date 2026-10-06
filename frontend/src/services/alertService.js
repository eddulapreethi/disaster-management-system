import { apiGet } from './api'

export async function getActiveAlerts() {
  const alerts = await apiGet('/alerts')
  return alerts.map(alert => ({
    id: alert.id,
    region: alert.title,
    severity: alert.severity === 'moderate' ? 'medium' : alert.severity,
    message: alert.message,
    issuedAt: alert.created_at,
  }))
}
