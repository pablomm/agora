# Agora API

The catalogue and the data, for the web (REST) and for agents (MCP), in one FastAPI app over the
same services.

```
platform ──REST──▶ api/ (FastAPI)  routes/  ─┐
agents   ──MCP───▶                 mcp/     ─┤─▶ services/ ─┬─▶ SQLite: catalogue, places, search
                                              │              └─▶ DuckDB: values, read from the pipelines' Parquet
```

- **Catalogue (SQLite)**: `data/catalog.sqlite`, built from the pipelines: their `catalog.json`
  files (datasets, dimensions, variables) and their outputs (territorial units with their bounding
  boxes, and which levels and years each dataset really has on disk). Not in git: rebuild it.
- **Values (DuckDB)**: read straight from `pipelines/data/processed/`, never copied.
- No authentication yet; CORS is open, for the local web.

## Setup and running

```sh
python3.13 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m agora_api.catalog.build        # after the pipelines; again whenever they change
.venv/bin/uvicorn agora_api.main:app --port 8000   # REST on http://localhost:8000, MCP on /mcp
.venv/bin/python -m pytest                         # against the real catalogue and data
```

Interactive docs: http://localhost:8000/docs.

## Variables

A variable (`population`, `population_age_share`…) is defined in a pipeline's
`catalog.json` as one or more **facets**: a dataset, a numerator filter (dimension → code, or a
list of codes summed) and, for ratios, a denominator filter; value = numerator / denominator ×
scale. When a variable has several sources (population: official figures and census), each level
has a default facet, and series return each source apart (never joined).

Datasets are yearly (period `2025`) or monthly (period `202509`, SEPE's registers); facets say
their `frequency`. A ratio's denominator can come from another, yearly dataset
(`{"dataset": …, "filter": …}`): each month is divided by that dataset's value for its year (the
latest year for later months), so the facet covers months from that dataset's first year.

A variable can have **options**: dimensions the user picks, which its facets refer to as
`"$dimension"`. `population` takes a sex (total, men, women); `population_age_share` takes a
range of five-year age groups, summed (`Y0T4..Y10T14` = 0 to 14). REST takes them as
`option=sex:female` or `option=age:Y0T4..Y10T14` (repeat for several); MCP tools as
`options={"age": "Y0T4..Y10T14"}`. Options left out take the variable's default, and results
carry the choice in their label ("Población · Mujeres", "Proporción de población por edad · De 0 a 14
años").

A share can say it's another measure of a count (`measure_of`: `population_age_share` of
`population_by_age`): both stay variables of their own here, and the web shows them as one layer
with a Número / % switch. They must share topic and option dimensions (checked when building).
A dimension can be tied to a classification: `"classification": {"id", "level"}` when its values
are that level's codes (labels come from the classification), `"groups_of": "<classification>"`
when they group its codes through the correspondences. Both are checked when building, and
`/classifications/{id}/{code}` lists the dimensions that hold a code.

Datasets carry tags: any a pipeline's `catalog.json` gives (`"tags": [...]`), and those found when
building: `imputed` (a cell on disk with `origin = imputed`), `derived` (computed from other
datasets), `experimental` (an experimental statistic), `single_edition` (one period only) and
`no_license` (none known: listed, but its files aren't served).

Datasets are of three kinds. **Statistics** (a `measure` in the `catalog.json`): values by unit
and period, a file per level, which variables are computed from. **Geometries** (a `geometry`):
boundaries, census sections, cadastre, postal codes, with their files: one per edition
(`{year}`), per province (`{province}`, labelled after the province most of the rows are in), or
one; an output's `"rows": {"source": "navarra"}` keeps a dataset's rows of files it shares with
others. **Reference** tables: each classification (its items) and their correspondences, and
`territorial_units` (every unit's codes, names, the units it's in and bounding box, a file per
level), written next to the catalogue when building.

Every dataset carries, in its `catalog.json`, a `description` (what it measures, what it's for and
how to read it) and `processing` notes (how it was made: sources joined, imputation, checks), both
`{es, en}`, `keywords` (`{es: [...], en: [...]}`) and, for geometries and reference tables, its
`topics`; the fields of geometries describe themselves in both languages too. Licenses are entities
of their own, in `pipelines/licenses.json` (title, summary, what they allow, require and limit, in
both languages): a dataset's license names one by `id`, with its own attribution, and the build
fails on an id that isn't there. Each file a dataset has whole carries its sha256, reused from the
previous build while the file is unchanged.

For each dataset's page, the catalogue also keeps its measure (statistics: unit and aggregation),
its publisher's URL, what its pipeline's run says (the output's `meta.json`: when it was made and
its source downloaded, the source's URL and tables, and its checks against what's published), and
for geometries the vector tile layer that draws them (`"tiles"` in the `catalog.json`), their
extent, and a focus (the municipality with most rows) for layers only drawn up close.

A variable whose values are above or below zero (a gap between two groups) says
`"palette": "diverging"`: the web colors it with two hues and gray around zero.

## REST

| Endpoint | Returns |
|---|---|
| `GET /catalog` | Levels (with their units), topics, variables (with each facet's levels and years), datasets (with their levels, years, units per level and tags), dimensions |
| `GET /variables/{id}` | One variable |
| `GET /observations?variable&level&period&facet&within&option&change` | `{entity_id: value}` for every unit of a level, plus quantiles for a legend; `within` limits it to the units inside another (e.g. `es:ine:prov:28`); `change=true` gives each unit's change against the year before (the same month for monthly data): % for counts, a difference for the rest (points for rates) |
| `GET /rank?variable&level&period&within&top&ascending&change` | Highest (or lowest) units, or changes |
| `GET /classifications` | Statistical classifications (CNAE-2025, CNAE-2009, CNO-11, CNED-2014 A and F, CPA 2.2): ids, levels, sizes |
| `GET /classifications/{id}?level&parent&q&limit` | A classification's items: of a level, under a code, or matching text (accents don't matter) |
| `GET /classifications/{id}/{code}` | One code: label, ancestors, children, and correspondences to and from other classifications (CNAE-2009 ↔ 2025, CNO-11 → ISCO-08, CNED-A → ISCED-A, census education levels → CNED-A) |
| `GET /search?q&level` | Places by name, accents ignored (autonomous communities, provinces, municipalities) |
| `GET /entities/{id}` | A unit, its ancestors and children |
| `GET /entities/{id}/value?variable&period` | One value |
| `GET /entities/{id}/series?variable` | Values over the years, per source |
| `GET /entities/{id}/breakdown?dataset&period` | Every cell of a dataset for the unit (population pyramid…) |
| `GET /datasets?q&kind` | Datasets: statistics (dimensions, frequency, levels with years), geometries and reference tables (what their rows are, as of when, files, rows); tags and whether they can be downloaded |
| `GET /datasets/{id}` | A dataset's columns (with what they mean), each dimension's codes and labels (statistics), and its files with rows and size (statistics: one per level, with its periods and units) |
| `GET /datasets/{id}/{file}/head?limit` | The first rows of a file (up to 100), as stored: geometries as the start of their WKT |
| `GET /licenses`, `GET /licenses/{id}` | The licenses: what each allows, requires and limits, and its datasets |
| `GET /datasets/{id}/{file}.{parquet\|csv}?period&within&entity&filter&labels` | One of the dataset's files (a level, an edition, a province…), as it is or a slice: statistics by periods, units inside another, some units and `filter=dimension:code` (repeatable), with `labels=true` adding `<dimension>_label` columns; the rest by `filter=column:value`. Geometries keep their GeoParquet metadata, and go as WKT in CSV. Answers HEAD and ranges, so DuckDB reads it straight from the URL; 403 for a dataset whose license isn't known |

Unknown variables, units or years answer 404 with the reason; impossible requests (a level inside
a smaller one) answer 400.

## MCP

The same data as tools for agents, at `http://localhost:8000/mcp` (streamable HTTP), or over stdio
with `python -m agora_api.mcp`. Results are self-explaining: labels, units, year, source and its
attribution; rankings and comparisons are computed on the server. Lists are short by default, but
have no cap: `limit`, `top` or `children` set to null return everything. Whole tables don't go
through the model: `download_dataset` hands it a link to the file, served by the REST API at
`AGORA_PUBLIC_URL` (default `http://localhost:8000`), to read with its own tools.

| Tool | |
|---|---|
| `search_entities(query, level?, limit?)` | Places by name → ids |
| `describe_entity(entity_id, children?)` | What it is, what it's inside, what it contains |
| `list_variables(topic?)` | Variables, units, and per source the levels and years |
| `get_value(entity_id, variable, year?)` | One value, with its source |
| `get_series(entity_id, variable)` | Values over the years, per source |
| `get_breakdown(entity_id, dataset, year?)` | A full split (pyramid, nationality), with labels |
| `rank(variable, level, year?, within?, top?, ascending?)` | Top places, optionally inside another |
| `compare(entity_ids, variable, year?)` | The same variable for several places |
| `classification(id, code?, query?, level?, limit?)` | Classification items, or one code with its correspondences |
| `list_datasets(query?)` | The datasets the variables come from |
| `describe_dataset(dataset)` | Columns, codes and labels, rows and size per level |
| `download_dataset(dataset, level, periods?, within?, entity_ids?, filters?, format?, labels?)` | A link to the file (or a slice), its rows and columns, and how to read it |

Expected failures (unknown place, no data that year) reach the agent with their message.

To use it from Claude Code, with the API running:

```sh
claude mcp add --transport http agora http://localhost:8000/mcp
```
