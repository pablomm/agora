"""
Agora as an MCP server: tools for an agent to find places, see what data there is about them, and
get values, series, breakdowns and rankings. Results are small and self-explaining (labels, units,
year, source and how to cite it): an agent never gets thousands of rows.
"""

import functools

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from agora_api.services import catalog, classifications, data, downloads, entities

INSTRUCTIONS = """\
Agora: Spanish statistics by territory (autonomous communities, provinces, municipalities, census
districts and sections), from official sources (INE…).

Workflow: find the place's id with search_entities (ids look like es:ine:mun:28079), see which
variables exist with list_variables, then use get_value, get_series, get_breakdown, rank or
compare. Values come with their year, unit and source: cite the source (its attribution) when
you use them. Some variables have several sources (facets), e.g. population from the official
register figures (long series) and from the annual census (more detail); results say which one
was used. Some variables have options (list_variables shows them): pass them as `options`, e.g.
{"sex": "female"} or, for a range of age groups, {"age": "Y0T4..Y10T14"} (0 to 14 years).

Every table is a dataset: statistics (values by unit and period, which variables are computed
from), geometries (boundaries of sections, municipalities…, cadastral parcels, postal codes) and
reference tables (classifications like CNAE, the territorial units with codes, names and what
they're in). To analyse one on your own, find it with list_datasets, see its columns and files with
describe_dataset, and get a link to a file (all of it or a slice, Parquet or CSV) with
download_dataset; read it with your own tools (DuckDB, pandas, GeoPandas…).

Periods are years (2025) for yearly data and YYYYMM (202509) for monthly data (employment
registers): list_variables says each source's frequency. Without a period, the latest is used.
"""

server = MCPServer("agora", instructions=INSTRUCTIONS)


def tool(function):
    """A tool whose expected failures (unknown place or variable, no data that year, bad arguments)
    reach the model with their message, so it can correct the call."""

    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (LookupError, ValueError, PermissionError) as error:
            raise ToolError(str(error)) from error

    return server.tool()(wrapper)


def _source(facet: dict) -> dict:
    license_ = facet.get("license") or {}
    return {"source": facet["dataset_title"], "facet": facet["id"], "attribution": license_.get("attribution"), "license": license_.get("id")}


@tool
def search_entities(query: str, level: str | None = None, limit: int | None = 10) -> list[dict]:
    """Find places by name (accents don't matter). `level` narrows it to autonomous_community,
    province or municipality. Returns ids to use with the other tools; limit=null returns every match."""
    rows = entities.search(query, [level] if level else None, limit)
    return [{"id": row["id"], "name": row["name"], "level": row["level"], "inside": row["parent_name"]} for row in rows]


@tool
def describe_entity(entity_id: str, children: int | None = 50) -> dict:
    """What a place is: its level, the units it's inside, and the ones inside it (the first
    `children`; null for all of them)."""
    entity = entities.describe(entity_id, children)
    return {
        "id": entity["id"],
        "name": entity["label"],
        "level": entity["level"],
        "inside": [ancestor["label"] for ancestor in entity["ancestors"]],
        "contains": [{"id": child["id"], "name": child["label"]} for child in entity["children"]],
        "contains_total": entity["children_total"],
    }


@tool
def list_variables(topic: str | None = None) -> list[dict]:
    """The variables available, with their unit and, per source, the levels and years they cover."""
    out = []
    for variable in catalog.variables().values():
        if topic and variable["topic"] != topic:
            continue
        out.append(
            {
                "id": variable["id"],
                "label": variable["label"],
                "unit": variable["unit"],
                "options": [
                    {
                        "dimension": option["dimension"],
                        "kind": "range (first..last)" if option["range"] else "one value",
                        "values": {value["code"]: value["label"] for value in option["values"]},
                        "default": option["default"],
                    }
                    for option in variable["options"]
                ],
                "sources": [
                    {
                        "facet": facet["id"],
                        "source": facet["dataset_title"],
                        "frequency": facet["frequency"],
                        "levels": {level: f"{min(periods)}–{max(periods)}" for level, periods in facet["coverage"].items()},
                    }
                    for facet in variable["facets"]
                ],
            }
        )
    return out


@tool
def get_value(entity_id: str, variable: str, period: int | None = None, facet: str | None = None, options: dict[str, str] | None = None) -> dict:
    """One place's value of a variable in a period (a year, or YYYYMM for monthly data; the latest by default)."""
    result = data.value(entity_id, variable, period, facet, options)
    entity = entities.find(entity_id)
    return {
        "place": entity["label"] if entity else entity_id,
        "variable": result["label"],
        "period": result["period"],
        "value": round(result["value"], 2),
        "unit": result["unit"],
        **_source(result["facet"]),
    }


@tool
def get_series(entity_id: str, variable: str, facet: str | None = None, options: dict[str, str] | None = None) -> dict:
    """A place's values over the years, from each source that has it (each source is its own series:
    don't join them, they measure slightly different things)."""
    result = data.series(entity_id, variable, facet, options)
    entity = entities.find(entity_id)
    return {
        "place": entity["label"] if entity else entity_id,
        "variable": result["label"],
        "unit": result["unit"],
        "series": [
            {**_source(series), "values": {row["period"]: round(row["value"], 2) for row in series["values"]}} for series in result["facets"]
        ],
    }


@tool
def get_breakdown(entity_id: str, dataset: str, period: int | None = None) -> dict:
    """A dataset's full split for one place and year, e.g. population_sex_age (population pyramid) or
    population_sex_age_nationality (list_datasets has them all). Codes are replaced by labels."""
    result = data.breakdown(entity_id, dataset, period)
    labels = {dimension["id"]: {value["code"]: value["label"] for value in dimension["values"]} for dimension in result["dimensions"]}
    rows = [{key: (labels[key].get(value, value) if key in labels else value) for key, value in row.items()} for row in result["rows"]]
    license_ = result["license"] or {}
    return {"dataset": result["dataset_title"], "period": result["period"], "available_years": result["periods"], "attribution": license_.get("attribution"), "rows": rows}


@tool
def rank(
    variable: str,
    level: str,
    period: int | None = None,
    within: str | None = None,
    top: int | None = 10,
    ascending: bool = False,
    options: dict[str, str] | None = None,
    change: bool = False,
) -> dict:
    """The places of a level (municipality, census_section…) with the highest values of a variable
    (lowest with ascending=true), optionally only inside another place (`within`, an id); top=null
    returns every place. With change=true, ranked by change against the year before (% for counts,
    points for rates)."""
    result = data.rank(variable, level, period, within, top, ascending, options=options, change=change)
    return {
        "variable": result["label"],
        "unit": result["unit"],
        "level": result["level"],
        "period": result["period"],
        "within": result["within"],
        "out_of": result["total_units"],
        **_source(result["facet"]),
        "items": [{"rank": item["rank"], "id": item["entity_id"], "name": item["name"], "value": round(item["value"], 2)} for item in result["items"]],
    }


@tool
def classification(classification_id: str, code: str | None = None, query: str | None = None, level: int | None = None, limit: int | None = 50) -> dict:
    """Spanish statistical classifications: cnae2025 and cnae2009 (economic activities), cno11
    (occupations), cned2014_a (education levels), cned2014_f (fields of study), cpa22 (products).
    With `code`, that item with its ancestors, children and correspondences (CNAE-2009 <-> 2025,
    CNO-11 -> ISCO-08, CNED-A -> ISCED-A); otherwise items matching `query` and/or of a `level`
    (1 = the top), the first `limit` (null for all)."""
    if code:
        return classifications.item(classification_id, code)
    result = classifications.items(classification_id, level, None, query, limit)
    return {"classification": result["classification"]["title"], "total": result["total"], "items": result["items"]}


@tool
def compare(entity_ids: list[str], variable: str, period: int | None = None, options: dict[str, str] | None = None) -> list[dict]:
    """The same variable for several places, each from its level's default source."""
    out = []
    for entity_id in entity_ids:
        try:
            out.append(get_value(entity_id, variable, period, options=options))
        except (LookupError, ToolError) as error:
            out.append({"place": entity_id, "error": str(error)})
    return out


@tool
def list_datasets(query: str | None = None, kind: str | None = None) -> list[dict]:
    """The datasets, or those of a `kind` (statistics, geometry, reference) or whose id, title,
    dimensions or kind of rows have every word of `query`. Statistics say their dimensions,
    frequency and levels with years; the rest what their rows are, as of when, files and rows."""
    return downloads.listing(query, kind)


@tool
def describe_dataset(dataset: str) -> dict:
    """A dataset's columns (and what they mean), each dimension's codes and labels (statistics), and
    its files with rows and size: one per level for statistics (with its periods and units), per
    edition or province for geometries. Statistics are long: one row per unit, period and
    combination of codes, with `value`."""
    return downloads.describe(dataset)


@tool
def download_dataset(
    dataset: str,
    file: str,
    periods: list[int] | None = None,
    within: str | None = None,
    entity_ids: list[str] | None = None,
    filters: dict[str, str | list[str]] | None = None,
    format: str = "parquet",
    labels: bool = False,
) -> dict:
    """A link to download one of a dataset's files (describe_dataset lists them: the level for
    statistics, like census_section; the edition, province or name for the rest), to analyse it with
    your own tools: all of it or a slice. Statistics slice by `periods`, the units `within` a place,
    the `entity_ids` given and codes (`filters`, e.g. {"sex": "female"} or {"age": ["Y0T4", "Y5T9"]}),
    and labels=true adds each code's label in a <dimension>_label column; the rest by values of their
    columns (`filters`, e.g. {"province_code": "28"}). `format` is parquet (default; GeoParquet for
    geometries) or csv (geometries as WKT). The link is served by the Agora API (fetch it with curl,
    or read it straight from DuckDB, pandas or GeoPandas)."""
    if format not in downloads.FORMATS:
        raise ValueError(f"Format {format!r} isn't one of {list(downloads.FORMATS)}")
    shape = downloads.shape(dataset, file, periods, within, entity_ids, filters, labels)
    source = catalog.dataset(dataset)
    link = downloads.url(dataset, file, format, periods, within, entity_ids, filters, labels)
    reader = f"pd.read_parquet('{link}')" if format == "parquet" else f"pd.read_csv('{link}')"
    license_ = source["license"] or {}
    return {
        "url": link,
        "format": format,
        **shape,
        "read_with": [f"curl -o {dataset}_{file}.{format} '{link}'", f"duckdb.sql(\"FROM '{link}'\")", reader],
        "source": source["title"],
        "attribution": license_.get("attribution"),
        "license": license_.get("id"),
    }
