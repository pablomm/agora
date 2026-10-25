import {
  Popup,
  type DataDrivenPropertyValueSpecification,
  type ExpressionSpecification,
  type FeatureIdentifier,
  type LayerSpecification,
  type Map as MaplibreMap,
  type MapMouseEvent,
  type StyleSpecification,
} from 'maplibre-gl'
import { config } from '../app/config'
import { formatPeriod, formatValue } from '../app/format'
import type { DataLevel } from '../data/api'
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

/** The statistical level each boundary layer draws (the cadastral and postal layers have no data yet). */
export const LAYER_LEVEL: Partial<Record<BoundaryLayer, DataLevel>> = {
  autonomous_communities: 'autonomous_community',
  provinces: 'province',
  municipalities: 'municipality',
  census_districts: 'census_district',
  census_sections: 'census_section',
}

/** The boundary layer drawing each statistical level. */
export const LEVEL_LAYER = Object.fromEntries(Object.entries(LAYER_LEVEL).map(([layer, level]) => [level, layer])) as Partial<
  Record<DataLevel, BoundaryLayer>
>

/** The kind of unit a level's features are (their `kind` in the tiles). */
export const LEVEL_KIND: Partial<Record<DataLevel, string>> = {
  autonomous_community: 'autonomous_community',
  province: 'province',
  municipality: 'municipality',
  census_district: 'census_district',
  census_section: 'census_section',
}

/**
 * Sequential ramp for choropleths: one hue (blue), light to dark (dataviz reference palette, steps
 * 150/300/450/550/700). On the dark basemap the anchor flips, so low values recede into the surface.
 */
const sequential: Record<BoundaryBasemap, string[]> = {
  light: ['#b7d3f6', '#6da7ec', '#2a78d6', '#1c5cab', '#0d366b'],
  satellite: ['#b7d3f6', '#6da7ec', '#2a78d6', '#1c5cab', '#0d366b'],
  dark: ['#184f95', '#256abf', '#3987e5', '#6da7ec', '#b7d3f6'],
}

/** A variable painted on a layer: each unit's value, and the class breaks (quantiles) of its legend. */
export interface Choropleth {
  layer: BoundaryLayer
  values: Record<string, number>
  breaks: number[]
  /** What the values are, for the hover label: the variable with its options, unit and year. */
  label: string
  unit: string
  period: number
}

/** The color a value gets: its class's. */
export function choroplethColor(value: number, breaks: number[], basemap: BoundaryBasemap): string {
  const classes = choroplethClasses(breaks, basemap)
  const index = classes.breaks.filter((limit) => value >= limit).length
  return classes.colors[index]
}

/**
 * The legend's classes: the distinct breaks, and one color per class taken evenly from the ramp
 * (fewer classes when quantiles repeat, as when most units share a value).
 */
export function choroplethClasses(breaks: number[], basemap: BoundaryBasemap): { breaks: number[]; colors: string[] } {
  const distinct = [...new Set(breaks)].sort((a, b) => a - b)
  const ramp = sequential[basemap]
  const count = distinct.length + 1
  const colors = Array.from({ length: count }, (_, index) => ramp[count === 1 ? ramp.length - 1 : Math.round((index * (ramp.length - 1)) / (count - 1))])
  return { breaks: distinct, colors }
}

const hasState = (key: string): ExpressionSpecification => ['boolean', ['feature-state', key], false]
const hasValue: ExpressionSpecification = ['==', ['typeof', ['feature-state', 'value']], 'number']

interface FillPaint {
  'fill-color': DataDrivenPropertyValueSpecification<string>
  'fill-opacity': DataDrivenPropertyValueSpecification<number>
}

/** A layer's fill: invisible until hovered or selected, or, with a choropleth, each unit's class color. */
function fillPaint(basemap: BoundaryBasemap, classes?: { breaks: number[]; colors: string[] }): FillPaint {
  const { hover } = colors[basemap]
  const interaction: ExpressionSpecification = ['case', hasState('selected'), 0.3, hasState('hover'), 0.18, 0]
  if (!classes) return { 'fill-color': hover, 'fill-opacity': interaction }
  const step = [
    'step',
    ['feature-state', 'value'],
    classes.colors[0],
    ...classes.breaks.flatMap((limit, index) => [limit, classes.colors[index + 1]]),
  ] as ExpressionSpecification
  return {
    'fill-color': ['case', hasValue, step, hover],
    'fill-opacity': ['case', hasValue, ['case', hasState('selected'), 0.95, hasState('hover'), 0.9, 0.75], interaction],
  }
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
      // Invisible until hovered or selected, but still there to be hovered; coloured when a variable is painted.
      paint: fillPaint(basemap),
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
        'line-color': ['case', ['any', hasState('selected'), hasState('hover')], hover, line],
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

/**
 * Paints a choropleth's classes on its layer's fill (the other layers get their plain fill back),
 * or none. Values are set apart, as feature state (`setChoroplethValues`).
 */
export function paintChoropleth(map: MaplibreMap, basemap: BoundaryBasemap, choropleth: Choropleth | undefined) {
  for (const layer of boundaryLayers) {
    if (!map.getLayer(fillId(layer))) continue
    const paint = fillPaint(basemap, choropleth?.layer === layer ? choroplethClasses(choropleth.breaks, basemap) : undefined)
    map.setPaintProperty(fillId(layer), 'fill-color', paint['fill-color'])
    map.setPaintProperty(fillId(layer), 'fill-opacity', paint['fill-opacity'])
  }
}

/** Where a unit's feature state lives in the tiles. */
export const featureTarget = (layer: BoundaryLayer, id: string): FeatureIdentifier => ({ source: sourceId(layer), sourceLayer: layer, id })

/**
 * Each unit's value as feature state, clearing the values set before (`previous`). Returns what's
 * now set, to clear next time.
 */
export function setChoroplethValues(map: MaplibreMap, choropleth: Choropleth | undefined, previous: { layer: BoundaryLayer; ids: string[] } | undefined) {
  if (previous && map.getSource(sourceId(previous.layer))) {
    for (const id of previous.ids) map.removeFeatureState(featureTarget(previous.layer, id), 'value')
  }
  if (!choropleth || !map.getSource(sourceId(choropleth.layer))) return undefined
  const ids = Object.keys(choropleth.values)
  for (const id of ids) map.setFeatureState(featureTarget(choropleth.layer, id), { value: choropleth.values[id] })
  return { layer: choropleth.layer, ids }
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

/**
 * Catastro's facade photo of a parcel, for state-cadastre parcels with a regular reference (the
 * foral cadastres have no such service).
 */
function facadePhoto(properties: Record<string, unknown>): string | undefined {
  const reference = String(properties.reference ?? '')
  if (!String(properties.id ?? '').startsWith('es:catastro:parcel:') || !/^[0-9A-Z]{14}$/.test(reference)) return undefined
  return config.catastro.facadePhotoUrl + reference
}

/** A camera struck through: a parcel without a facade photo. */
const NO_PHOTO_ICON =
  '<svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M4 8h3l2-2.5h6L17 8h3v10H4z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="12" cy="13" r="3.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M4 4l16 16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>'

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

/** A unit found by search, as if clicked on the map (its layer's feature, by id). */
export function unitFromPlace(id: string, level: DataLevel, name: string): SelectedUnit | undefined {
  const layer = LEVEL_LAYER[level]
  const kind = LEVEL_KIND[level]
  if (!layer || !kind) return undefined
  return { target: featureTarget(layer, id), kind, properties: { id, name, kind } }
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

/** The hover label's data: the value with its class's swatch, then what it is (variable, year). */
function dataLine(choropleth: Choropleth, value: number | undefined, basemap: BoundaryBasemap): HTMLElement {
  const line = document.createElement('div')
  line.className = 'boundary-label-value'
  const swatch = document.createElement('span')
  swatch.className = 'boundary-label-swatch'
  const amount = document.createElement('strong')
  if (value === undefined) {
    swatch.classList.add('is-empty')
    amount.textContent = copy.boundaries.noValue
  } else {
    swatch.style.background = choroplethColor(value, choropleth.breaks, basemap)
    amount.textContent = formatValue(value, choropleth.unit)
  }
  const what = document.createElement('small')
  what.textContent = `${choropleth.label} · ${formatPeriod(choropleth.period)}`
  line.append(swatch, amount)
  const box = document.createElement('div')
  box.append(line, what)
  return box
}

/**
 * Highlights the unit under the pointer, shows its name next to it and a pointer cursor (units
 * can be clicked); with a data layer on the hovered unit's layer, the label adds its value. Returns
 * the cleanup that removes the listeners and the label.
 */
export function trackBoundaryHover(map: MaplibreMap, data: () => { choropleth: Choropleth | undefined; basemap: BoundaryBasemap }): () => void {
  let hovered: FeatureIdentifier | undefined
  // The data layer the label was made with, to remake it when the layer changes under the pointer.
  let shownWith: Choropleth | undefined
  let photoTimer: ReturnType<typeof setTimeout> | undefined
  const label = new Popup({ closeButton: false, closeOnClick: false, className: 'boundary-label', offset: 14, maxWidth: 'none' })

  const clear = () => {
    clearTimeout(photoTimer)
    // The source may be gone for a moment while the style swaps.
    if (hovered && map.getSource(hovered.source)) map.setFeatureState(hovered, { hover: false })
    hovered = undefined
    label.remove()
    map.getCanvas().style.cursor = ''
  }

  /**
   * The label's text; for parcels, a square thumbnail to its left: a loading placeholder, then
   * the facade photo (cropped to the square) or, without one, a "no photo" sign.
   */
  const showLabel = (properties: Record<string, unknown>, layer: string | undefined, id: string) => {
    const content = document.createElement('div')
    const text = document.createElement('span')
    text.textContent = unitLabel(properties)
    content.append(text)
    label.setDOMContent(content)
    const { choropleth, basemap } = data()
    shownWith = choropleth
    if (choropleth && choropleth.layer === layer) {
      content.className = 'boundary-label-data'
      text.className = 'boundary-label-name'
      content.append(dataLine(choropleth, choropleth.values[id], basemap))
      return
    }
    if (properties.kind !== 'cadastral_parcel') return

    // Parcels: a card with the thumbnail, then what it is, the reference and the municipality.
    content.className = 'parcel-card'
    const details = document.createElement('div')
    details.className = 'parcel-details'
    const kind = document.createElement('span')
    kind.className = 'parcel-kind'
    kind.textContent = copy.detail.kinds.cadastral_parcel
    const reference = document.createElement('strong')
    reference.className = 'parcel-reference'
    reference.textContent = String(properties.reference ?? '')
    const place = document.createElement('span')
    place.className = 'parcel-place'
    place.textContent = String(properties.name ?? '')
    details.append(kind, reference, place)
    const thumb = document.createElement('div')
    thumb.className = 'boundary-thumb is-loading'
    content.replaceChildren(thumb, details)
    const missing = () => {
      thumb.className = 'boundary-thumb is-missing'
      thumb.title = copy.boundaries.noFacadePhoto
      thumb.innerHTML = NO_PHOTO_ICON
    }
    const photo = facadePhoto(properties)
    // Foral cadastres have no photo service.
    if (!photo) return missing()
    photoTimer = setTimeout(() => {
      const image = new Image()
      image.alt = copy.boundaries.facadePhoto
      image.onload = () => {
        // Parcels without a photo get an empty answer.
        if (image.naturalWidth === 0) return missing()
        thumb.className = 'boundary-thumb'
        thumb.append(image)
      }
      image.onerror = missing
      image.src = photo
    }, config.catastro.photoDelayMs)
  }

  const onMove = (event: MapMouseEvent) => {
    const feature = unitAt(map, event.point)
    if (!feature) return clear()
    if (!hovered || hovered.id !== feature.id || hovered.source !== feature.source) {
      clear()
      hovered = { source: feature.source, sourceLayer: feature.sourceLayer, id: feature.id! }
      map.setFeatureState(hovered, { hover: true })
      showLabel(feature.properties, feature.sourceLayer, String(feature.id))
    } else if (shownWith !== data().choropleth) {
      showLabel(feature.properties, feature.sourceLayer, String(feature.id))
    }
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
