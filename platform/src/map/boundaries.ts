import {
  Popup,
  type DataDrivenPropertyValueSpecification,
  type FeatureIdentifier,
  type LayerSpecification,
  type Map as MaplibreMap,
  type MapMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import { config } from '../app/config'
import { copy } from '../app/copy'
import { boundaryLayers, boundaryLevels, boundaryOverlays, type BoundaryLayer, type BoundaryLevel, type BoundaryMode, type BoundaryOverlay } from '../app/settings'

/** Basemap under the boundaries, which decides their colours. */
export type BoundaryBasemap = 'light' | 'dark' | 'satellite'

/** Above any zoom the map reaches: a layer with this max zoom never hides by zoom. */
const NO_MAX_ZOOM = 24

const sourceId = (layer: BoundaryLayer) => `boundaries-${layer}`
const fillId = (layer: BoundaryLayer) => `boundaries-${layer}-fill`
const lineId = (layer: BoundaryLayer) => `boundaries-${layer}-line`

export const isBoundarySource = (id: string | undefined) => !!id && boundaryLayers.some((layer) => sourceId(layer) === id)

/** The levels drawn as context lines over a fixed overlay. */
const overlayContext: Record<BoundaryOverlay, BoundaryLevel[]> = {
  rural_polygons: ['autonomous_communities', 'provinces', 'municipalities'],
  postal_codes: ['autonomous_communities', 'provinces'],
}

// Coarser levels draw thicker, so communities stand out over provinces, and provinces over municipalities.
const lineWidths: Record<BoundaryLayer, DataDrivenPropertyValueSpecification<number>> = {
  autonomous_communities: ['interpolate', ['linear'], ['zoom'], 4, 1.2, 10, 2.6],
  provinces: ['interpolate', ['linear'], ['zoom'], 4, 0.7, 10, 1.6],
  municipalities: ['interpolate', ['linear'], ['zoom'], 6, 0.25, 12, 1],
  census_districts: ['interpolate', ['linear'], ['zoom'], 8, 0.2, 14, 0.9],
  census_sections: ['interpolate', ['linear'], ['zoom'], 8, 0.15, 14, 0.6],
  cadastral_parcels: ['interpolate', ['linear'], ['zoom'], 15, 0.15, 18, 0.6],
  postal_codes: ['interpolate', ['linear'], ['zoom'], 6, 0.25, 13, 1],
  rural_polygons: ['interpolate', ['linear'], ['zoom'], 9, 0.25, 14, 1],
}

const colors: Record<BoundaryBasemap, { line: string; hover: string }> = {
  light: { line: '#3d4a57', hover: '#2563eb' },
  dark: { line: '#c3ccd5', hover: '#60a5fa' },
  satellite: { line: '#ffffff', hover: '#fde047' },
}

interface ZoomRange {
  min: number
  max: number
}

const isOverlay = (layer: BoundaryLayer): layer is BoundaryOverlay => (boundaryOverlays as readonly string[]).includes(layer)

/** The layers drawn as lines along with a fixed layer: itself and the coarser levels, or an overlay's context. */
function fixedLines(layer: BoundaryLayer): BoundaryLayer[] {
  if (isOverlay(layer)) return [layer, ...overlayContext[layer]]
  return boundaryLevels.slice(0, boundaryLevels.indexOf(layer) + 1)
}

/**
 * Where each layer shows in a mode. A layer's fill (hover target, and later its choropleth) shows
 * only while it's the active one; a level's lines also stay under finer levels, as context.
 * - Automatic: each level is active from its zoom (config) to the next one's; overlays are hidden.
 * - Fixed: the chosen layer is active at every zoom, with the coarser levels' lines over it
 *   (for an overlay, the levels in `overlayContext`).
 */
function zoomRanges(mode: BoundaryMode): Record<BoundaryLayer, { fill?: ZoomRange; line?: ZoomRange }> {
  const always = { min: 0, max: NO_MAX_ZOOM }
  const lines = mode === 'auto' ? [] : fixedLines(mode)
  const entries = boundaryLayers.map((layer) => {
    if (mode !== 'auto') {
      return [layer, { fill: layer === mode ? always : undefined, line: lines.includes(layer) ? always : undefined }] as const
    }
    if (isOverlay(layer)) return [layer, {}] as const
    const index = boundaryLevels.indexOf(layer)
    const from = config.boundaries.autoFromZoom[layer]
    const next = boundaryLevels[index + 1]
    const to = next ? config.boundaries.autoFromZoom[next] : NO_MAX_ZOOM
    return [layer, { fill: { min: from, max: to }, line: { min: from, max: NO_MAX_ZOOM } }] as const
  })
  return Object.fromEntries(entries) as Record<BoundaryLayer, { fill?: ZoomRange; line?: ZoomRange }>
}

/** How far out the map can zoom in a mode. */
export const minZoomFor = (mode: BoundaryMode) => (mode === 'auto' ? config.map.minZoom : config.boundaries.fixedMinZoom[mode])

/** The layer whose units are shown (and hovered) at this zoom. */
export function activeLevel(mode: BoundaryMode, zoom: number): BoundaryLayer {
  if (mode !== 'auto') return mode
  return boundaryLevels.findLast((level) => zoom >= config.boundaries.autoFromZoom[level]) ?? boundaryLevels[0]
}

function layers(mode: BoundaryMode, basemap: BoundaryBasemap): LayerSpecification[] {
  const ranges = zoomRanges(mode)
  const { line, hover } = colors[basemap]
  const fills = boundaryLayers.map(
    (level): LayerSpecification => ({
      id: fillId(level),
      type: 'fill',
      source: sourceId(level),
      'source-layer': level,
      minzoom: ranges[level].fill?.min ?? 0,
      maxzoom: ranges[level].fill?.max ?? NO_MAX_ZOOM,
      layout: { visibility: ranges[level].fill ? 'visible' : 'none' },
      // Invisible until hovered, but still there to be hovered (and, later, coloured by a statistic).
      paint: {
        'fill-color': hover,
        'fill-opacity': [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          0.3,
          ['boolean', ['feature-state', 'hover'], false],
          0.18,
          0,
        ],
      },
    }),
  )
  // Overlays, then the levels finest first, so the coarser lines draw on top.
  const lines = [...boundaryOverlays, ...[...boundaryLevels].reverse()].map(
    (level): LayerSpecification => ({
      id: lineId(level),
      type: 'line',
      source: sourceId(level),
      'source-layer': level,
      minzoom: ranges[level].line?.min ?? 0,
      maxzoom: ranges[level].line?.max ?? NO_MAX_ZOOM,
      layout: { visibility: ranges[level].line ? 'visible' : 'none', 'line-join': 'round' },
      paint: {
        'line-color': ['case', ['boolean', ['feature-state', 'selected'], false], hover, line],
        'line-width': lineWidths[level],
        'line-opacity': 0.85,
      },
    }),
  )
  return [...fills, ...lines]
}

/**
 * The basemap style with the boundary sources and layers added, under the basemap's labels so
 * place names stay readable. Used on every style load (first one, theme and basemap swaps).
 */
export function withBoundaries(style: StyleSpecification, mode: BoundaryMode, basemap: BoundaryBasemap): StyleSpecification {
  const sources = { ...style.sources }
  for (const level of boundaryLayers) {
    // Each layer's TileJSON brings its own zoom range: past its max zoom, its last tiles scale up.
    sources[sourceId(level)] = { type: 'vector', url: `${config.tiles.url}/${level}`, promoteId: 'id' }
  }
  const firstLabel = style.layers.findIndex((layer) => layer.type === 'symbol')
  const at = firstLabel === -1 ? style.layers.length : firstLabel
  return { ...style, sources, layers: [...style.layers.slice(0, at), ...layers(mode, basemap), ...style.layers.slice(at)] }
}

/** Switches the mode on the loaded style, without reloading it. */
export function applyBoundaryMode(map: MaplibreMap, mode: BoundaryMode) {
  const ranges = zoomRanges(mode)
  for (const level of boundaryLayers) {
    for (const [id, range] of [
      [fillId(level), ranges[level].fill],
      [lineId(level), ranges[level].line],
    ] as const) {
      if (!map.getLayer(id)) continue
      map.setLayoutProperty(id, 'visibility', range ? 'visible' : 'none')
      if (range) map.setLayerZoomRange(id, range.min, range.max)
    }
  }
}

/** What the hover label and the detail panel call a unit: its name, or for census units their number and municipality. */
export function unitLabel(properties: Record<string, unknown>): string {
  const name = String(properties.name ?? '')
  const district = String(properties.district ?? '')
  switch (properties.kind) {
    case 'shared_territory':
      return `${name} · ${copy.boundaries.sharedTerritory}`
    case 'census_district':
      return copy.boundaries.unitLabels.census_district(district, name)
    case 'census_section':
      return copy.boundaries.unitLabels.census_section(district, String(properties.section ?? ''), name)
    case 'postal_code':
      return copy.boundaries.unitLabels.postal_code(name)
    case 'rural_polygon':
      return copy.boundaries.unitLabels.rural_polygon(String(properties.polygon ?? ''), name)
    case 'cadastral_parcel':
      return copy.boundaries.unitLabels.parcel(String(properties.reference ?? ''), name)
    default:
      return name
  }
}

/** The unit drawn at a point of the map: the active layer's (only its fill is shown and queryable). */
function unitAt(map: MaplibreMap, point: MapMouseEvent['point']) {
  const fills = boundaryLayers.map(fillId).filter((id) => map.getLayer(id))
  const feature = fills.length ? map.queryRenderedFeatures(point, { layers: fills })[0] : undefined
  return feature?.id === undefined ? undefined : feature
}

/** A unit picked on the map: where it is in the tiles (for its highlight) and what it is. */
export interface SelectedUnit {
  target: FeatureIdentifier
  kind: string
  properties: Record<string, unknown>
}

/** Calls `onSelect` with the unit clicked, or undefined after a click on no unit. Returns the cleanup. */
export function trackBoundaryClicks(map: MaplibreMap, onSelect: (unit: SelectedUnit | undefined) => void): () => void {
  const onClick = (event: MapMouseEvent) => {
    const feature = unitAt(map, event.point)
    onSelect(
      feature && {
        target: { source: feature.source, sourceLayer: feature.sourceLayer, id: feature.id! },
        kind: String(feature.properties.kind ?? ''),
        properties: feature.properties,
      },
    )
  }
  map.on('click', onClick)
  return () => {
    map.off('click', onClick)
  }
}

/** Marks a unit as selected (or unmarks it); a no-op while its source is missing during a style swap. */
export function markSelected(map: MaplibreMap, unit: SelectedUnit | undefined, selected: boolean) {
  if (unit && map.getSource(unit.target.source)) map.setFeatureState(unit.target, { selected })
}

/**
 * Highlights the unit under the pointer, shows its name next to it and a pointer cursor (units
 * can be clicked). Returns the cleanup that removes the listeners and the label.
 */
export function trackBoundaryHover(map: MaplibreMap): () => void {
  let hovered: FeatureIdentifier | undefined
  const label = new Popup({ closeButton: false, closeOnClick: false, className: 'boundary-label', offset: 14, maxWidth: 'none' })

  const clear = () => {
    // The source may be gone for a moment while the style swaps.
    if (hovered && map.getSource(hovered.source)) map.setFeatureState(hovered, { hover: false })
    hovered = undefined
    label.remove()
    map.getCanvas().style.cursor = ''
  }

  const onMove = (event: MapMouseEvent) => {
    const feature = unitAt(map, event.point)
    if (!feature) return clear()
    if (!hovered || hovered.id !== feature.id || hovered.source !== feature.source) {
      clear()
      hovered = { source: feature.source, sourceLayer: feature.sourceLayer, id: feature.id! }
      map.setFeatureState(hovered, { hover: true })
    }
    label.setText(unitLabel(feature.properties))
    label.setLngLat(event.lngLat)
    if (!label.isOpen()) label.addTo(map)
    map.getCanvas().style.cursor = 'pointer'
  }

  map.on('mousemove', onMove)
  map.on('mouseout', clear)
  return () => {
    map.off('mousemove', onMove)
    map.off('mouseout', clear)
    clear()
  }
}
