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
A variable whose values are above or below zero (a gap between two groups) says
`"palette": "diverging"`: the web colors it with two hues and gray around zero.

## REST

| Endpoint | Returns |
|---|---|
| `GET /catalog` | Levels, topics, variables (with each facet's levels and years), datasets, dimensions |
| `GET /variables/{id}` | One variable |
| `GET /observations?variable&level&period&facet&within&option` | `{entity_id: value}` for every unit of a level, plus quantiles for a legend; `within` limits it to the units inside another (e.g. `es:ine:prov:28`) |
| `GET /rank?variable&level&period&within&top&ascending` | Highest (or lowest) units |
| `GET /search?q&level` | Places by name, accents ignored (autonomous communities, provinces, municipalities) |
| `GET /entities/{id}` | A unit, its ancestors and children |
| `GET /entities/{id}/value?variable&period` | One value |
| `GET /entities/{id}/series?variable` | Values over the years, per source |
| `GET /entities/{id}/breakdown?dataset&period` | Every cell of a dataset for the unit (population pyramid…) |

Unknown variables, units or years answer 404 with the reason; impossible requests (a level inside
a smaller one) answer 400.

## MCP

The same data as tools for agents, at `http://localhost:8000/mcp` (streamable HTTP), or over stdio
with `python -m agora_api.mcp`. Results are small and self-explaining: labels, units, year, source
and its attribution; rankings and comparisons are computed on the server, so an agent never gets
thousands of rows.

| Tool | |
|---|---|
| `search_entities(query, level?)` | Places by name → ids |
| `describe_entity(entity_id)` | What it is, what it's inside, what it contains |
| `list_variables(topic?)` | Variables, units, and per source the levels and years |
| `get_value(entity_id, variable, year?)` | One value, with its source |
| `get_series(entity_id, variable)` | Values over the years, per source |
| `get_breakdown(entity_id, dataset, year?)` | A full split (pyramid, nationality), with labels |
| `rank(variable, level, year?, within?, top?, ascending?)` | Top places, optionally inside another |
| `compare(entity_ids, variable, year?)` | The same variable for several places |

Expected failures (unknown place, no data that year) reach the agent with their message.

To use it from Claude Code, with the API running:

```sh
claude mcp add --transport http agora http://localhost:8000/mcp
```
