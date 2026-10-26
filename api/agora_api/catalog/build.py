"""
Builds the catalogue database (SQLite) from the pipelines: their catalog.json files (datasets,
dimensions, variables) and their outputs (territorial units, and which levels and periods each
dataset really has on disk).

    python -m agora_api.catalog.build
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import duckdb

from agora_api.config import CATALOG_DB, PIPELINES_DIR, PROCESSED_DIR

log = logging.getLogger(__name__)

LEVELS = [
    ("census_section", "Sección censal", "Census section"),
    ("census_district", "Distrito censal", "Census district"),
    ("municipality", "Municipio", "Municipality"),
    ("province", "Provincia", "Province"),
    ("autonomous_community", "Comunidad autónoma", "Autonomous community"),
    ("country", "España", "Spain"),
]
COUNTRY = ("es:country:es", "country", "es", "España", "España", None, 1, -18.17, 27.63, 4.33, 43.80)
BBOX = "bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax"

#: The territorial units' files (cartography): level, file, and how to read their names.
CENSUS_YEAR = 2026


def territorial_entities(con: duckdb.DuckDBPyConnection) -> list[tuple]:
    """(id, level, code, name, label, parent_id, searchable, west, south, east, north) for every unit of the current cartography."""
    rows = [COUNTRY]
    p = PROCESSED_DIR
    rows += con.execute(
        f"SELECT id, 'autonomous_community', ine_code, name, name, 'es:country:es', 1, {BBOX} FROM '{p}/autonomous_communities/autonomous_communities.parquet'"
    ).fetchall()
    rows += con.execute(f"SELECT id, 'province', ine_code, name, name, parent_id, 1, {BBOX} FROM '{p}/provinces/provinces.parquet'").fetchall()
    rows += con.execute(
        f"SELECT id, 'municipality', ine_code, name, name, parent_id, 1, {BBOX} FROM '{p}/municipalities/municipalities.parquet'"
    ).fetchall()
    # Census units have numbers, not names: their label carries their municipality's (IGN's) name.
    rows += con.execute(
        f"""
        SELECT d.id, 'census_district', d.ine_code, 'Distrito ' || d.district_code,
               'Distrito ' || d.district_code || ' · ' || coalesce(m.name, d.municipality_name), d.parent_id, 0,
               d.bbox.xmin, d.bbox.ymin, d.bbox.xmax, d.bbox.ymax
        FROM '{p}/census_sections/census_districts_{CENSUS_YEAR}_aligned.parquet' d
        LEFT JOIN '{p}/municipalities/municipalities.parquet' m ON m.ine_code = d.municipality_code
        """
    ).fetchall()
    rows += con.execute(
        f"""
        SELECT s.id, 'census_section', s.ine_code, 'Sección ' || s.section_code,
               'Distrito ' || s.district_code || ' · Sección ' || s.section_code || ' · ' || coalesce(m.name, s.municipality_name),
               s.parent_id, 0, s.bbox.xmin, s.bbox.ymin, s.bbox.xmax, s.bbox.ymax
        FROM '{p}/census_sections/census_sections_{CENSUS_YEAR}_aligned.parquet' s
        LEFT JOIN '{p}/municipalities/municipalities.parquet' m ON m.ine_code = s.municipality_code
        """
    ).fetchall()
    return rows


def coverage(con: duckdb.DuckDBPyConnection, dataset: str, template: str) -> list[tuple]:
    """(dataset, level, period, rows, entities) for each level file the dataset has on disk."""
    out = []
    for level, *_ in LEVELS:
        path = PROCESSED_DIR / template.replace("processed/", "", 1).format(level=level)
        if not path.exists():
            continue
        for period, rows, entities in con.execute(
            f"SELECT period, count(*), count(DISTINCT entity_id) FROM '{path}' GROUP BY period ORDER BY period"
        ).fetchall():
            out.append((dataset, level, int(period), int(rows), int(entities)))
    return out


#: How the web shows an option with one value to pick: side by side, or a dropdown for long or many values.
CONTROLS = ("segmented", "select")


def check_options(variable: dict) -> None:
    """Every "$dimension" a facet uses is one of the variable's options, and every option's default is one of its values."""
    options = {option["dimension"]: option for option in variable.get("options", [])}
    for facet in variable["facets"]:
        denominator = facet.get("denominator") or {}
        for filter_ in (facet["numerator"], denominator.get("filter", denominator) if "dataset" in denominator else denominator):
            for code in filter_.values():
                if isinstance(code, str) and code.startswith("$") and code[1:] not in options:
                    raise ValueError(f"{variable['id']}: facet {facet['id']} uses {code}, which isn't an option")
    for option in options.values():
        defaults = option["default"] if isinstance(option["default"], list) else [option["default"]]
        if not set(defaults) <= set(option["values"]):
            raise ValueError(f"{variable['id']}: the default of option {option['dimension']} isn't one of its values")
        if option.get("control", "segmented") not in CONTROLS or (option.get("control") and option.get("range")):
            raise ValueError(f"{variable['id']}: option {option['dimension']} has control {option.get('control')!r}, not one of {CONTROLS} (and ranges take none)")


def label(value: dict | str | None, lang: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.get(lang) or value.get("es")


def build(target: Path = CATALOG_DB) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".sqlite.part")
    partial.unlink(missing_ok=True)
    db = sqlite3.connect(partial)
    db.executescript(resources.files("agora_api.catalog").joinpath("schema.sql").read_text())
    con = duckdb.connect()

    db.executemany("INSERT INTO levels VALUES (?, ?, ?, ?)", [(level, rank, es, en) for rank, (level, es, en) in enumerate(LEVELS)])
    entities = territorial_entities(con)
    db.executemany(
        "INSERT INTO entities (id, level, code, name, label, parent_id, searchable, west, south, east, north) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        entities,
    )
    db.execute("INSERT INTO entities_fts (rowid, name, label) SELECT rowid, name, label FROM entities WHERE searchable = 1")
    log.info("%d territorial units", len(entities))

    for path in sorted(PIPELINES_DIR.glob("*/catalog.json")):
        catalog = json.loads(path.read_text())
        pipeline = path.parent.name
        for topic in catalog.get("topics", []):
            db.execute("INSERT OR REPLACE INTO topics VALUES (?, ?, ?)", (topic["id"], label(topic["label"], "es"), label(topic["label"], "en")))
        for dimension in catalog.get("dimensions", []):
            db.execute("INSERT INTO dimensions VALUES (?, ?, ?)", (dimension["id"], label(dimension["label"], "es"), label(dimension["label"], "en")))
            order = dimension.get("order", list(dimension["values"]))
            db.executemany(
                "INSERT INTO dimension_values VALUES (?, ?, ?, ?)",
                [(dimension["id"], code, dimension["values"][code], position) for position, code in enumerate(order)],
            )
        # Only statistical datasets (with a measure) are queryable; geometry datasets are the tiles'.
        for dataset in catalog.get("datasets", []):
            if "measure" not in dataset:
                continue
            template = dataset["output"]
            db.execute(
                "INSERT INTO datasets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dataset["id"],
                    dataset["title"],
                    pipeline,
                    (dataset.get("publisher") or {}).get("name"),
                    json.dumps(dataset.get("license"), ensure_ascii=False),
                    json.dumps(dataset.get("source"), ensure_ascii=False),
                    json.dumps(dataset["dimensions"]),
                    dataset.get("base_level"),
                    (dataset.get("validity") or {}).get("kind", "yearly"),
                    template,
                ),
            )
            rows = coverage(con, dataset["id"], template)
            db.executemany("INSERT INTO coverage VALUES (?, ?, ?, ?, ?)", rows)
            log.info("%s: %d level-periods on disk", dataset["id"], len(rows))
        for variable in catalog.get("variables", []):
            db.execute(
                "INSERT INTO variables VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    variable["id"],
                    variable.get("topic"),
                    label(variable["label"], "es"),
                    label(variable["label"], "en"),
                    label(variable.get("description"), "es"),
                    label(variable.get("description"), "en"),
                    variable["unit"],
                    variable["kind"],
                    variable.get("scale", 1),
                    json.dumps(variable.get("default_facet", {})),
                    json.dumps(variable.get("options", [])),
                ),
            )
            check_options(variable)
            db.executemany(
                "INSERT INTO variable_facets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        variable["id"],
                        facet["id"],
                        label(facet["label"], "es"),
                        label(facet["label"], "en"),
                        facet["dataset"],
                        json.dumps(facet["numerator"]),
                        json.dumps(facet["denominator"]) if facet.get("denominator") else None,
                        position,
                    )
                    for position, facet in enumerate(variable["facets"])
                ],
            )

    db.execute("INSERT INTO build VALUES ('built_at', ?)", (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    db.commit()
    db.close()
    partial.rename(target)
    log.info("Wrote %s", target)
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build()
