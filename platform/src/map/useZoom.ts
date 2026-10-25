import type { Map as MaplibreMap } from 'maplibre-gl'
import { useEffect, useState } from 'react'

/** The map's zoom, updated when a zoom ends. */
export function useZoom(map: MaplibreMap | undefined) {
  const [zoom, setZoom] = useState(() => map?.getZoom())
  useEffect(() => {
    if (!map) return
    const update = () => setZoom(map.getZoom())
    update()
    map.on('zoomend', update)
    return () => {
      map.off('zoomend', update)
    }
  }, [map])
  return zoom
}
