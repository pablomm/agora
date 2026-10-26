# Features

Log of what the platform does, newest first. Add an entry with every feature that ships.

## 2026-10-26 · Age indicators, birthplace, foreign population by section

- Demografía gains **Edad media** (from the five-year age groups, within 0.04 years of INE's) and
  the **índices de envejecimiento, dependencia y sobreenvejecimiento**, all by sex, down to census
  sections.
- Nacionalidad y origen gains **Población por lugar de nacimiento** (nº · %): born in the same
  municipality, another of the province, another province of the community, another community,
  abroad, or in Spain (the first four together), down to census sections.
- Población extranjera reaches census sections, with a second source (by section, without age).
  A layer's card only shows the options its current source applies: zoomed into sections, the age
  slider hides; the legend names only the choices applied.

## 2026-10-26 · Contract shares

- Contratos registrados and Contratos registrados por sector gain a % measure: each contract type's
  share of the month's contracts (of the same sex), and each sector's share.

## 2026-10-26 · Number and share as one layer

- A layer with a number and a share (Población por edad, Paro registrado por sector, the
  nationality and country of birth layers…) is one row in the list, marked `nº · %`, with a
  **Medida: Número | %** switch in its card. Switching keeps the options, source and year picked;
  an option the other measure lacks falls back to its default. The search finds a layer by either
  name. 29 rows become 21.
- No layer name starts with "%": shares are "Proporción de…" (the legend still says "(%)"), and
  "% de contratos indefinidos" is "Contratos indefinidos".

## 2026-10-26 · Nationality and country of birth layers, searchable dropdown

- New topic **Nacionalidad y origen** with eight layers, each as persons and as % of residents of
  the same sex: population by nationality and by country of birth, with about twenty main countries
  down to census sections, or a detailed list (about sixty countries and INE's country groups) down
  to municipalities. Each list nests countries under their groups and continents (Europa › Unión
  Europea › Francia), with the rests INE publishes ("Otros países de África"); groups are sums.
- Población extranjera and % de población extranjera move to that topic and gain sex and age
  options (the share is over residents of the same sex and age).
- Options with many values (more than 12) get a dropdown with a search box: typing filters the list
  (accents and case aside), arrows move, Enter picks, Esc closes; nested values are indented and
  groups are in bold. Values can name a `parent` in their dimension (`parents` in `catalog.json`).

## 2026-10-26 · Dropdowns for long options

- A layer's option (and its source switch) shows its values side by side only when they fit: up
  to 4 values with up to 40 characters between them. Otherwise it's a dropdown, so long or many
  values (sectors, relation with activity, contract type, age bands; nationalities later) no
  longer overlap. An option can force either in its pipeline's `catalog.json` with
  `"control": "segmented"` or `"control": "select"`; sector, activity and contract type say
  `select`.

## 2026-10-25 · Logo and app icons

- New logo: a pediment over columns of different heights, a stoa whose columns are bars. Used as
  the favicon (SVG, and an ICO at 16/32/48 with a pixel-aligned 16 px version), the Apple touch
  icon, and 192/512 PNG icons (plus a maskable one) in a web manifest (`site.webmanifest`), so the
  site can be added to the home screen as "Agora".

## 2026-10-26 · Parcel hover card, favicon, stronger control labels

- The parcel hover label is a compact card: the facade thumbnail (56 px, even margin around it)
  and, beside it, "Parcela urbana" as a small caption, the cadastral reference in bold and the
  municipality below, instead of one long bold line.
- The names of the active layer's controls (Sexo, Edad, Mes, Año, Fuente) are in text ink, so
  they stand out from the muted range ends.
- Favicon (ICO, SVG), Apple touch icon and web app manifest.

## 2026-10-25 · Collapsible topics in the layers list

- Each topic heading in the layers list (Demografía, Empleo…) collapses and expands its layers,
  with a chevron and the number of layers it has. The browser remembers which are collapsed. While
  searching, every topic with matches shows, collapsed or not.

## 2026-10-25 · Employment layers, monthly periods

- New topic **Empleo**: registered unemployment (by sex and age band; by sector; share by sector;
  over the population aged 15–64), job seekers (by sex and age; by sector), registered contracts
  (by sex and contract type; by sector; % permanent), monthly by municipality since 2006 (SEPE),
  and from the annual census by **census section** (2021–2024): unemployment, activity and
  employment rates, and population 16+ by relation with activity, by sex.
- **Monthly periods**: the slider moves by month ("sep 2026"), the evolution chart has a time axis
  with one point per month, legend, tooltip and panel say the month. Switching between a monthly
  and a yearly layer keeps the time: a month becomes its year, a year its last month.
- In automatic boundaries mode, zooming in past a layer's finest level keeps that level on the map
  (municipal registers stay on municipalities at district zoom).
- Topics in the layers list follow the catalogue's order.

## 2026-10-25 · Hover label with the layer's value

- With a data layer on, hovering a unit of the layer shown adds its value (bold, with its
  class's color swatch) and what it is ("% de población por edad · 65 años o más · 2025") under
  its name; "Sin datos" when the unit has no value. Without a layer, the label is the name, as before.

## 2026-10-25 · Layer options: sex, age range and source

- Layers that are the same measure split by a dimension are now one layer with a **selector
  next to the year**: "Población" (Total · Hombres · Mujeres), "% de población por sexo"
  (Mujeres · Hombres), "Población por edad" and "% de población por edad" (a two-thumb slider
  over the five-year age groups, 0 to 100+: the groups in between are summed). Replaces the
  separate Hombres, Mujeres, % menores de 15 and % 65 o más layers.
- **Fuente** selector when the level has two sources of the same layer (Padrón (cifras oficiales)
  and Censo anual, from municipalities up); at census districts and sections only the census
  exists (2021–2025). The detail panel's evolution shows both as separate series.
- Each layer remembers its own choices; the legend, the detail panel's headline and its
  evolution follow them ("Población · Mujeres").

## 2026-10-25 · Data layers panel redesign

- The Mapa tab's layers panel, top to bottom: a small **search** over the layers (name,
  description or topic, accents ignored); the **layer on the map** — "Ninguna capa
  seleccionada" or a card with its name, a ✕ to remove it, its description and its year; then
  the **list of layers** by topic, dense one-line rows (name, and its unit on the right), no
  radio buttons, the chosen one marked. The list scrolls on its own, with each topic's heading
  pinned while its rows scroll, ready for dozens of layers.
- The active layer's **year is a slider** (thin track filled up to the thumb, year in bold, "último"
  when it's the newest, first and last year under the ends). It moves over the years the layer has
  at that level, so missing years are skipped. Layers whose versions aren't years get a select.

## 2026-10-25 · Data layers, search and data in the detail panel

- The web reads the catalogue and the data from the API (`VITE_API_URL`, `../api`).
- **Data layers**: the sidebar's Mapa tab lists the catalogue's variables by topic (population,
  men, women, men per 100 women, foreign population and its share, under-15 and 65+ shares).
  Choosing one paints it as a **choropleth** on the boundary level the map shows: in automatic
  mode the level, and the data with it, change with the zoom. Five classes by quantiles, one-hue
  blue ramp (its own steps on the dark basemap). A **year** selector lists the years the variable
  has at that level (latest by default).
- **Legend** (bottom left): variable, level, year, source, classes and attribution; it says when the
  level has no data for the variable, or the layer has no statistics (parcels, postal codes…).
- **Search** ("Busca tu ciudad") finds autonomous communities, provinces and municipalities by
  name, accents ignored, with keyboard navigation; picking one fits the map to it and opens its panel.
- **Detail panel with data**: the variable shown on the map (population when none) as a headline
  value with its year and source, its **evolution** (one line per source, legend, crosshair
  tooltip, table view), and the **population pyramid** (men and women by five-year group, tooltip
  per group) of the year on the map.
- With a data layer, hovering and selecting a unit raise its fill and outline its border.

## 2026-10-25 · Facade photos of parcels

- Hovering an urban parcel shows a square thumbnail left of its name: a grey loading placeholder
  (animated), then Catastro's facade photo of it, cropped to the square, from Catastro's facade
  photo service by cadastral reference (asked for after 100 ms on the parcel, so moving across
  parcels asks for none). Parcels without a photo, and foral-cadastre parcels (no such service),
  show a "no photo" sign instead.

## 2026-10-25 · Labels over the satellite basemap

- The satellite basemap (IGN's PNOA orthophoto) now has place, neighbourhood, street, road and
  water names over it: the light vector map's labels, in white with a dark halo. The street names
  switch works on it too. If the vector style can't be loaded, the orthophoto shows alone.

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
