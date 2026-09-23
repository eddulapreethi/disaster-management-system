import { stations } from './stationData'

// Client-side alert generation from current risk scores.
// (A real backend alerts/ service would push these instead of computing on read.)
export function getActiveAlerts() {
  return stations
    .filter(s => s.risk >= 45)
    .map(s => ({
      id: s.id,
      region: s.name,
      severity: s.risk >= 65 ? 'high' : 'medium',
      message:
        s.risk >= 65
          ? `High flood risk detected in ${s.name}. Rescue teams and shelters should be prepared.`
          : `Moderate flood risk in ${s.name}. Increase monitoring and brief response teams.`,
      riskScore: s.risk,
      issuedAt: new Date().toISOString(),
    }))
    .sort((a, b) => b.riskScore - a.riskScore)
}
