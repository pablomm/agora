# TODO

Pending work and decisions, with the reasoning behind them.

## Smaller `/observations` payloads

Today the API answers uncompressed: `population` by census section (36,554 units) is 1.12 MB on
every change of variable, year or option. Municipalities are 207 KB.

Measured on that response:

| Format | Raw | gzip |
|---|---|---|
| Current (`{"es:ine:sec:…": 970.0}`) | 1,122 KB | 213 KB |
| Without the `es:ine:sec:` prefix | 646 KB | 196 KB |
| Columnar, sorted (`codes: […], values: […]`) | 646 KB | 154 KB |
| Values only, in an order the client knows | 171 KB | 70 KB |

Brotli on the current format: 152 KB.

1. **Compress responses**: `GZipMiddleware(minimum_size=1000)` in `api/agora_api/main.py`; in
   production, brotli at the proxy or CDN. 1.1 MB → ~210 KB, no format change.
2. **HTTP caching**: values don't change for a given variable, period and option. `Cache-Control`
   until the next catalogue rebuild, or an `ETag` tied to it, so browser and CDN don't download them
   again across sessions (`platform/src/data/api.ts` only caches in memory while the app is open).
3. **Columnar format, without the prefix** (optional): another ~28% over gzip, still readable. The
   level is already in the response. Cheap to change now while the platform is the only consumer
   (MCP calls the services directly).

Not worth it: values only, in the tiles' order (ties the API to the tiles, and a mismatch paints data
on the wrong units without any error); binary formats (Arrow, protobuf), little gain over gzip and
harder to debug.

## Data by cadastral parcel

Geometries are already served as vector tiles (Martin over PMTiles, z15–17 for
`cadastral_parcels`), but `/observations` sends a whole level at once. With millions of urban parcels
that's impossible: values have to come for the area on screen.

- **A. By census section** (`/observations?level=cadastral_parcel&within=es:ine:sec:…`):
  - For: `within` already exists, and it means something to the API and MCP ("the parcels in this
    section").
  - Needs: each parcel assigned to its section by centroid, in the pipeline.
  - Against: at z15 a city screen covers dozens of sections, so dozens of requests. The parcel
    tiles don't carry the section, so the client would have to query the sections layer to know
    which ones are on screen. Rural and urban sections differ widely in size.
- **B. By tile** (`/observations/tiles/{variable}/14/{x}/{y}?…` → `{codes, values}` of the parcels
  whose centroid falls in it), the one to build if there are many variables:
  - Which to fetch: the client works out the tiles on screen with the same math as MapLibre.
  - Size: similar sizes, 4–9 requests per screen.
  - Caching: each URL is immutable (variable + period + tile), ideal for HTTP caching and a CDN.
  - Needs: each parcel's tile precomputed in the pipeline (a `tile_z14` column in the Parquet), so
    DuckDB filters it at once.
  - Parcels on a border paint when the tile of their centroid arrives. MapLibre already loads the
    neighbouring tiles at z15, so it barely shows.
- **C. Values baked into the tiles** (year built, floor area, use… as feature attributes in
  `cadastral_parcels.pmtiles`):
  - For: no extra requests and no joins, the fastest.
  - Against: every new variable or year means rebuilding a 2.2 GB file. It can't do options or
    ratios computed on the server.
  - Fits if cadastral data is a few stable attributes, updated once a year.

Whichever it is:

- **A global legend**: quantiles over all parcels (or the municipality), sent apart (e.g.
  `/observations/stats`). Quantiles of what's on screen would change the colours while panning.
- **Painting**: the same as now, values joined by `id` (`promoteId`) through `feature-state`, added as
  tiles arrive.
- **API and MCP**: `within` by section or municipality still serves queries and rankings. For painting
  the map, the tile is a better unit than the section.

Leaning: **C** if cadastral variables are few and fixed, **B** if there will be many, or with options
like the other layers.
