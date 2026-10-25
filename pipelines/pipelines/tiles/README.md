# Tiles

Vector tiles (PMTiles) of the administrative and census boundaries, for the tile server in
`../tileserver` and the platform's map. Built with [tippecanoe](https://github.com/felt/tippecanoe) from the
outputs of other pipelines, so run those first:

```sh
python pipelines/autonomous_communities/autonomous_communities.py
python pipelines/provinces/provinces.py
python pipelines/municipalities/municipalities.py
python pipelines/census_sections/census_sections.py
python pipelines/census_sections/align_to_municipalities.py
python pipelines/postal_codes/postal_codes.py
python pipelines/cadastre/cadastral_zones.py              # then cadastral_parcels.py and foral_parcels.py
python pipelines/cadastre/cadastral_parcels.py
python pipelines/cadastre/foral_parcels.py
python pipelines/tiles/admin_boundaries.py               # all layers
python pipelines/tiles/admin_boundaries.py provinces     # just some
```

Requires `brew install tippecanoe` (2.79.0 when this was written). The administrative, census and
postal code layers take about two minutes together. The urban parcels (13.2 million) take about 20
minutes: they're written one province at a time, so memory peaks around 5 GB.

## Layers

One PMTiles file per layer, each with its own zoom range (`LAYERS` in `admin_boundaries.py`):

| Layer | Inputs | Zooms | Size |
|---|---|---|---|
| `autonomous_communities` | autonomous_communities | 0–14 | 8.6 MB |
| `provinces` | provinces | 0–14 | 11.5 MB |
| `municipalities` | municipalities + shared_territories | 4–14 | 69 MB |
| `census_districts` | census_sections (districts, 2026, aligned) | 5–14 | 80 MB |
| `census_sections` | census_sections (sections, 2026, aligned) | 6–14 | 103 MB |
| `cadastral_parcels` | cadastre: urban parcels, state Catastro and foral cadastres (2023) | 15–17 | 2.3 GB |
| `rural_polygons` | cadastre: cadastral polygons, state Catastro and foral cadastres (2023) | 8–14 | 472 MB |
| `postal_codes` | postal_codes (January 2024) | 5–13 | 38 MB |

The census layers are built from one edition (`CENSUS_YEAR`, 2026), redrawn to IGN's municipal
boundaries (`align_to_municipalities.py`) so they meet the municipalities layer; another edition's
census tiles would be separate layers, since sections change every year.

Tiles are built up to each layer's max zoom; past it, the map scales the last level up. Each layer
has its own file, so each can start at its own zoom.

**The administrative and census hierarchy (autonomous communities down to sections) all goes up to
zoom 14** (`HIERARCHY_MAX_ZOOM`). Their boundaries coincide in the data (each level is the union
of the next; sections are aligned to municipalities), but a layer whose tiles stopped at a lower
zoom would be scaled up from coarser, more simplified lines, drawing a second line next to the
finer layers' at the same border. Hierarchy layers also keep the nodes where borders meet
(`--no-simplification-of-shared-nodes`), so a shared border simplifies the same way in every level.

## Features

Each feature carries only:

- `id`: the catalogue id (`es:ine:prov:28`), which the map uses to join statistics and to hover.
- `name`: as in the source; for census units, their municipality's name as IGN writes it (census
  units have numbers, not names, and INE writes municipality names differently).
- `kind`: `autonomous_community`, `province`, `municipality`, `shared_territory`, `census_district`,
  `census_section`, `cadastral_parcel`, `rural_polygon` or `postal_code` (whose `name` is the code
  itself).
- Census units only: `district` (two digits) and, for sections, `section` (three digits), for the
  map's label ("Distrito 05 · Sección 003 · Madrid").
- Urban parcels: their `name` is their municipality's, plus `reference`. Cadastral polygons: their
  municipality's `name`, plus `polygon` (the number). Neither Catastro's blocks
  nor its rural polygons are tiled: the map goes from census sections to parcels.

Statistics aren't in the tiles: the map joins them by `id` in the browser, so changing a variable or
a year never needs new tiles.

## tippecanoe options

- `--detect-shared-borders`: neighbours share each border, simplified once, so they never gap or overlap.
- `--no-feature-limit --no-tile-size-limit`: a choropleth can't lose units, so no feature is dropped
  however dense the tile. The densest tiles are about 250 KB gzipped for municipalities (zooms 4–6)
  and 530 KB for census sections at zoom 6 over Madrid (only requested when sections are fixed far out).
- Attribution per source (`CC BY 4.0 ign.es`, INE's wording for the census layers, Dirección General
  del Catastro for the cadastral zones, and a provisional one for postal codes until their
  provenance is documented), which
  reaches the map through each layer's TileJSON.

## Output

In `data/processed/tiles/`: `{layer}.pmtiles`, and `admin_boundaries.meta.json` with the build time,
tippecanoe version, and each layer's settings, feature count and size (building only some layers
keeps the others' entries).
