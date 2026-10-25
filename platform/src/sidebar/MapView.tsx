import { copy } from '../app/copy'

/** The map tab's panel: the data layers on the map (none yet). */
export function MapView() {
  return (
    <section className="sidebar-section">
      <h3>{copy.mapView.layers}</h3>
      <p className="sidebar-empty">{copy.mapView.noLayers}</p>
    </section>
  )
}
