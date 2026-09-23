// Regional monitoring stations. Coordinates are approximate and used to position
// markers on the map; risk figures are illustrative starting values — Risk
// Prediction and Simulation pages call the live backend for real scores.
export const stations = [
  { id: 'kochi', name: 'Kochi', region: 'Kerala coast', lat: 9.9312, lng: 76.2673, risk: 78, rain: 210, river: 82, soil: 74, pop: 2.1 },
  { id: 'wayanad', name: 'Wayanad', region: 'Western Ghats', lat: 11.6854, lng: 76.1320, risk: 66, rain: 170, river: 58, soil: 81, pop: 0.8 },
  { id: 'guwahati', name: 'Guwahati', region: 'Brahmaputra basin', lat: 26.1445, lng: 91.7362, risk: 71, rain: 190, river: 75, soil: 69, pop: 1.1 },
  { id: 'kolkata', name: 'Kolkata', region: 'Ganga delta', lat: 22.5726, lng: 88.3639, risk: 58, rain: 140, river: 63, soil: 60, pop: 4.5 },
  { id: 'mumbai', name: 'Mumbai', region: 'Konkan coast', lat: 19.0760, lng: 72.8777, risk: 52, rain: 120, river: 48, soil: 55, pop: 12.4 },
  { id: 'chennai', name: 'Chennai', region: 'Coromandel coast', lat: 13.0827, lng: 80.2707, risk: 44, rain: 95, river: 40, soil: 47, pop: 7.1 },
  { id: 'srinagar', name: 'Srinagar', region: 'Jhelum valley', lat: 34.0837, lng: 74.7973, risk: 35, rain: 60, river: 33, soil: 38, pop: 1.2 },
  { id: 'dehradun', name: 'Dehradun', region: 'Himalayan foothills', lat: 30.3165, lng: 78.0322, risk: 61, rain: 155, river: 52, soil: 66, pop: 0.7 },
]

export function riskBand(v) {
  return v >= 65 ? 'high' : v >= 45 ? 'medium' : 'low'
}

export function riskColor(v) {
  return v >= 65 ? '#d2452c' : v >= 45 ? '#d68b1f' : '#1f9d6b'
}
