"""The catalogue: variables (with where and when they exist), datasets, dimensions, levels."""

import json
from functools import lru_cache

from agora_api.config import PROCESSED_DIR
from agora_api.services.db import NotFound, catalog


@lru_cache
def levels() -> list[dict]:
    with catalog() as db:
        return db.execute("SELECT id, rank, label_es AS label FROM levels ORDER BY rank").fetchall()


def level_ids() -> list[str]:
    return [level["id"] for level in levels()]


@lru_cache
def datasets() -> dict[str, dict]:
    with catalog() as db:
        rows = db.execute("SELECT * FROM datasets").fetchall()
        coverage = db.execute("SELECT dataset_id, level, period FROM coverage ORDER BY period").fetchall()
    out = {}
    for row in rows:
        row["license"] = json.loads(row["license"] or "null")
        row["source"] = json.loads(row["source"] or "null")
        row["dimensions"] = json.loads(row["dimensions"])
        row["coverage"] = {}
        out[row["id"]] = row
    for entry in coverage:
        out[entry["dataset_id"]]["coverage"].setdefault(entry["level"], []).append(entry["period"])
    return out


def dataset(dataset_id: str) -> dict:
    try:
        return datasets()[dataset_id]
    except KeyError:
        raise NotFound(f"Unknown dataset {dataset_id!r}") from None


def dataset_path(dataset_id: str, level: str) -> str:
    template = dataset(dataset_id)["path_template"]
    return str(PROCESSED_DIR / template.replace("processed/", "", 1).format(level=level))


@lru_cache
def dimensions() -> dict[str, dict]:
    with catalog() as db:
        rows = db.execute("SELECT id, label_es AS label FROM dimensions").fetchall()
        values = db.execute("SELECT dimension_id, code, label FROM dimension_values ORDER BY dimension_id, position").fetchall()
    out = {row["id"]: {**row, "values": []} for row in rows}
    for value in values:
        out[value["dimension_id"]]["values"].append({"code": value["code"], "label": value["label"]})
    return out


@lru_cache
def variables() -> dict[str, dict]:
    with catalog() as db:
        rows = db.execute(
            "SELECT id, topic_id AS topic, label_es AS label, description_es AS description, unit, kind, scale, default_facet, options FROM variables"
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
                "label": dimensions()[option["dimension"]]["label"],
                "values": [{"code": code, "label": dimension_labels(option["dimension"])[code]} for code in option["values"]],
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
        # Where and when the facet exists: its dataset's coverage, as found on disk.
        facet["coverage"] = source["coverage"]
        facet["license"] = source["license"]
        facet["dataset_title"] = source["title"]
        variable["facets"].append(facet)
    return out


def dimension_labels(dimension_id: str) -> dict[str, str]:
    return {value["code"]: value["label"] for value in dimensions()[dimension_id]["values"]}


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
            {key: value for key, value in entry.items() if key != "path_template"} for entry in datasets().values()
        ],
        "dimensions": list(dimensions().values()),
    }


@lru_cache
def topics() -> list[dict]:
    with catalog() as db:
        return db.execute("SELECT id, label_es AS label FROM topics ORDER BY id").fetchall()
