import type { Map as MaplibreMap } from 'maplibre-gl'
import { useCallback, useEffect, useState } from 'react'
import { ActivityBar } from '../components/ActivityBar'
import { BoundariesMenu } from '../components/BoundariesMenu'
import { DetailPanel } from '../components/DetailPanel'
import { Header } from '../components/Header'
import { SettingsMenu } from '../components/SettingsMenu'
import { Sidebar } from '../components/Sidebar'
import { minZoomFor, type SelectedUnit } from '../map/boundaries'
import { MainMap } from '../map/MainMap'
import { MapControls } from '../map/MapControls'
import type { ViewId } from '../sidebar/views'
import { loadSettings, saveSettings } from './settings'
import { setThemeMode } from './theme'

export default function App() {
  const [settings, setSettings] = useState(loadSettings)
  const [view, setView] = useState<ViewId | undefined>('map')
  const [map, setMap] = useState<MaplibreMap>()
  // The unit clicked on the map, open in the detail panel.
  const [selected, setSelected] = useState<SelectedUnit>()
  const closeDetail = useCallback(() => setSelected(undefined), [])

  useEffect(() => {
    saveSettings(settings)
    setThemeMode(settings.theme)
  }, [settings])

  return (
    <div className="app">
      <ActivityBar active={view} onSelect={(id) => setView(view === id ? undefined : id)} />
      {view && <Sidebar viewId={view} onClose={() => setView(undefined)} />}
      <main className="map-area">
        <MainMap settings={settings} selected={selected} onSelect={setSelected} onReady={setMap} />
        <div className="top-left">
          <Header />
        </div>
        <div className="top-right">
          <SettingsMenu settings={settings} onChange={setSettings} />
          <BoundariesMenu mode={settings.boundaries} onChange={(boundaries) => setSettings({ ...settings, boundaries })} map={map} />
          {map && <MapControls map={map} minZoom={minZoomFor(settings.boundaries)} />}
        </div>
      </main>
      {selected && <DetailPanel unit={selected} onClose={closeDetail} />}
    </div>
  )
}
