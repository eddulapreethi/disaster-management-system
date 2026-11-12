import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import { normalizeLocation } from './location'

const LocationContext = createContext(null)

export function LocationProvider({ children }) {
  const [selectedLocation, setSelectedLocationState] = useState(null)

  const setSelectedLocation = useCallback(location => {
    setSelectedLocationState(location == null ? null : normalizeLocation(location))
  }, [])

  const value = useMemo(
    () => ({ selectedLocation, setSelectedLocation }),
    [selectedLocation, setSelectedLocation],
  )

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>
}

export function useSelectedLocation() {
  const context = useContext(LocationContext)
  if (!context) {
    throw new Error('useSelectedLocation must be used within LocationProvider.')
  }
  return context
}
