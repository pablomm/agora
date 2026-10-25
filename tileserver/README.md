# Agora tile server

[Martin](https://maplibre.org/martin/) serving the vector tiles the platform draws: for now, the
administrative boundaries built by `pipelines/pipelines/tiles/` as PMTiles. Later, the same server
will also serve layers generated on the fly from PostGIS.

## Setup

```sh
brew install martin      # 1.16.1 when this was written
```

## Running

From this folder:

```sh
martin --config martin.yaml
```

It listens on `http://localhost:3000`, which is the platform's default `VITE_TILES_URL`.

| URL | What |
|---|---|
| `/catalog` | Every source it serves |
| `/{layer}` | A layer's TileJSON: zoom range, bounds, attribution, fields |
| `/{layer}/{z}/{x}/{y}` | A vector tile (MVT, gzip) |

Every `.pmtiles` file in `../pipelines/data/processed/tiles` becomes a source named after the file
(`provinces.pmtiles` → `/provinces`). Set `AGORA_TILES_DIR` to serve another folder. Martin keeps
tiles in a memory cache, so restart it after rebuilding the tiles.

CORS is open (Martin's default), so the platform's dev server can read the tiles from another port.

## Layers

| Layer | Features | Tile zooms |
|---|---|---|
| `autonomous_communities` | 19 | 0–14 |
| `provinces` | 52 | 0–14 |
| `municipalities` | 8,132 municipalities + 81 shared territories | 4–14 |
| `census_districts` | 10,452 census districts (2026, aligned to municipalities) | 5–14 |
| `census_sections` | 36,669 census sections (2026, aligned to municipalities) | 6–14 |
| `cadastral_parcels` | 13,209,772 urban cadastral parcels: state Catastro and foral cadastres (2023) | 15–17 |
| `rural_polygons` | 183,133 cadastral polygons: state Catastro and foral cadastres (2023) | 8–14 |
| `postal_codes` | 10,874 postal code areas (January 2024) | 5–13 |

Past its max zoom, the map scales a layer's last tiles up. Each feature carries `id` (the catalogue
id), `name` and `kind` (census units also `district` and `section`). Data: IGN (CC BY 4.0 ign.es),
INE (census layers), Dirección General del Catastro (urban parcels, with the foral cadastres of Navarra and the Basque Country; Catastro's under its own
license: see `pipelines/pipelines/cadastre/README.md`) and postal code areas from an earlier project, as each TileJSON's attribution says.
