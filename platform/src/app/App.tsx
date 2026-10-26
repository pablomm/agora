import type { Map as MaplibreMap } from 'maplibre-gl'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ActivityBar } from '../components/ActivityBar'
import { BoundariesMenu } from '../components/BoundariesMenu'
import { DetailPanel } from '../components/DetailPanel'
import { Header } from '../components/Header'
import { Legend } from '../components/Legend'
import { SettingsMenu } from '../components/SettingsMenu'
import { Sidebar } from '../components/Sidebar'
import { api, facetFor, facetsAt, periodFor, yearBefore, type Catalog, type Choices, type Observations, type Place, type Variable } from '../data/api'
import { activeLevel, classBreaks, LAYER_LEVEL, minZoomFor, unitFromPlace, type Choropleth, type SelectedUnit } from '../map/boundaries'
import { MainMap } from '../map/MainMap'
import { MapControls } from '../map/MapControls'
import { useZoom } from '../map/useZoom'
import { MapView } from '../sidebar/MapView'
import type { ViewId } from '../sidebar/views'
import { loadSettings, saveSettings, type BoundaryLayer } from './settings'
import { setThemeMode, useTheme } from './theme'

/** Boundary layers with statistics, from the most detailed. */
const DATA_LAYERS: BoundaryLayer[] = ['census_sections', 'census_districts', 'municipalities', 'provinces', 'autonomous_communities']

/** The layer to paint a variable on: the one shown, or the finest coarser one with data when it has none there. */
function finestWithData(variable: Variable, shown: BoundaryLayer): BoundaryLayer {
  // Layers without statistics in the automatic sequence (parcels) are finer than sections.
  const start = Math.max(0, DATA_LAYERS.indexOf(shown))
  return DATA_LAYERS.slice(start).find((layer) => facetsAt(variable, LAYER_LEVEL[layer]!).length > 0) ?? shown
}

/** A variable with nothing picked yet: its default options and source (one object, so effects see no change). */
const NO_PICK: { choices: Choices; facet?: string; change?: boolean } = { choices: {} }

export default function App() {
  const [settings, setSettings] = useState(loadSettings)
  const [view, setView] = useState<ViewId | undefined>('map')
  const [map, setMap] = useState<MaplibreMap>()
  // The unit clicked on the map (or found by search), open in the detail panel.
  const [selected, setSelected] = useState<SelectedUnit>()
  const closeDetail = useCallback(() => setSelected(undefined), [])

  useEffect(() => {
    saveSettings(settings)
    setThemeMode(settings.theme)
  }, [settings])

  // The catalogue: which variables there are, at which levels and years.
  const [catalog, setCatalog] = useState<Catalog>()
  const [catalogFailed, setCatalogFailed] = useState(false)
  useEffect(() => {
    api.catalog().then(setCatalog, () => setCatalogFailed(true))
  }, [])

  // The data layer: a variable painted on the boundary layer the map shows, in a year.
  const [variableId, setVariableId] = useState<string>()
  const [period, setPeriod] = useState<number>()
  // Each variable keeps its options and source while others are shown.
  const [picks, setPicks] = useState<Record<string, { choices: Choices; facet?: string; change?: boolean }>>({})
  const pick = (variableId && picks[variableId]) || NO_PICK
  const updatePick = (change: Partial<typeof pick>) => variableId && setPicks({ ...picks, [variableId]: { ...pick, ...change } })
  const zoom = useZoom(map)
  const variable = catalog?.variables.find((item) => item.id === variableId)
  const zoomLayer = zoom === undefined ? undefined : activeLevel(settings.boundaries, zoom)
  // In automatic mode, zooming in past the data layer's finest level keeps that level on the map
  // (municipal registers at district zoom show municipalities).
  const layer = settings.boundaries === 'auto' && variable && zoomLayer ? finestWithData(variable, zoomLayer) : zoomLayer
  const level = layer ? LAYER_LEVEL[layer] : undefined
  const mapSettings = layer && layer !== zoomLayer ? { ...settings, boundaries: layer } : settings
  const facet = variable && level ? facetFor(variable, level, pick.facet) : undefined
  const change = Boolean(pick.change)
  const covered = facet && level ? [...(facet.coverage[level] ?? [])].sort((a, b) => b - a) : []
  // A change needs the year before: the first year can't show one.
  const years = change ? covered.filter((item) => covered.includes(yearBefore(item))) : covered
  const shown = facet && level ? periodFor(facet, level, period) : undefined
  const year = shown !== undefined && change && !years.includes(shown) ? years[0] : shown
  const choices = pick.choices

  const request =
    variable && level && facet && year !== undefined ? `${variable.id}|${level}|${year}|${facet.id}|${JSON.stringify(choices)}|${change}` : undefined
  const [observations, setObservations] = useState<{ key: string; data?: Observations }>()
  useEffect(() => {
    if (!request || !variable || !level || !facet || year === undefined) return
    let current = true
    api.observations(variable.id, level, year, facet.id, choices, change).then(
      (data) => current && setObservations({ key: request, data }),
      () => current && setObservations({ key: request }),
    )
    return () => {
      current = false
    }
    // The request key covers the choices.
  }, [request, variable, level, facet, year, choices, change])
  const ready = observations?.key === request ? observations : undefined
  // Changes go both ways: a diverging scale.
  const palette = change ? 'diverging' : (variable?.palette ?? 'sequential')

  const choropleth = useMemo<Choropleth | undefined>(
    () =>
      layer && ready?.data
        ? {
            layer,
            values: ready.data.values,
            breaks: classBreaks(Object.values(ready.data.values), ready.data.stats.quantiles, palette),
            palette,
            change: Boolean(ready.data.change),
            label: ready.data.label,
            unit: ready.data.unit,
            period: ready.data.period,
          }
        : undefined,
    [layer, ready, palette],
  )
  const theme = useTheme()
  const basemap = settings.basemap === 'satellite' ? 'satellite' : theme
  const levelLabel = level && catalog?.levels.find((item) => item.id === level)?.label
  const legendStatus = !facet ? 'unavailable' : !ready ? 'loading' : ready.data ? 'ready' : 'failed'

  /** A place found by search: the map fits it and its panel opens. */
  const goTo = useCallback(
    (place: Place) => {
      if (map && place.west !== null && place.south !== null && place.east !== null && place.north !== null) {
        map.fitBounds(
          [
            [place.west, place.south],
            [place.east, place.north],
          ],
          { padding: 60, maxZoom: 13, duration: 900 },
        )
      }
      setSelected(unitFromPlace(place.id, place.level, place.name))
    },
    [map],
  )

  return (
    <div className="app">
      <ActivityBar active={view} onSelect={(id) => setView(view === id ? undefined : id)} />
      {view && (
        <Sidebar viewId={view} onClose={() => setView(undefined)}>
          <MapView
            catalog={catalog}
            catalogFailed={catalogFailed}
            variableId={variableId}
            onVariable={setVariableId}
            onMeasure={(id) => {
              // The other measure takes what's picked here (options it lacks fall back to its default).
              setPicks({ ...picks, [id]: pick })
              setVariableId(id)
            }}
            years={years}
            period={period}
            onPeriod={setPeriod}
            choices={choices}
            onChoices={(next) => updatePick({ choices: next })}
            facets={variable && level ? facetsAt(variable, level) : []}
            facetId={facet?.id}
            onFacet={(id) => updatePick({ facet: id })}
            change={change}
            onChange={(next) => updatePick({ change: next })}
          />
        </Sidebar>
      )}
      <main className="map-area">
        <MainMap settings={mapSettings} selected={selected} onSelect={setSelected} choropleth={choropleth} onReady={setMap} />
        <div className="top-left">
          <Header onPlace={goTo} />
        </div>
        <div className="top-right">
          <SettingsMenu settings={settings} onChange={setSettings} />
          <BoundariesMenu mode={settings.boundaries} onChange={(boundaries) => setSettings({ ...settings, boundaries })} map={map} />
          {map && <MapControls map={map} minZoom={minZoomFor(settings.boundaries)} />}
        </div>
        {variable && (
          <div className="bottom-left">
            <Legend variable={variable} basemap={basemap} palette={palette} levelLabel={levelLabel} observations={ready?.data} status={legendStatus} />
          </div>
        )}
      </main>
      {selected && <DetailPanel unit={selected} catalog={catalog} variableId={variableId} choices={choices} facetId={pick.facet} period={period} onClose={closeDetail} />}
    </div>
  )
}
