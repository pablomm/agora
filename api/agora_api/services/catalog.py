"""The catalogue: variables (with where and when they exist), datasets, dimensions, levels."""

import json
from functools import lru_cache
from pathlib import Path

from agora_api.config import CATALOG_DB, PROCESSED_DIR
from agora_api.services.db import NotFound, catalog


@lru_cache
def levels() -> list[dict]:
    """The levels, with how many units each has in the current cartography (`units`)."""
    with catalog() as db:
        return db.execute(
            "SELECT id, rank, label_es AS label, (SELECT count(*) FROM entities WHERE entities.level = levels.id) AS units FROM levels ORDER BY rank"
        ).fetchall()


def level_ids() -> list[str]:
    return [level["id"] for level in levels()]


@lru_cache
def datasets() -> dict[str, dict]:
    with catalog() as db:
        rows = db.execute("SELECT * FROM datasets").fetchall()
        coverage = db.execute("SELECT dataset_id, level, period, entities FROM coverage ORDER BY period").fetchall()
        files = db.execute("SELECT dataset_id, name, label, path, filter, rows, bytes FROM dataset_files ORDER BY dataset_id, position").fetchall()
    out = {}
    for row in rows:
        for key in ("license", "source", "validity", "fields"):
            row[key] = json.loads(row[key] or "null")
        row["dimensions"] = json.loads(row["dimensions"])
        row["tags"] = json.loads(row["tags"])
        row["downloadable"] = bool(row["downloadable"])
        row["files"] = []
        row["coverage"] = {}
        # The most units a level has data for in any period (fewer than the level has: partial coverage).
        row["units"] = {}
        out[row["id"]] = row
    for entry in coverage:
        dataset = out[entry["dataset_id"]]
        dataset["coverage"].setdefault(entry["level"], []).append(entry["period"])
        dataset["units"][entry["level"]] = max(dataset["units"].get(entry["level"], 0), entry["entities"])
    for entry in files:
        entry["filter"] = json.loads(entry["filter"] or "null")
        out[entry.pop("dataset_id")]["files"].append(entry)
    return out


def dataset(dataset_id: str) -> dict:
    try:
        return datasets()[dataset_id]
    except KeyError:
        raise NotFound(f"Unknown dataset {dataset_id!r}") from None


def dataset_path(dataset_id: str, level: str) -> str:
    template = dataset(dataset_id)["path_template"]
    return str(PROCESSED_DIR / template.replace("processed/", "", 1).format(level=level))


def file_path(path: str) -> Path:
    """Where a dataset file is: the pipelines' outputs (processed/…), or next to the catalogue."""
    if path.startswith("processed/"):
        return PROCESSED_DIR / path.removeprefix("processed/")
    return CATALOG_DB.parent / path


def dataset_file(dataset_id: str, name: str) -> dict:
    """One of a dataset's files, by name (a level for statistics)."""
    source = dataset(dataset_id)
    for entry in source["files"]:
        if entry["name"] == name:
            return entry
    raise NotFound(f"{dataset_id} has no file {name!r} (its files: {', '.join(entry['name'] for entry in source['files'])})")


@lru_cache
def dimensions() -> dict[str, dict]:
    with catalog() as db:
        rows = db.execute("SELECT id, label_es AS label, classification, groups_of FROM dimensions").fetchall()
        values = db.execute("SELECT dimension_id, code, label, parent FROM dimension_values ORDER BY dimension_id, position").fetchall()
    out = {row["id"]: {**row, "values": []} for row in rows}
    for value in values:
        out[value["dimension_id"]]["values"].append({"code": value["code"], "label": value["label"], "parent": value["parent"]})
    return out


@lru_cache
def variables() -> dict[str, dict]:
    with catalog() as db:
        rows = db.execute(
            "SELECT id, topic_id AS topic, label_es AS label, description_es AS description, unit, kind, scale, default_facet, options, measure_of, palette FROM variables"
        ).fetchall()
        facets = db.execute(
            "SELECT variable_id, id, label_es AS label, dataset_id AS dataset, numerator, denominator FROM variable_facets ORDER BY variable_id, position"
        ).fetchall()
    out = {}
    for row in rows:
        row["default_facet"] = json.loads(row["default_facet"] or "{}")
        # Each option with its dimension's label and its values' labels, in order.
        row["options"] = [
            {
                **option,
                "range": option.get("range", False),
                # As the catalogue says; None: the web picks by whether the values fit side by side.
                "control": option.get("control"),
                "label": dimensions()[option["dimension"]]["label"],
                "values": [{"code": code, "label": dimension_labels(option["dimension"])[code], "parent": dimension_parents(option["dimension"])[code]} for code in option["values"]],
            }
            for option in json.loads(row["options"] or "[]")
        ]
        row["facets"] = []
        out[row["id"]] = row
    for facet in facets:
        variable = out[facet.pop("variable_id")]
        facet["numerator"] = json.loads(facet["numerator"])
        facet["denominator"] = json.loads(facet["denominator"]) if facet["denominator"] else None
        source = dataset(facet["dataset"])
        # Where and when the facet exists: its dataset's coverage, as found on disk (and, with a
        # denominator from another dataset, only from that one's first year on).
        facet["frequency"] = source["frequency"]
        facet["coverage"] = source["coverage"]
        if facet["denominator"] and "dataset" in facet["denominator"]:
            other = dataset(facet["denominator"]["dataset"])["coverage"]
            facet["coverage"] = {
                level: [period for period in periods if other.get(level) and year_of(period, source["frequency"]) >= min(other[level])]
                for level, periods in source["coverage"].items()
            }
            facet["coverage"] = {level: periods for level, periods in facet["coverage"].items() if periods}
        facet["license"] = source["license"]
        facet["dataset_title"] = source["title"]
        variable["facets"].append(facet)
    return out


def year_of(period: int, frequency: str) -> int:
    """The year of a period (202509 → 2025 for monthly data)."""
    return period // 100 if frequency == "monthly" else period


def dimension_labels(dimension_id: str) -> dict[str, str]:
    return {value["code"]: value["label"] for value in dimensions()[dimension_id]["values"]}


def dimension_parents(dimension_id: str) -> dict[str, str | None]:
    return {value["code"]: value["parent"] for value in dimensions()[dimension_id]["values"]}


def variable(variable_id: str) -> dict:
    try:
        return variables()[variable_id]
    except KeyError:
        raise NotFound(f"Unknown variable {variable_id!r}; see the catalogue for the available ones") from None


def facet_for(variable_id: str, level: str, facet_id: str | None = None) -> dict:
    """The facet to use for a variable at a level: the one asked for, the level's default, or the only one there."""
    spec = variable(variable_id)
    available = [facet for facet in spec["facets"] if level in facet["coverage"]]
    if facet_id:
        for facet in available:
            if facet["id"] == facet_id:
                return facet
        raise NotFound(f"{variable_id} has no facet {facet_id!r} at level {level}")
    if not available:
        raise NotFound(f"{variable_id} isn't available at level {level}")
    default = spec["default_facet"].get(level)
    return next((facet for facet in available if facet["id"] == default), available[0])


def summary() -> dict:
    """The whole catalogue, as the web and agents read it."""
    return {
        "levels": levels(),
        "topics": topics(),
        "variables": list(variables().values()),
        "datasets": [
            {
                **{key: value for key, value in entry.items() if key not in ("path_template", "files")},
                "files": [{key: value for key, value in file.items() if key not in ("path", "filter")} for file in entry["files"]],
            }
            for entry in datasets().values()
        ],
        "dimensions": list(dimensions().values()),
    }


@lru_cache
def topics() -> list[dict]:
    with catalog() as db:
        return db.execute("SELECT id, label_es AS label FROM topics ORDER BY position, id").fetchall()
