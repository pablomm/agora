import { Map as MaplibreMap, setWorkerUrl, type ExpressionSpecification } from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useEffect, useRef } from 'react'
import { config } from '../app/config'
import type { BoundaryLayer } from '../app/settings'
import { useTheme } from '../app/theme'
import { choroplethColor, type Palette } from '../map/boundaries'

setWorkerUrl(workerUrl)

type Bounds = [number, number, number, number]

interface Props {
  /** The vector tile layer to draw (its source layer has the same name). */
  layer: string
  /** What to show: [west, south, east, north]. */
  bounds: Bounds
  /** Painted by value (a statistical dataset's variable); otherwise the geometries in the accent color. */
  choropleth?: { values: Record<string, number>; breaks: number[]; palette: Palette }
  label: string
}

/** Below this zoom a layer has no tiles to draw, or too many: the map starts at least there. */
const minZoom = (layer: string) => (config.boundaries.fixedMinZoom as Partial<Record<string, number>>)[layer as BoundaryLayer] ?? config.map.minZoom

/**
 * A small, static map of a dataset: its geometries from the map's own tiles, over the basemap of
 * the theme, fitted to its bounds (centred on them, closer in, for layers only drawn up close).
 */
export function DatasetMap({ layer, bounds, choropleth, label }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const theme = useTheme()

  useEffect(() => {
    if (!container.current) return
    const [west, south, east, north] = bounds
    const map = new MaplibreMap({
      container: container.current,
      style: theme === 'dark' ? config.map.darkStyleUrl : config.map.styleUrl,
      bounds: [
        [west, south],
        [east, north],
      ],
      fitBoundsOptions: { padding: 12 },
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      cooperativeGestures: true,
    })
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#2563eb'
    // The page lays out after the map is made: it follows its container's size.
    const resize = new ResizeObserver(() => map.resize())
    resize.observe(container.current)
    // The attribution starts folded (its button unfolds it): unfolded, it covers a small map.
    map.once('idle', () => map.getContainer().querySelector('.maplibregl-compact-show')?.classList.remove('maplibregl-compact-show'))
    map.on('load', () => {
      if (map.getZoom() < minZoom(layer)) map.jumpTo({ center: [(west + east) / 2, (south + north) / 2], zoom: minZoom(layer) + 0.5 })
      map.addSource('dataset', { type: 'vector', url: `${config.tiles.url}/${layer}`, promoteId: 'id' })
      // Under the basemap's labels.
      const labels = map.getStyle().layers.find((item) => item.type === 'symbol')?.id
      const fill: ExpressionSpecification | string = choropleth
        ? ([
            'match',
            ['get', 'id'],
            ...Object.entries(choropleth.values).flatMap(([id, value]) => [id, choroplethColor(value, choropleth.breaks, theme, choropleth.palette)]),
            'rgba(0, 0, 0, 0)',
          ] as unknown as ExpressionSpecification)
        : accent
      map.addLayer(
        { id: 'dataset-fill', type: 'fill', source: 'dataset', 'source-layer': layer, paint: { 'fill-color': fill, 'fill-opacity': choropleth ? 0.9 : 0.22 } },
        labels,
      )
      map.addLayer(
        {
          id: 'dataset-line',
          type: 'line',
          source: 'dataset',
          'source-layer': layer,
          paint: { 'line-color': choropleth ? (theme === 'dark' ? '#16191c' : '#ffffff') : accent, 'line-width': 0.6, 'line-opacity': 0.8 },
        },
        labels,
      )
    })
    return () => {
      resize.disconnect()
      map.remove()
    }
  }, [layer, bounds, choropleth, theme])

  return <div ref={container} className="dataset-map" role="img" aria-label={label} />
}
