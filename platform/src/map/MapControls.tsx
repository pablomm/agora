import { Marker, type Map as MaplibreMap } from 'maplibre-gl'
import { useEffect, useRef, useState } from 'react'
import { config } from '../app/config'
import { copy } from '../app/copy'

/**
 * The map's own buttons, under the settings in the top-right corner: full screen, zoom and my location.
 * Drawn by React instead of MapLibre's controls so they share the floating buttons' look.
 */
export function MapControls({ map, minZoom }: { map: MaplibreMap; minZoom: number }) {
  return (
    <div className="map-controls">
      <FullscreenButton />
      <ZoomButtons map={map} minZoom={minZoom} />
      <LocateButton map={map} />
    </div>
  )
}

const isFullscreen = () => document.fullscreenElement !== null

/** The whole page goes full screen. Browsers without the Fullscreen API for pages (Safari on iPhone) don't show it. */
function FullscreenButton() {
  const [active, setActive] = useState(isFullscreen)

  useEffect(() => {
    // Also covers leaving with Escape or the browser's own controls.
    const onChange = () => setActive(isFullscreen())
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  if (!document.fullscreenEnabled) return null
  const label = active ? copy.controls.fullscreen.exit : copy.controls.fullscreen.enter

  return (
    <button
      type="button"
      className="tool-button"
      aria-label={label}
      title={label}
      aria-pressed={active}
      onClick={() => (active ? document.exitFullscreen() : document.documentElement.requestFullscreen()).catch(() => {})}
    >
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
        <path
          d={active ? 'M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5' : 'M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5'}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </button>
  )
}

/**
 * Zoom in and out, one above the other in a single card; each is disabled at its limit. The minimum
 * comes from the boundary mode (a fixed layer raises it), as a prop so it's right on the render
 * that changes it, before the map applies it.
 */
function ZoomButtons({ map, minZoom }: { map: MaplibreMap; minZoom: number }) {
  const [zoom, setZoom] = useState(() => map.getZoom())

  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom())
    map.on('zoomend', onZoom)
    return () => {
      map.off('zoomend', onZoom)
    }
  }, [map])

  return (
    <div className="tool-group" role="group">
      <button
        type="button"
        aria-label={copy.controls.zoomIn}
        title={copy.controls.zoomIn}
        disabled={zoom >= map.getMaxZoom()}
        onClick={() => map.zoomIn()}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      <button
        type="button"
        aria-label={copy.controls.zoomOut}
        title={copy.controls.zoomOut}
        disabled={zoom <= minZoom}
        onClick={() => map.zoomOut()}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <path d="M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  )
}

type LocateStatus = 'idle' | 'locating' | 'denied' | 'unavailable'

/** How long a message next to the button stays. */
const MESSAGE_MS = 4000

/**
 * Asks the browser once for the device position, flies there and marks it with a dot.
 * Without the Geolocation API it isn't shown.
 */
function LocateButton({ map }: { map: MaplibreMap }) {
  const [status, setStatus] = useState<LocateStatus>('idle')
  const marker = useRef<Marker | null>(null)

  useEffect(() => {
    if (status !== 'denied' && status !== 'unavailable') return
    const timer = setTimeout(() => setStatus('idle'), MESSAGE_MS)
    return () => clearTimeout(timer)
  }, [status])

  // The dot belongs to this map: gone with it (or with a new one).
  useEffect(
    () => () => {
      marker.current?.remove()
      marker.current = null
    },
    [map],
  )

  if (!('geolocation' in navigator)) return null

  const locate = () => {
    setStatus('locating')
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setStatus('idle')
        const here: [number, number] = [coords.longitude, coords.latitude]
        if (!marker.current) {
          const element = document.createElement('div')
          element.className = 'location-dot'
          marker.current = new Marker({ element })
        }
        marker.current.setLngLat(here).addTo(map)
        map.flyTo({ center: here, zoom: Math.max(map.getZoom(), config.map.locateZoom), duration: 800 })
      },
      (error) => setStatus(error.code === error.PERMISSION_DENIED ? 'denied' : 'unavailable'),
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 30_000 },
    )
  }

  const message = status === 'denied' || status === 'unavailable' ? copy.locate[status] : undefined

  return (
    <div className="locate-control">
      <button
        type="button"
        className={`tool-button${status === 'locating' ? ' is-locating' : ''}`}
        aria-label={copy.locate.label}
        title={copy.locate.label}
        aria-busy={status === 'locating'}
        onClick={locate}
      >
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
          <circle cx="12" cy="12" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <circle cx="12" cy="12" r="2.2" fill="currentColor" />
          <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      <span className="locate-message" role="status">
        {message}
      </span>
    </div>
  )
}
