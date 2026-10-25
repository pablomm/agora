export const themeModes = ['auto', 'light', 'dark'] as const
export type ThemeMode = (typeof themeModes)[number]

export const basemaps = ['map', 'satellite'] as const
export type Basemap = (typeof basemaps)[number]

/** Nested administrative levels with boundary tiles, coarsest first: the automatic mode walks them with the zoom. */
export const boundaryLevels = [
  'autonomous_communities',
  'provinces',
  'municipalities',
  'census_districts',
  'census_sections',
  'cadastral_parcels',
] as const
export type BoundaryLevel = (typeof boundaryLevels)[number]
/** Boundary layers outside that hierarchy (postal codes don't nest in municipalities): they can only be fixed. */
export const boundaryOverlays = ['rural_polygons', 'postal_codes'] as const
export type BoundaryOverlay = (typeof boundaryOverlays)[number]
export const boundaryLayers = [...boundaryLevels, ...boundaryOverlays] as const
export type BoundaryLayer = (typeof boundaryLayers)[number]
/** 'auto' changes level with the zoom; a layer fixes it at every zoom. */
export type BoundaryMode = 'auto' | BoundaryLayer
export const boundaryModes: BoundaryMode[] = ['auto', ...boundaryLayers]

export interface Settings {
  basemap: Basemap
  boundaries: BoundaryMode
  /** Street names and road shields on the vector map (the orthophoto has none). */
  streetNames: boolean
  theme: ThemeMode
}

const defaults: Settings = { basemap: 'map', boundaries: 'auto', streetNames: true, theme: 'auto' }
const STORAGE_KEY = 'agora:settings'

/** The visitor's last settings; anything missing or no longer valid falls back to its default. */
export function loadSettings(): Settings {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}') as Partial<Settings>
    return {
      basemap: basemaps.includes(saved.basemap as Basemap) ? (saved.basemap as Basemap) : defaults.basemap,
      boundaries: boundaryModes.includes(saved.boundaries as BoundaryMode) ? (saved.boundaries as BoundaryMode) : defaults.boundaries,
      streetNames: typeof saved.streetNames === 'boolean' ? saved.streetNames : defaults.streetNames,
      theme: themeModes.includes(saved.theme as ThemeMode) ? (saved.theme as ThemeMode) : defaults.theme,
    }
  } catch {
    return defaults
  }
}

export function saveSettings(settings: Settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
  } catch {
    // Private mode or blocked storage: the settings last for this visit only.
  }
}
