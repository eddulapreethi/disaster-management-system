import { useEffect, useRef, useState } from 'react'
import Loading from './Loading'
import {
  createSatelliteRequestSequence,
  fetchSatelliteStatus,
  fetchSentinel2Scene,
  searchSentinel2Catalog,
} from '../services/satelliteService'

function dateString(date) {
  return date.toISOString().slice(0, 10)
}

function formatTimestamp(value) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? 'Unavailable' : parsed.toLocaleString()
}

function createDefaultDates() {
  const end = new Date()
  const start = new Date(end)
  start.setUTCDate(start.getUTCDate() - 30)
  return { startDate: dateString(start), endDate: dateString(end) }
}

export default function SatelliteSceneCard({ location }) {
  const defaults = createDefaultDates()
  const [startDate, setStartDate] = useState(defaults.startDate)
  const [endDate, setEndDate] = useState(defaults.endDate)
  const [scene, setScene] = useState(null)
  const [catalog, setCatalog] = useState(null)
  const [downloadUrl, setDownloadUrl] = useState(null)
  const [loading, setLoading] = useState('')
  const [catalogError, setCatalogError] = useState('')
  const [imageError, setImageError] = useState('')
  const [status, setStatus] = useState({
    authentication: 'NOT_CHECKED',
    catalogSearch: 'NOT_CHECKED',
    catalogResults: 'NOT_CHECKED',
    imagery: 'NOT_CHECKED',
  })
  const requestSequence = useRef(null)
  if (!requestSequence.current) requestSequence.current = createSatelliteRequestSequence()

  useEffect(() => {
    requestSequence.current.invalidate()
    setScene(null)
    setCatalog(null)
    setCatalogError('')
    setImageError('')
    setLoading('')
    setStatus({
      authentication: 'NOT_CHECKED',
      catalogSearch: 'NOT_CHECKED',
      catalogResults: 'NOT_CHECKED',
      imagery: 'NOT_CHECKED',
    })
    return () => requestSequence.current.invalidate()
  }, [location?.latitude, location?.longitude, startDate, endDate])

  useEffect(() => {
    if (!scene) {
      setDownloadUrl(null)
      return undefined
    }
    const url = URL.createObjectURL(scene.blob)
    setDownloadUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [scene])

  async function searchCatalog() {
    if (!location) return
    const requestId = requestSequence.current.next()
    let authenticationChecked = false
    setLoading('catalog')
    setScene(null)
    setCatalog(null)
    setCatalogError('')
    setImageError('')
    setStatus({
      authentication: 'CHECKING',
      catalogSearch: 'NOT_CHECKED',
      catalogResults: 'NOT_CHECKED',
      imagery: 'NOT_CHECKED',
    })
    try {
      const authentication = await fetchSatelliteStatus()
      if (!requestSequence.current.isCurrent(requestId)) return
      authenticationChecked = true
      setStatus(current => ({ ...current, authentication: authentication.authentication_status, catalogSearch: 'REQUESTED' }))
      const result = await searchSentinel2Catalog(location, { startDate, endDate })
      if (!requestSequence.current.isCurrent(requestId)) return
      setCatalog(result)
      setStatus({
        authentication: authentication.authentication_status,
        catalogSearch: result.catalog_search_status,
        catalogResults: result.catalog_results_status,
        imagery: result.imagery_status,
      })
    } catch (requestError) {
      if (!requestSequence.current.isCurrent(requestId)) return
      if (!authenticationChecked && requestError.status === 503) {
        setStatus(current => ({ ...current, authentication: 'UNAVAILABLE' }))
        setCatalogError(`Authentication is unavailable: ${requestError.message || 'Copernicus OAuth could not be checked.'}`)
      } else if (!authenticationChecked) {
        setStatus(current => ({ ...current, authentication: 'ERROR' }))
        setCatalogError(`Authentication check failed: ${requestError.message || 'Copernicus OAuth could not be checked.'}`)
      } else {
        setStatus(current => ({ ...current, catalogSearch: 'ERROR' }))
        setCatalogError(requestError.message || 'Sentinel-2 Catalog search could not be completed.')
      }
    } finally {
      if (requestSequence.current.isCurrent(requestId)) setLoading('')
    }
  }

  async function retrieveScene() {
    if (!location || !catalog?.features?.length || loading) return
    const requestId = requestSequence.current.next()
    setLoading('image')
    setScene(null)
    setImageError('')
    setStatus(current => ({ ...current, imagery: 'REQUESTED' }))
    try {
      const result = await fetchSentinel2Scene(location, { startDate, endDate, width: 64, height: 64 })
      if (requestSequence.current.isCurrent(requestId)) {
        setScene(result)
        setStatus(current => ({ ...current, imagery: result.metadata.imagery_status }))
      }
    } catch (requestError) {
      if (requestSequence.current.isCurrent(requestId)) {
        const statusValue = requestError.status === 404 ? 'UNAVAILABLE' : 'ERROR'
        setStatus(current => ({ ...current, imagery: statusValue }))
        setImageError(requestError.status === 404
          ? 'No usable Catalog scene was found for this retrieval query; no image was received.'
          : requestError.message || 'The image retrieval request failed; provider imagery was not confirmed.')
      }
    } finally {
      if (requestSequence.current.isCurrent(requestId)) setLoading('')
    }
  }

  if (!location) {
    return <section className="card" aria-label="Sentinel-2 scene retrieval">
      <div className="sectitle">Sentinel-2 scene retrieval</div>
      <p className="explain">Select a location before searching for satellite scenes.</p>
    </section>
  }

  return (
    <section className="card" aria-label="Sentinel-2 scene retrieval">
      <div className="sectitle">Sentinel-2 image retrieval</div>
      <p className="explain">
        Search for historical Sentinel-2 L2A Catalog metadata at this location, then optionally request a small image.
        This does not identify a hazard or confirm a flood extent.
      </p>
      <div className="formgrid">
        <label>
          Search start date
          <input className="text-input" type="date" value={startDate} onChange={event => setStartDate(event.target.value)} />
        </label>
        <label>
          Search end date
          <input className="text-input" type="date" value={endDate} onChange={event => setEndDate(event.target.value)} />
        </label>
      </div>
      <p className="explain">
        Coordinates: {location.latitude.toFixed(5)}, {location.longitude.toFixed(5)}. Output request: 64×64 pixels.
      </p>
      <button className="btn" type="button" onClick={searchCatalog} disabled={Boolean(loading)}>
        {loading === 'catalog' ? 'Checking authentication and searching Catalog…' : 'Search Sentinel-2 Catalog'}
      </button>
      {loading === 'catalog' && <Loading label="Checking OAuth, then searching the Catalog…" />}
      <div className="detailbox" aria-label="Satellite request status" aria-live="polite">
        <div className="kv"><span>OAuth authentication</span><span>{status.authentication}</span></div>
        <div className="kv"><span>Catalog search</span><span>{status.catalogSearch}</span></div>
        <div className="kv"><span>Catalog results</span><span>{status.catalogResults}</span></div>
        <div className="kv"><span>Image retrieval</span><span>{status.imagery}</span></div>
      </div>
      {catalogError && <p className="error" role="alert">Satellite status or Catalog request failed: {catalogError}</p>}
      {catalog && (
        <div className="detailbox">
          <div className="sectitle">Catalog metadata · {catalog.features.length} result(s)</div>
          {catalog.features.length === 0 && <p className="explain">No Catalog results matched this request. This does not indicate the absence of a hazard.</p>}
          {catalog.features.slice(0, 5).map((feature, index) => (
            <div className="kv" key={feature.id || `catalog-result-${index}`}>
              <span>{feature.id || 'Catalog item ID unavailable'}<small className="explain" style={{ display: 'block' }}>Acquired {formatTimestamp(feature.acquisition_time || feature.sensing_time)}</small></span>
              <span>
                {feature.cloud_coverage == null ? 'Cloud cover unavailable' : `${feature.cloud_coverage}% cloud`}
                {feature.canonical_record && (
                  <small className="explain" style={{ display: 'block' }}>
                    Canonical: {feature.canonical_record.quality_status} · not live-verified
                  </small>
                )}
              </span>
            </div>
          ))}
          {catalog.features.length > 0 && <p className="explain">Scene metadata is not imagery. A later image request performs its own time/AOI selection and is not guaranteed to use any displayed Catalog item.</p>}
        </div>
      )}
      {catalog?.features?.length > 0 && (
        <button className="btn" type="button" onClick={retrieveScene} disabled={Boolean(loading)}>
          {loading === 'image' ? 'Requesting image…' : 'Request 64×64 image'}
        </button>
      )}
      {loading === 'image' && <Loading label="Requesting a bounded TIFF after a separate Catalog search…" />}
      {imageError && <p className="error" role="alert">Image not retrieved: {imageError}</p>}
      {!catalog && !catalogError && !loading && <p className="explain" role="status">Catalog and imagery have not been checked.</p>}
      {scene && (
        <div aria-live="polite">
          <div className="kv"><span>Catalog item reference</span><span>{scene.metadata.source_record_id || 'Unavailable'}</span></div>
          <div className="kv"><span>Satellite collection</span><span>{scene.metadata.product || 'Unavailable'}</span></div>
          <div className="kv"><span>Requested AOI (west, south, east, north)</span><span>{scene.metadata.requested_bbox?.join(', ') || 'Unavailable'}</span></div>
          <div className="kv"><span>Acquisition time</span><span>{formatTimestamp(scene.metadata.acquisition_time)}</span></div>
          <div className="kv"><span>Catalog fetched</span><span>{formatTimestamp(scene.metadata.catalog_fetched_at)}</span></div>
          <div className="kv"><span>Process request time</span><span>{formatTimestamp(scene.metadata.process_requested_at)}</span></div>
          <div className="kv"><span>Image received</span><span>{formatTimestamp(scene.metadata.downloaded_at)}</span></div>
          <div className="kv"><span>Scene cloud coverage</span><span>{scene.metadata.cloud_coverage == null ? 'Unavailable' : `${scene.metadata.cloud_coverage}%`}</span></div>
          <div className="kv"><span>Freshness</span><span>{scene.metadata.freshness_status || 'UNVERIFIED'}</span></div>
          <div className="kv"><span>Scene match</span><span>{scene.metadata.scene_match_status || 'UNVERIFIED'}</span></div>
          <div className="kv"><span>Image format and size</span><span>{scene.metadata.format || 'image/tiff'}, {scene.metadata.width}×{scene.metadata.height}</span></div>
          {scene.metadata.canonical_record && (
            <div className="kv">
              <span>Canonical contract</span>
              <span>
                v{scene.metadata.canonical_record.contract_version}
                {' · '}{scene.metadata.canonical_record.quality_status}
                {' · '}
                {scene.metadata.canonical_record.payload?.process_result_pinned_to_catalog_item
                  ? 'Catalog item pinned'
                  : 'Catalog item not pinned'}
              </span>
            </div>
          )}
          <p className="explain">
            Acquisition is the Catalog scene time; retrieval timestamps describe this request. The Process API
            selects by area and time and may stitch inputs; this image is not guaranteed to originate from the
            displayed Catalog item.
          </p>
          <a className="btn" href={downloadUrl || undefined} download="sentinel-2-scene.tiff">Download TIFF (not previewed)</a>
        </div>
      )}
    </section>
  )
}
