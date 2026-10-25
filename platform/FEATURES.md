# Features

Log of what the platform does, newest first. Add an entry with every feature that ships.

## 2026-10-25 · Matching borders between levels

- Where levels share a border (autonomous community, province, municipality, district, section),
  the map now draws a single line at every zoom: all levels' tiles go up to zoom 14, so none is
  scaled up from coarser lines under the others.

## 2026-10-25 · Cadastral polygons

- **Cadastral polygons** (183,133 rural polygons, every municipality: state Catastro and the foral
  cadastres) as a fixed-only layer, like postal codes: chosen from the boundaries button
  ("Polígonos catastrales"), not part of the automatic mode, with autonomous community, province
  and municipality lines over them. Can't zoom out past 9. Hover and detail: "Polígono 003 ·
  Bujalance · Polígono catastral".

## 2026-10-25 · Detail panel

- **Clicking a unit** on the map (any boundary layer) opens a **detail panel on the right**, like
  Tupper Tracker's: its name as title and its kind under it ("Comunidad de Madrid · Comunidad
  autónoma", "Parcela 0444101VK4704C · Madrid · Parcela urbana"). No data yet ("Todavía no hay
  datos de esta unidad").
- The selected unit stays highlighted on the map (stronger fill and outline), also after theme or
  basemap changes. The pointer turns into a hand over units.
- Closes with its ✕ button, Escape, or a click on the map outside any unit; clicking another unit
  shows that one. On phones it's a sheet over the bottom of the map.

## 2026-10-25 · Census units meet municipal boundaries

- Census districts and sections are redrawn to IGN's municipal boundaries (clipped to each
  municipality, gaps given to the neighbouring section), so their lines meet the municipalities'
  exactly instead of INE's slightly different cartography.

## 2026-10-25 · Urban parcels

- **Urban cadastral parcels** (13.2 million, every municipality) as the most detailed level: from
  the state Catastro (April 2023) and the foral cadastres of Navarra, Álava, Bizkaia and Gipuzkoa
  (spring 2023). In the automatic mode after census sections, from zoom 15; fixed from the
  boundaries button ("Parcelas urbanas"), which can't zoom out past 15. Hover: "Parcela
  0000602VK4800A · Madrid".
- No blocks or rural polygons on the map: the automatic mode goes from census sections straight to
  parcels (blocks don't exist in the foral cadastres, and sections are already small in cities).
  Each parcel keeps its block in the data.

## 2026-10-25 · Postal codes and zoom limits per layer

- **Postal codes** as a boundary layer (10,874 areas, January 2024). They don't nest in the
  administrative hierarchy, so they're not part of the automatic mode: only fixed, from the
  boundaries button, where a line sets them apart. Fixed, they show with the province and
  autonomous community lines over them. Hover: "Código postal 28001".
- **Zoom limit per fixed layer**: with a layer fixed, the map can't zoom out further than makes
  sense for it, so it never loads too many units at once or shows an empty map: municipalities
  from zoom 5, census districts from 8, census sections from 9, postal codes from 7
  (`config.boundaries.fixedMinZoom`). Fixing a layer while further out zooms the map in to its
  minimum; the zoom-out button disables at it. The automatic mode keeps the map's own minimum.

## 2026-10-25 · Census districts and sections

- Two more boundary levels from the tile server: **census districts** and **census sections**
  (INE, 2026 edition).
- **Automatic mode** now goes on past municipalities: districts from zoom 10, sections from 12.
- Both can be fixed from the boundaries button ("Distritos censales", "Secciones censales").
- Hover label for census units, which have numbers rather than names: "Distrito 05 · Madrid",
  "Distrito 05 · Sección 003 · Madrid".

## 2026-10-25 · Administrative boundaries

- **Boundary layers** from the tile server (Martin, `../tileserver`, `VITE_TILES_URL`): autonomous
  communities, provinces and municipalities (with the shared territories between them), as vector
  tiles. Each layer has its own tile zoom range; past its max zoom the map scales it up.
- **Automatic mode** (default): the level changes with the zoom: autonomous communities below
  zoom 6, provinces from 6, municipalities from 8 (`config.boundaries.autoFromZoom`). Coarser
  levels stay drawn as thicker lines over finer ones.
- **Boundaries button** (layers icon, in the right column under settings): Automático, or one level
  fixed at every zoom. The automatic option names the level shown at the current zoom; a fixed
  level marks the button with a dot. Saved with the settings.
- **Hover**: the unit under the pointer is highlighted and its name shown next to it (shared
  territories say so).
- Colours follow the basemap (light, dark, orthophoto), and the layers survive theme and basemap
  changes.
- If the tile server can't be reached, a notice says so (separate from the basemap's).
- Attribution "CC BY 4.0 ign.es" on the map.

## 2026-10-25 · Map buttons on the right

- Full screen, zoom and my location move to the top-right corner, as in Tupper Tracker
  (the location message now opens to the button's left). Settings joins them, first in the
  column, and its panel opens to its left. The top-left corner keeps only the header.

## 2026-10-24 · First iteration: map shell

- **Base map**: full-size MapLibre GL map opening on mainland Spain and the Balearic Islands.
  OpenFreeMap Positron (light) and Dark styles, no API key; overridable in `.env.local`.
- **Header**: name and a "Busca tu ciudad" search field (no search behind it yet).
- **Left column of map buttons**, under the header:
  - Settings (gear), whose panel opens to its right.
  - Full screen (hidden where the browser can't put the page in full screen).
  - Zoom in / out, each disabled at its limit.
  - My location: asks the browser once, flies there and marks the position with a dot;
    shows a short message if permission is denied or the position is unavailable.
- **Settings panel**:
  - Basemap: Mapa (vector) or Satélite (IGN PNOA orthophoto).
  - Layers: street names on/off (disabled on the orthophoto).
  - Theme: Auto (follows the system) / Claro / Oscuro, applied to the UI and the basemap.
  - Saved in `localStorage` (falls back to defaults when storage is unavailable).
- **Activity bar + sidebar** (VS Code style): a strip on the left edge with one tab, *Mapa*
  (map icon). Clicking it opens or closes its panel, which pushes the map on desktop and
  floats over it on phones. The panel holds an empty "Capas de datos" section for now.
