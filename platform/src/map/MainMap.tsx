import { Map as MaplibreMap, setWorkerUrl, type StyleSpecification } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef, useState } from 'react'
import { config } from '../app/config'
import { copy } from '../app/copy'
import type { BoundaryMode, Settings } from '../app/settings'
import { useTheme, type Theme } from '../app/theme'
import {
  applyBoundaryMode,
  isBoundarySource,
  markSelected,
  minZoomFor,
  trackBoundaryClicks,
  trackBoundaryHover,
  withBoundaries,
  type SelectedUnit,
} from './boundaries'

// MapLibre looks for its worker next to its own bundle, which Vite relocates; let Vite bundle it instead.
setWorkerUrl(workerUrl)

type BasemapStyle = Theme | 'satellite'

const satelliteStyle: StyleSpecification = {
  version: 8,
  sources: {
    pnoa: {
      type: 'raster',
      tiles: [config.map.satellite.tileUrl],
      tileSize: 256,
      maxzoom: config.map.maxZoom,
      attribution: config.map.satellite.attribution,
    },
  },
  layers: [{ id: 'pnoa', type: 'raster', source: 'pnoa' }],
}

const styles: Record<BasemapStyle, string | StyleSpecification> = {
  light: config.map.styleUrl,
  dark: config.map.darkStyleUrl,
  satellite: satelliteStyle,
}

/** Labels drawn from OpenMapTiles' road names layer (names and shields, in any style using that schema). */
function showStreetNames(map: MaplibreMap, visible: boolean) {
  for (const layer of map.getStyle()?.layers ?? []) {
    if ('source-layer' in layer && layer['source-layer'] === 'transportation_name') {
      map.setLayoutProperty(layer.id, 'visibility', visible ? 'visible' : 'none')
    }
  }
}

interface Props {
  settings: Settings
  /** The unit open in the detail panel, highlighted on the map. */
  selected: SelectedUnit | undefined
  /** A unit clicked on the map, or undefined after a click on no unit. */
  onSelect: (unit: SelectedUnit | undefined) => void
  /** The map once created (again after a remount), for the controls drawn around it. */
  onReady: (map: MaplibreMap) => void
}

/** Loads a basemap style with the boundary layers added to it (see map/boundaries.ts). */
function loadStyle(map: MaplibreMap, basemapStyle: BasemapStyle, boundaries: BoundaryMode) {
  map.setStyle(styles[basemapStyle], { transformStyle: (_, next) => withBoundaries(next, boundaries, basemapStyle) })
}

/**
 * The full-size MapLibre map: basemap by theme or the orthophoto, the street names switch, and the
 * administrative boundaries from the tile server.
 */
export function MainMap({ settings, selected, onSelect, onReady }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MaplibreMap | null>(null)
  const theme = useTheme()
  const basemapStyle: BasemapStyle = settings.basemap === 'satellite' ? 'satellite' : theme
  // Read when the map is created, so a style change doesn't rebuild it (see the effects below).
  const initialStyle = useRef(basemapStyle)
  const streetNamesRef = useRef(settings.streetNames)
  const boundariesRef = useRef(settings.boundaries)
  const selectedRef = useRef(selected)
  const onSelectRef = useRef(onSelect)
  const [failed, setFailed] = useState(false)
  const [boundariesFailed, setBoundariesFailed] = useState(false)

  useEffect(() => {
    const map = new MaplibreMap({
      container: container.current!,
      bounds: config.map.initialBounds,
      fitBoundsOptions: { padding: 40 },
      minZoom: minZoomFor(boundariesRef.current),
      maxZoom: config.map.maxZoom,
      attributionControl: { compact: true },
    })
    loadStyle(map, initialStyle.current, boundariesRef.current)
    // Every style load (first one, theme or basemap swaps) starts with all labels: reapply the choice.
    map.on('styledata', () => showStreetNames(map, streetNamesRef.current))
    // The tile server failing isn't the basemap failing: each has its own message.
    map.on('error', (event) => {
      const source = 'sourceId' in event ? String(event.sourceId) : undefined
      if (isBoundarySource(source)) setBoundariesFailed(true)
      else setFailed(true)
    })
    map.on('data', (event) => {
      if (event.dataType !== 'source' || !('tile' in event && event.tile)) return
      if (isBoundarySource(event.sourceId)) setBoundariesFailed(false)
      else setFailed(false)
    })
    const stopHover = trackBoundaryHover(map)
    const stopClicks = trackBoundaryClicks(map, (unit) => onSelectRef.current(unit))
    // A new style brings new sources, without the selection's highlight: mark it again.
    map.on('style.load', () => markSelected(map, selectedRef.current, true))
    mapRef.current = map
    onReady(map)
    return () => {
      stopHover()
      stopClicks()
      map.remove()
      mapRef.current = null
    }
  }, [onReady])

  // Theme or basemap: swap the style in place (MapLibre diffs styles that share their sources).
  useEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  // The selection's highlight follows the selected unit.
  useEffect(() => {
    const map = mapRef.current
    selectedRef.current = selected
    if (!map) return
    markSelected(map, selected, true)
    return () => markSelected(map, selected, false)
  }, [selected])

  useEffect(() => {
    if (basemapStyle === initialStyle.current) return
    initialStyle.current = basemapStyle
    if (mapRef.current) loadStyle(mapRef.current, basemapStyle, boundariesRef.current)
  }, [basemapStyle])

  useEffect(() => {
    boundariesRef.current = settings.boundaries
    if (!mapRef.current) return
    applyBoundaryMode(mapRef.current, settings.boundaries)
    // Zoomed out further than the layer allows: the map zooms in to its minimum.
    mapRef.current.setMinZoom(minZoomFor(settings.boundaries))
  }, [settings.boundaries])

  useEffect(() => {
    streetNamesRef.current = settings.streetNames
    const map = mapRef.current
    if (map?.isStyleLoaded()) showStreetNames(map, settings.streetNames)
  }, [settings.streetNames])

  return (
    <>
      <div ref={container} className="main-map" />
      {(failed || boundariesFailed) && (
        <div className="tile-error" role="status">
          {failed ? copy.tileError : copy.boundariesError}
        </div>
      )}
    </>
  )
}
