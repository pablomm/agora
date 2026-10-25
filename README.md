# Agora

Spanish statistics on the map: territories, people, organisations and contracts as entities linked
to each other and to the places they belong to. The map is one view of that data.

## Structure

| Folder | What |
|---|---|
| [`platform/`](platform/) | The web: React + TypeScript + Vite, MapLibre GL. What it does is logged in [`platform/FEATURES.md`](platform/FEATURES.md). |
| [`tileserver/`](tileserver/README.md) | [Martin](https://maplibre.org/martin/), serving the vector tiles the map draws. |
| [`pipelines/`](pipelines/README.md) | Python scripts that download and normalise the data (administrative boundaries, census, cadastre, postal codes, population…) and build the tiles. |
| [`api/`](api/README.md) | FastAPI: the catalogue (SQLite) and the data (Parquet, read with DuckDB), as REST for the web and as an MCP server for agents. |

Data isn't in the repository: the pipelines write it to `pipelines/data/` (see each pipeline's
README for its source, license and validity).

## Running it locally

```sh
# 1. Data and tiles (once, and when sources change)
cd pipelines
python3.13 -m venv .venv && .venv/bin/pip install -e .
brew install tippecanoe
# run the pipelines, then the tiles: see pipelines/README.md and pipelines/pipelines/tiles/README.md

# 2. Tile server
brew install martin
cd tileserver && martin --config martin.yaml          # http://localhost:3000

# 3. API (catalogue, data, MCP)
cd api
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m agora_api.catalog.build
.venv/bin/uvicorn agora_api.main:app --port 8000      # http://localhost:8000, MCP on /mcp

# 4. Web
cd platform && npm install && npm run dev               # http://localhost:5173
```

Without the tile server the web still opens, with the basemap only and a notice that the
boundaries can't be loaded; without the API, the map works but there are no data layers or search.

## Conventions

- Code, comments and docs in English; the interface in Spanish (`platform/src/app/copy.ts`).
- Every feature the platform ships is logged in `platform/FEATURES.md`.
