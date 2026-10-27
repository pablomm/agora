"""
Datasets as files, for agents (or anyone) to analyse on their own: any dataset's file as it is
(a statistical dataset's level, a geometry's edition or province, a classification…), or a slice
of it in Parquet or CSV. Statistics slice by periods, places and dimension codes, optionally with
each code's label next to it; the rest by any column's values. Geometries keep their GeoParquet
metadata in Parquet, and go as WKT in CSV.
"""

import hashlib
import json
import os
import tempfile
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlencode

from agora_api.config import PUBLIC_URL
from agora_api.services import catalog, data, db
from agora_api.services.db import NotFound, query

FORMATS = {"parquet": "application/vnd.apache.parquet", "csv": "text/csv"}

#: Where slices are made and kept for a while: readers like DuckDB fetch a file in several ranged
#: requests, so each one must find the slice already made.
CACHE_DIR = Path(tempfile.gettempdir()) / "agora-downloads"
CACHE_SECONDS = 3600


class NotDownloadable(PermissionError):
    """A dataset whose license isn't known or doesn't allow redistributing it: listed, but its files aren't handed out."""


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def _levels(source: dict) -> list[str]:
    """A statistical dataset's levels, from census sections up."""
    return [level for level in catalog.level_ids() if level in source["coverage"]]


def _type(column_type: str) -> str:
    """A column's type, short: geometries carry their whole CRS in DuckDB's."""
    return "GEOMETRY (EPSG:4326)" if column_type.startswith("GEOMETRY") else column_type


def listing(text: str | None = None, kind: str | None = None) -> list[dict]:
    """
    Every dataset (or those of a kind, or whose id, title, dimensions or what its rows are have
    every word of `text`), briefly.
    """
    words = _fold(text or "").split()
    out = []
    for source in catalog.datasets().values():
        if kind and source["kind"] != kind:
            continue
        haystack = _fold(" ".join([source["id"], source["title"], source["kind"], source["entity_type"] or "", *source["dimensions"]]))
        if not all(word in haystack for word in words):
            continue
        entry = {"id": source["id"], "title": source["title"], "kind": source["kind"], "publisher": source["publisher"]}
        if source["kind"] == "statistics":
            entry |= {
                "frequency": source["frequency"],
                "dimensions": source["dimensions"],
                "levels": {level: f"{min(source['coverage'][level])}–{max(source['coverage'][level])}" for level in _levels(source)},
            }
        else:
            entry |= {"rows_are": source["entity_type"], "as_of": (source["validity"] or {}).get("as_of"), "files": len(source["files"]), "rows": sum(file["rows"] for file in source["files"])}
        out.append({**entry, "tags": source["tags"], "downloadable": source["downloadable"]})
    return out


def describe(dataset_id: str) -> dict:
    """
    What a dataset's files hold: their columns (with what each means, where the pipeline says),
    each dimension's codes and labels (statistics), and each file's rows and size (and, for
    statistics, a file per level: its periods and units).
    """
    source = catalog.dataset(dataset_id)
    dimensions = catalog.dimensions()
    units = _units_by_period(dataset_id) if source["kind"] == "statistics" else {}
    first = catalog.file_path(source["files"][0]["path"]) if source["files"] else None
    columns = {row["column_name"]: _type(row["column_type"]) for row in query(f"DESCRIBE SELECT * FROM read_parquet('{str(first).replace(chr(39), chr(39) * 2)}')")} if first else {}
    files = []
    for entry in source["files"]:
        file = {"name": entry["name"], "label": entry["label"], "rows": entry["rows"], "bytes": entry["bytes"], "sha256": entry["sha256"]}
        if source["kind"] == "statistics":
            file |= {"periods": source["coverage"][entry["name"]], "units": source["units"].get(entry["name"]), "units_by_period": units.get(entry["name"], {})}
        files.append(file)
    out = {
        key: source[key]
        for key in (
            "id", "title", "kind", "pipeline", "publisher", "publisher_url", "license", "source", "validity", "entity_type", "frequency",
            "measure", "base_level", "tags", "downloadable", "run", "tiles", "extent", "focus", "description", "processing", "keywords", "topics",
        )
        if source[key] is not None
    }
    out["columns"] = columns
    if source["fields"]:
        out["fields"] = {field["name"]: field.get("description") for field in source["fields"]}
    if source["kind"] == "statistics":
        out["dimensions"] = [
            {"id": dimension, "label": dimensions[dimension]["label"], "values": {value["code"]: value["label"] for value in dimensions[dimension]["values"]}}
            for dimension in source["dimensions"]
        ]
    out["files"] = files
    return out


def _units_by_period(dataset_id: str) -> dict[str, dict[int, int]]:
    """How many units a statistical dataset has data for, per level and period."""
    out: dict[str, dict[int, int]] = {}
    with db.catalog() as connection:
        for row in connection.execute("SELECT level, period, entities FROM coverage WHERE dataset_id = ? ORDER BY period", [dataset_id]):
            out.setdefault(row["level"], {})[row["period"]] = row["entities"]
    return out


def _select(
    dataset_id: str,
    file: str,
    periods: list[int] | None,
    within: str | None,
    entity_ids: list[str] | None,
    filters: dict[str, str | list[str]] | None,
    labels: bool,
) -> tuple[str, list, bool, Path]:
    """The SQL for a slice of a dataset's file, its parameters, whether it's all of the file as it is, and the file."""
    source = catalog.dataset(dataset_id)
    if not source["downloadable"]:
        reason = "its license isn't known" if not source["license"] else "its license doesn't allow redistributing it"
        raise NotDownloadable(f"{dataset_id} can't be downloaded from Agora: {reason} (its processing notes say where to get it)")
    entry = catalog.dataset_file(dataset_id, file)
    location = catalog.file_path(entry["path"])
    path = str(location).replace("'", "''")
    statistics = source["kind"] == "statistics"
    if not statistics and (periods or within or entity_ids or labels):
        raise ValueError(f"{dataset_id} isn't statistics: slice it with filters on its columns (periods, within, entities and labels are for statistics)")
    columns, joins, parameters, conditions = ["t.*"], [], [], []
    if labels:
        for index, dimension in enumerate(source["dimensions"]):
            pairs = catalog.dimension_labels(dimension)
            joins.append(f'LEFT JOIN (VALUES {",".join(["(?, ?)"] * len(pairs))}) AS l{index}(lc, lv) ON l{index}.lc = t."{dimension}"')
            columns.append(f'l{index}.lv AS "{dimension}_label"')
            parameters.extend(item for pair in pairs.items() for item in pair)
    # The file's rows that are the dataset's (one classification of the items of all of them…).
    for column, value in (entry["filter"] or {}).items():
        conditions.append(f't."{column}" = ?')
        parameters.append(value)
    if periods:
        available = source["coverage"][file]
        missing = [period for period in periods if period not in available]
        if missing:
            raise NotFound(f"No data for {missing} at level {file} (available: {available[0]}–{available[-1]})")
        conditions.append(f"t.period IN ({','.join('?' * len(periods))})")
        parameters.extend(periods)
    if within:
        conditions.append(data._within(within, file, parameters))
    if entity_ids:
        conditions.append(f"t.entity_id IN ({','.join('?' * len(entity_ids))})")
        parameters.extend(entity_ids)
    if filters:
        if statistics:
            allowed = source["dimensions"]
        else:
            described = query(f"DESCRIBE SELECT * FROM read_parquet('{path}')")
            allowed = [row["column_name"] for row in described if not row["column_type"].startswith(("GEOMETRY", "STRUCT"))]
        conditions.append(data._condition(filters, allowed, parameters))
    where = " AND ".join(conditions) or "TRUE"
    sql = f"SELECT {', '.join(columns)} FROM read_parquet('{path}') AS t {' '.join(joins)} WHERE {where}"
    return sql, parameters, not labels and not conditions, location


def shape(dataset_id: str, file: str, periods=None, within=None, entity_ids=None, filters=None, labels=False) -> dict:
    """A slice's rows and columns, without making its file (and, by asking, that it's a valid one)."""
    sql, parameters, _, _ = _select(dataset_id, file, periods, within, entity_ids, filters, labels)
    columns = {row["column_name"]: _type(row["column_type"]) for row in query(f"DESCRIBE {sql}", parameters)}
    return {"rows": query(f"SELECT count(*) AS n FROM ({sql})", parameters)[0]["n"], "columns": columns}


#: The longest text a preview cell shows (a geometry's WKT is cut).
PREVIEW_TEXT = 120


def head(dataset_id: str, file: str, limit: int = 20) -> dict:
    """
    The first rows of one of a dataset's files, as they are on disk, to look at before
    downloading it: geometries as the start of their WKT, nested values as text.
    """
    sql, parameters, _, _ = _select(dataset_id, file, None, None, None, None, False)
    described = query(f"DESCRIBE {sql}", parameters)
    columns = []
    for row in described:
        name, kind = row["column_name"], row["column_type"]
        quoted = '"' + name.replace('"', '""') + '"'
        if kind.startswith(("GEOMETRY", "STRUCT", "MAP", "LIST")) or kind.endswith("[]"):
            columns.append(f"left(CAST({quoted} AS VARCHAR), {PREVIEW_TEXT}) AS {quoted}")
        elif kind.startswith(("DATE", "TIMESTAMP", "TIME")):
            columns.append(f"CAST({quoted} AS VARCHAR) AS {quoted}")
        else:
            columns.append(quoted)
    rows = query(f"SELECT {', '.join(columns)} FROM ({sql}) LIMIT ?", [*parameters, min(max(limit, 1), 100)])
    return {"columns": {row["column_name"]: _type(row["column_type"]) for row in described}, "rows": rows}


def _prune() -> None:
    """Removes the slices not asked for in the last CACHE_SECONDS."""
    now = time.time()
    for path in CACHE_DIR.glob("*"):
        try:
            if now - path.stat().st_atime > CACHE_SECONDS:
                path.unlink()
        except FileNotFoundError:
            pass


def export(dataset_id: str, file: str, format: str = "parquet", periods=None, within=None, entity_ids=None, filters=None, labels=False) -> Path:
    """
    A file with the slice: the dataset's own Parquet when it's all of it, otherwise one made in
    CACHE_DIR (named after what was asked and the source file's version, so it's made once).
    """
    if format not in FORMATS:
        raise ValueError(f"Format {format!r} isn't one of {list(FORMATS)}")
    sql, parameters, whole, source = _select(dataset_id, file, periods, within, entity_ids, filters, labels)
    if whole and format == "parquet":
        return source
    CACHE_DIR.mkdir(exist_ok=True)
    _prune()
    key = json.dumps([sql, parameters, format, source.stat().st_mtime_ns], default=str)
    path = CACHE_DIR / f"{dataset_id}-{file}-{hashlib.sha256(key.encode()).hexdigest()[:16]}.{format}"
    if path.exists():
        # Only its access time: the modification time makes the ETag, which mustn't change between ranges.
        os.utime(path, (time.time(), path.stat().st_mtime))
        return path
    # Made under another name and moved, so a request at the same time never reads half a file.
    partial = path.with_suffix(f".{os.getpid()}.{time.monotonic_ns()}.partial")
    options = "FORMAT parquet, COMPRESSION zstd" if format == "parquet" else "FORMAT csv, HEADER"
    try:
        query(f"COPY ({sql}) TO '{partial}' ({options})", parameters)
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def url(dataset_id: str, file: str, format: str = "parquet", periods=None, within=None, entity_ids=None, filters=None, labels=False) -> str:
    """Where the API serves a slice (see the /datasets/{dataset}/{file}.{format} route)."""
    parameters: list[tuple[str, str]] = [("period", str(period)) for period in periods or []]
    if within:
        parameters.append(("within", within))
    parameters += [("entity", entity_id) for entity_id in entity_ids or []]
    for dimension, codes in (filters or {}).items():
        parameters += [("filter", f"{dimension}:{code}") for code in (codes if isinstance(codes, list) else [codes])]
    if labels:
        parameters.append(("labels", "true"))
    query_string = f"?{urlencode(parameters)}" if parameters else ""
    return f"{PUBLIC_URL}/datasets/{quote(dataset_id)}/{quote(file)}.{format}{query_string}"


def parse_filters(entries: list[str] | None) -> dict[str, list[str]]:
    """Filters given as dimension:code (repeated, for several codes of a dimension)."""
    out: dict[str, list[str]] = {}
    for entry in entries or []:
        dimension, separator, code = entry.partition(":")
        if not separator:
            raise ValueError(f"Filter {entry!r} isn't dimension:code")
        out.setdefault(dimension, []).append(code)
    return out
