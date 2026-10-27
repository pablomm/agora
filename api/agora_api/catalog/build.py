"""
Builds the catalogue database (SQLite) from the pipelines: their catalog.json files (datasets,
dimensions, variables) and their outputs (territorial units, and which levels and periods each
dataset really has on disk).

    python -m agora_api.catalog.build
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from agora_api.config import CATALOG_DB, LICENSES, PIPELINES_DIR, PROCESSED_DIR

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


#: Tags found when building, besides the ones a catalog.json gives a dataset.
AUTO_TAGS = ("imputed", "derived", "experimental", "single_edition", "no_license", "not_downloadable")


def dataset_tags(con: duckdb.DuckDBPyConnection, dataset: dict, rows: list[tuple] | None = None) -> list[str]:
    """
    A dataset's tags: its own, and `imputed` (any cell on disk with origin imputed), `derived`
    (computed from other datasets), `experimental` (an experimental statistic), `single_edition`
    (one period only) for statistics (`rows`: their coverage), and `no_license` (none known).
    """
    tags = list(dataset.get("tags", []))
    if set(tags) & set(AUTO_TAGS):
        raise ValueError(f"{dataset['id']}: tags {sorted(set(tags) & set(AUTO_TAGS))} are found when building, not given")
    if rows is not None:
        template = dataset["output"]
        for level, *_ in LEVELS:
            path = PROCESSED_DIR / template.replace("processed/", "", 1).format(level=level)
            columns = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()} if path.exists() else set()
            if "origin" in columns and con.execute(f"SELECT bool_or(origin = 'imputed') FROM '{path}'").fetchone()[0]:
                tags.append("imputed")
                break
    kind = (dataset.get("source") or {}).get("kind", "")
    if kind == "derived":
        tags.append("derived")
    if "experimental" in kind:
        tags.append("experimental")
    if rows is not None and len({period for _, _, period, *_ in rows}) == 1:
        tags.append("single_edition")
    if not dataset.get("license"):
        tags.append("no_license")
    if not downloadable(dataset):
        tags.append("not_downloadable")
    return tags


def downloadable(dataset: dict) -> bool:
    """
    Whether its files are handed out: not when its license isn't known, nor when its catalog.json
    says so (`"downloadable": false`, a license not allowing to redistribute it; its processing notes
    say where to get it).
    """
    return bool(dataset.get("license")) and dataset.get("downloadable", True)


DATASET_COLUMNS = (
    "id", "title", "pipeline", "publisher", "license", "source", "dimensions", "base_level", "frequency",
    "path_template", "tags", "kind", "entity_type", "validity", "fields", "downloadable",
    "publisher_url", "measure", "run", "tiles", "extent", "focus", "description", "processing", "keywords", "topics",
)

#: The licenses pipelines/licenses.json has, which datasets' licenses must name.
KNOWN_LICENSES: set[str] = set()

#: Checksums of the last build's files, by (path, size, modification time): a file not changed isn't read again.
CHECKSUMS: dict[tuple[str, int, int], str] = {}


def previous_checksums(target: Path) -> dict[tuple[str, int, int], str]:
    """The checksums the catalogue being replaced has (none if it's older than them)."""
    if not target.exists():
        return {}
    db = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    try:
        rows = db.execute("SELECT path, bytes, modified, sha256 FROM dataset_files WHERE sha256 IS NOT NULL").fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        db.close()
    return {(path, size, modified): checksum for path, size, modified, checksum in rows}


def checksum(path: Path) -> tuple[str, int]:
    """A file's sha256 and modification time, from the last build's if it hasn't changed."""
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key not in CHECKSUMS:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while chunk := file.read(1 << 22):
                digest.update(chunk)
        CHECKSUMS[key] = digest.hexdigest()
    return CHECKSUMS[key], stat.st_mtime_ns


def load_licenses(db: sqlite3.Connection) -> set[str]:
    """The licenses in pipelines/licenses.json; their ids."""
    entries = json.loads(LICENSES.read_text())["licenses"]
    db.executemany(
        "INSERT INTO licenses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                entry["id"], entry["short"], label(entry["title"], "es"), label(entry["title"], "en"), entry.get("url"), entry.get("legal_url"), int(entry["open"]),
                *(json.dumps(entry[key], ensure_ascii=False) for key in ("summary", "permissions", "conditions", "limitations")),
            )
            for entry in entries
        ],
    )
    return {entry["id"] for entry in entries}


def insert_dataset(
    db: sqlite3.Connection,
    con: duckdb.DuckDBPyConnection,
    dataset: dict,
    pipeline: str,
    kind: str,
    files: list[tuple],
    coverage_rows: list[tuple] | None = None,
    places: dict[str, tuple] | None = None,
) -> None:
    """
    A dataset (as a catalog.json gives it) and its files ((name, label, path, filter, rows, bytes));
    `places` (municipality code → bounding box) to find a geometry's focus.
    """
    output = dataset["output"]
    extent, focus = spatial_extent(con, files, places or {}) if kind == "geometry" else (None, None)
    license_id = (dataset.get("license") or {}).get("id")
    if license_id and license_id not in KNOWN_LICENSES:
        raise ValueError(f"{dataset['id']}: license {license_id!r} isn't in {LICENSES.name}")
    row = {
        "id": dataset["id"],
        "title": label(dataset["title"], "es"),
        "pipeline": pipeline,
        "publisher": (dataset.get("publisher") or {}).get("name"),
        "license": json.dumps(dataset.get("license"), ensure_ascii=False),
        "source": json.dumps(dataset.get("source"), ensure_ascii=False),
        "dimensions": json.dumps(dataset.get("dimensions", [])),
        "base_level": dataset.get("base_level"),
        "frequency": (dataset.get("validity") or {}).get("kind", "yearly") if kind == "statistics" else None,
        "path_template": output if isinstance(output, str) else output["path"],
        "tags": json.dumps(dataset_tags(con, dataset, coverage_rows)),
        "kind": kind,
        "entity_type": dataset.get("entity_type"),
        "validity": json.dumps(validity(dataset), ensure_ascii=False) if kind != "statistics" else None,
        "fields": json.dumps(output.get("fields"), ensure_ascii=False) if isinstance(output, dict) and output.get("fields") else None,
        # Listed, but not handed out (with the not_downloadable tag): see `downloadable`.
        "downloadable": int(downloadable(dataset)),
        "publisher_url": (dataset.get("publisher") or {}).get("url"),
        "measure": json.dumps(dataset.get("measure"), ensure_ascii=False) if dataset.get("measure") else None,
        "run": json.dumps(run_metadata(dataset, files), ensure_ascii=False),
        "tiles": dataset.get("tiles"),
        "extent": json.dumps(extent) if extent else None,
        "focus": json.dumps(focus) if focus else None,
        "description": json.dumps(dataset.get("description"), ensure_ascii=False) if dataset.get("description") else None,
        "processing": json.dumps(dataset.get("processing"), ensure_ascii=False) if dataset.get("processing") else None,
        "keywords": json.dumps(dataset.get("keywords"), ensure_ascii=False) if dataset.get("keywords") else None,
        "topics": json.dumps(dataset.get("topics", [])),
    }
    db.execute(f"INSERT INTO datasets ({', '.join(DATASET_COLUMNS)}) VALUES ({', '.join('?' * len(DATASET_COLUMNS))})", [row[column] for column in DATASET_COLUMNS])
    rows = []
    for position, file in enumerate(files):
        # Checksums of files the dataset has whole (not a classification's share of the items).
        sha256, modified = checksum(file_location(file[2])) if file[5] is not None else (None, None)
        rows.append((dataset["id"], *file, position, sha256, modified))
    db.executemany("INSERT INTO dataset_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)


def file_location(path: str) -> Path:
    """Where a dataset file is: the pipelines' outputs (processed/…), or next to the catalogue (see services.catalog.file_path)."""
    return PROCESSED_DIR / path.removeprefix("processed/") if path.startswith("processed/") else CATALOG_DB.parent / path


def run_metadata(dataset: dict, files: list[tuple]) -> dict | None:
    """
    What the pipeline's run says about the output (its meta.json): when it was made and its source
    downloaded, the source's URL and tables, and the checks between levels. The meta.json is the
    output folder's, or the file's or folder's own (<name>.meta.json); one naming another dataset
    isn't taken.
    """
    if not files:
        return None
    first = Path(files[0][2])
    if not str(first).startswith("processed/"):
        return None
    path = PROCESSED_DIR / str(first).removeprefix("processed/")
    for candidate in (path.parent / "meta.json", path.with_suffix(".meta.json"), path.parent.with_suffix(".meta.json")):
        if not candidate.exists():
            continue
        meta = json.loads(candidate.read_text())
        if meta.get("dataset", dataset["id"]) != dataset["id"] and candidate.name != "meta.json":
            continue
        source = meta.get("source") or {}
        tables = source.get("tables")
        checks = [
            {key: check.get(key) for key in ("level", "compared", "mismatches", "max_difference")}
            for check in meta.get("checks", [])
            if isinstance(check, dict) and "mismatches" in check
        ]
        out = {
            "generated_at": meta.get("generated_at"),
            "retrieved_at": meta.get("retrieved_at"),
            "source_url": source.get("url"),
            "tables": tables if isinstance(tables, list) else None,
            "checks": checks or None,
        }
        return {key: value for key, value in out.items() if value} or None
    return None


def spatial_extent(con: duckdb.DuckDBPyConnection, files: list[tuple], places: dict[str, tuple]) -> tuple[list | None, list | None]:
    """
    A geometry's bounding box over its files, and its focus: the bounding box of the municipality
    with most of its rows (where a map shows layers only drawn up close, like parcels).
    """
    paths = [str(PROCESSED_DIR / relative.removeprefix("processed/")) for _, _, relative, *_ in files if relative.startswith("processed/")]
    if not paths:
        return None, None
    columns = {row[0] for row in con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [paths[0]]).fetchall()}
    extent = focus = None
    if "bbox" in columns:
        box = con.execute("SELECT min(bbox.xmin), min(bbox.ymin), max(bbox.xmax), max(bbox.ymax) FROM read_parquet(?)", [paths]).fetchone()
        extent = [round(value, 5) for value in box] if None not in box else None
    if "municipality_code" in columns:
        code = con.execute("SELECT mode(municipality_code) FROM read_parquet(?)", [paths]).fetchone()[0]
        focus = list(places[code]) if code in places else None
    return extent, focus


def validity(dataset: dict) -> dict | None:
    """The catalog.json's validity, its date for the latest edition when it's per edition ("{year}-01-01")."""
    given = dataset.get("validity")
    if given and "{year}" in (given.get("as_of") or "") and dataset.get("editions"):
        return {**given, "as_of": given["as_of"].format(year=max(dataset["editions"]))}
    return given


def statistics_files(template: str, coverage_rows: list[tuple]) -> list[tuple]:
    """A statistical dataset's files: one per level, with its rows from its coverage."""
    rows = {}
    for _, level, _, count, _ in coverage_rows:
        rows[level] = rows.get(level, 0) + count
    out = []
    for level, label_es, _ in LEVELS:
        if level in rows:
            relative = template.format(level=level)
            out.append((level, label_es, relative, None, rows[level], (PROCESSED_DIR / relative.replace("processed/", "", 1)).stat().st_size))
    return out


def output_files(con: duckdb.DuckDBPyConnection, dataset: dict, province_names: dict[str, str]) -> list[tuple]:
    """
    A geometry dataset's files: one per edition ({year}), per province ({province}; Catastro's,
    named after the province most of its rows are in), or its one file; with `rows` in its output
    ({column: value}), only its rows of files it shares with other datasets.
    """
    output = dataset["output"]
    template = output["path"]
    if "{year}" in template:
        candidates = [(str(year), f"Edición {year}", template.format(year=year)) for year in dataset.get("editions", [])]
    elif "{province}" in template:
        folder = (PROCESSED_DIR / template.replace("processed/", "", 1)).parent
        candidates = [(path.stem, path.stem, template.format(province=path.stem)) for path in sorted(folder.glob("*.parquet"))]
    else:
        candidates = [(Path(template).stem, label(dataset["title"], "es"), template)]
    wanted = output.get("rows") or {}
    condition = " AND ".join(f'"{column}" = ?' for column in wanted) or "TRUE"
    out = []
    for name, file_label, relative in candidates:
        path = PROCESSED_DIR / relative.replace("processed/", "", 1)
        if not path.exists():
            continue
        total, matching = con.execute(f"SELECT count(*), count(*) FILTER (WHERE {condition}) FROM '{path}'", list(wanted.values())).fetchone()
        if not matching:
            continue
        if "{province}" in template:
            columns = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchall()}
            if "municipality_code" in columns:
                code = con.execute(f"SELECT mode(substr(municipality_code, 1, 2)) FROM '{path}'").fetchone()[0]
                name_es = province_names.get(code, name)
                file_label = name_es if code == name else f"{name_es} (gerencia {name})"
        whole = matching == total
        out.append((name, file_label, relative, None if whole else json.dumps(wanted), matching, path.stat().st_size if whole else None))
    return out


#: The territorial units' table, made when building next to the catalogue (named relative to it).
TERRITORIAL_UNITS = "territorial_units.parquet"


def territorial_units(db: sqlite3.Connection, con: duckdb.DuckDBPyConnection, entities: list[tuple], folder: Path) -> None:
    """
    Every territorial unit with its codes, names, the units it's in and its bounding box: the
    gazetteer, as a reference dataset (one file per level).
    """
    by_id = {row[0]: row for row in entities}
    records = []
    for entity_id, level, code, name, label_, parent_id, _, west, south, east, north in entities:
        inside = {}
        parent = parent_id
        while parent in by_id:
            inside[by_id[parent][1]] = parent
            parent = by_id[parent][5]
        records.append(
            {
                "id": entity_id, "level": level, "code": code, "name": name, "label": label_, "parent_id": parent_id,
                **{f"{level_id}_id": inside.get(level_id) for level_id in ("census_district", "municipality", "province", "autonomous_community")},
                "west": west, "south": south, "east": east, "north": north,
            }
        )
    # Written aside and moved, so the API never reads half a file.
    partial = folder / f"{TERRITORIAL_UNITS}.part"
    pq.write_table(pa.Table.from_pylist(records), partial, compression="zstd")
    partial.replace(folder / TERRITORIAL_UNITS)
    counts = {}
    for record in records:
        counts[record["level"]] = counts.get(record["level"], 0) + 1
    ine = "Elaboración propia con datos extraídos del sitio web del INE: www.ine.es"
    dataset = {
        "id": "territorial_units",
        "title": "Unidades territoriales: códigos, nombres y jerarquía (secciones censales, distritos, municipios, provincias y comunidades autónomas)",
        "entity_type": "territorial_unit",
        "description": {
            "es": "Todas las unidades territoriales de la plataforma (secciones, distritos, municipios, provincias, comunidades y España) con su id, código INE, nombre, la unidad en la que está cada una y su caja envolvente. Es el nomenclátor que une el resto de tablas: sirve para poner nombre a un código, saber a qué municipio o provincia pertenece una sección, o agregar datos hacia arriba.",
            "en": "Every territorial unit of the platform (sections, districts, municipalities, provinces, communities and Spain) with its id, INE code, name, the units it's in and its bounding box. It's the gazetteer joining all other tables: use it to name a code, find which municipality or province a section is in, or sum data up."
        },
        "processing": {
            "es": "Elaboración de Agora al construir el catálogo: los límites vigentes del IGN y las secciones censales del INE de 2026, con la jerarquía resuelta.",
            "en": "Made by Agora when building the catalogue: IGN's current boundaries and INE's 2026 census sections, with the hierarchy resolved."
        },
        "keywords": {
            "es": [
                "nomenclátor",
                "códigos INE",
                "unidades territoriales",
                "jerarquía"
            ],
            "en": [
                "gazetteer",
                "INE codes",
                "territorial units",
                "hierarchy"
            ]
        },
        "topics": [
            "territory"
        ],
        "publisher": {"name": "Agora"},
        "source": {"kind": "derived", "from": ["ign_au_autonomous_communities", "ign_au_provinces", "ign_au_municipalities", "ine_census_sections", "ine_census_districts"]},
        "license": {"id": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/", "attribution": f"CC BY 4.0 ign.es · {ine}"},
        "validity": {"kind": "current", "description": f"The cartography the platform uses: IGN's current boundaries and INE's census sections of {CENSUS_YEAR}."},
        "output": {
            "path": TERRITORIAL_UNITS,
            "format": "Parquet, one file per level",
            "fields": [
                {"name": "id", "type": "string", "description": {"es": "Id en el catálogo (es:ine:mun:28079).", "en": "Catalogue id (es:ine:mun:28079)."}},
                {"name": "level", "type": "string", "description": {"es": "census_section, census_district, municipality, province, autonomous_community o country.", "en": "census_section, census_district, municipality, province, autonomous_community or country."}},
                {"name": "code", "type": "string", "description": {"es": "Código INE (es para España).", "en": "INE code (es for Spain)."}},
                {"name": "name", "type": "string", "description": {"es": "Nombre; las unidades censales, su número (Sección 001).", "en": "Name; census units, their number (Sección 001)."}},
                {"name": "label", "type": "string", "description": {"es": "Cómo mostrarla: las unidades censales, con su distrito y municipio.", "en": "What to show: census units with their district and municipality."}},
                {"name": "parent_id", "type": "string", "description": {"es": "La unidad en la que está directamente.", "en": "The unit it's directly in."}},
                {"name": "census_district_id", "type": "string", "description": {"es": "El distrito censal en el que está (secciones censales).", "en": "The census district it's in (census sections)."}},
                {"name": "municipality_id", "type": "string", "description": {"es": "El municipio en el que está.", "en": "The municipality it's in."}},
                {"name": "province_id", "type": "string", "description": {"es": "La provincia en la que está.", "en": "The province it's in."}},
                {"name": "autonomous_community_id", "type": "string", "description": {"es": "La comunidad autónoma en la que está.", "en": "The autonomous community it's in."}},
                {"name": "west", "type": "double", "description": {"es": "Caja envolvente, EPSG:4326 (también south, east y north).", "en": "Bounding box, EPSG:4326 (also south, east, north)."}},
            ],
        },
    }
    files = [(level, label_es, TERRITORIAL_UNITS, json.dumps({"level": level}), counts[level], None) for level, label_es, _ in LEVELS if level in counts]
    insert_dataset(db, con, dataset, "catalog", "reference", files)


CLASSIFICATION_FIELDS = [
    {"name": "classification", "type": "string", "description": {"es": "Id de la clasificación (cnae2025…).", "en": "Classification id (cnae2025…)."}},
    {"name": "code", "type": "string", "description": {"es": "El código del elemento.", "en": "The item's code."}},
    {"name": "label", "type": "string", "description": {"es": "Su nombre.", "en": "Its name."}},
    {"name": "level", "type": "integer", "description": {"es": "Su nivel; 1 es el superior.", "en": "Its level, 1 = the top."}},
    {"name": "level_name", "type": "string", "description": {"es": "El nombre del nivel (Sección, División…).", "en": "The level's name (Sección, División…)."}},
    {"name": "parent", "type": "string", "description": {"es": "El código del elemento al que pertenece.", "en": "The code of the item it belongs to."}},
    {"name": "position", "type": "integer", "description": {"es": "El orden del publicador.", "en": "The publisher's order."}},
]


def classification_datasets(db: sqlite3.Connection, con: duckdb.DuckDBPyConnection, declared: list[tuple[str, dict]]) -> None:
    """Each classification as a reference dataset (its items), and their correspondences as another."""
    items = "processed/classifications/items.parquet"
    for pipeline, entry in declared:
        rows = db.execute("SELECT count(*) FROM classification_items WHERE classification_id = ?", [entry["id"]]).fetchone()[0]
        dataset = {
            **entry,
            "entity_type": "classification_item",
            "validity": {"kind": "edition", "as_of": entry.get("version")},
            "output": {"path": items, "format": "Parquet", "fields": CLASSIFICATION_FIELDS},
        }
        insert_dataset(db, con, dataset, pipeline, "reference", [("items", label(entry["title"], "es"), items, json.dumps({"classification": entry["id"]}), rows, None)])
    path = "processed/classifications/correspondences.parquet"
    rows = con.execute(f"SELECT count(*) FROM '{PROCESSED_DIR / 'classifications' / 'correspondences.parquet'}'").fetchone()[0]
    first = declared[0][1]
    dataset = {
        "id": "classification_correspondences",
        "title": "Correspondencias entre clasificaciones (CNAE-2009 ↔ CNAE-2025, CNO-11 → CIUO-08, CNED-A → CINE-A…)",
        "entity_type": "classification_correspondence",
        "description": {
            "es": "Correspondencias entre clasificaciones: de cada código, a qué códigos de otra clasificación equivale (CNAE-2009 y CNAE-2025, CNO-11 y CIUO-08, CNED-A y CINE-A, y los niveles de estudios del censo). Un código puede corresponder a varios. Sirve para comparar datos codificados con versiones distintas.",
            "en": "Correspondences between classifications: which codes of another classification each code matches (CNAE-2009 and CNAE-2025, CNO-11 and ISCO-08, CNED-A and ISCED-A, and the census's education levels). A code can match several. Use it to compare data coded with different versions."
        },
        "processing": {
            "es": "Las tablas de correspondencia de cada publicador, tal como las da, una fila por pareja.",
            "en": "Each publisher's correspondence tables, as given, one row per pair."
        },
        "keywords": {
            "es": [
                "correspondencias",
                "tablas de equivalencia",
                "CNAE",
                "CNO",
                "CNED"
            ],
            "en": [
                "correspondences",
                "concordance tables",
                "CNAE",
                "ISCO",
                "ISCED"
            ]
        },
        "topics": [
            "classifications"
        ],
        "publisher": first.get("publisher"),
        "license": first.get("license"),
        "source": {"kind": "file", "note": "The correspondence tables each classification's publisher gives."},
        "validity": {"kind": "edition"},
        "output": {
            "path": path,
            "format": "Parquet",
            "fields": [
                {"name": "from_classification", "type": "string", "description": {"es": "Clasificación (o dimensión de la plataforma) del código de origen.", "en": "Classification (or platform dimension) of the code matched."}},
                {"name": "from_code", "type": "string", "description": {"es": "Su código.", "en": "Its code."}},
                {"name": "to_classification", "type": "string", "description": {"es": "Clasificación de destino.", "en": "Classification it's matched to."}},
                {"name": "to_code", "type": "string", "description": {"es": "El código al que corresponde (un elemento puede corresponder a varios).", "en": "The code it matches (an item can match several)."}},
                {"name": "to_label", "type": "string", "description": {"es": "El nombre de ese código, para clasificaciones que no están en el catálogo.", "en": "That code's name, for classifications not in the catalogue."}},
                {"name": "note", "type": "string", "description": {"es": "La nota del publicador, si la hay.", "en": "The publisher's note, if any."}},
            ],
        },
    }
    insert_dataset(db, con, dataset, declared[0][0], "reference", [("correspondences", "Correspondencias", path, None, rows, (PROCESSED_DIR / "classifications" / "correspondences.parquet").stat().st_size)])


#: How the web colors a variable: by magnitude, or above and below zero (a gap between two groups).
PALETTES = ("sequential", "diverging")

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


def check_measures(db: sqlite3.Connection) -> None:
    """A variable shown as another measure of one ("measure_of") has its topic and its options' dimensions, and isn't itself another's."""
    rows = {row[0]: row[1:] for row in db.execute("SELECT id, topic_id, options, measure_of FROM variables")}
    for id_, (topic, options, measure_of) in rows.items():
        if not measure_of:
            continue
        if measure_of not in rows or rows[measure_of][2]:
            raise ValueError(f"{id_}: measure_of {measure_of!r} isn't a variable shown on its own")
        dimensions = [{option["dimension"] for option in json.loads(spec or "[]")} for spec in (options, rows[measure_of][1])]
        if topic != rows[measure_of][0] or dimensions[0] != dimensions[1]:
            raise ValueError(f"{id_}: another measure of {measure_of} must have its topic and options")


def load_classifications(db: sqlite3.Connection, con: duckdb.DuckDBPyConnection) -> None:
    """Classifications declared in catalog.json files, with their items and correspondences from the classifications pipeline."""
    with_pipeline = [
        (path.parent.name, entry) for path in sorted(PIPELINES_DIR.glob("*/catalog.json")) for entry in json.loads(path.read_text()).get("classifications", [])
    ]
    declared = [entry for _, entry in with_pipeline]
    if not declared:
        return
    db.executemany(
        "INSERT INTO classifications VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (entry["id"], label(entry["title"], "es"), label(entry["title"], "en"), entry.get("version"), json.dumps(entry["levels"], ensure_ascii=False),
             json.dumps(entry.get("publisher")), json.dumps(entry.get("license")), entry.get("source", {}).get("url"))
            for entry in declared
        ],
    )
    folder = PROCESSED_DIR / "classifications"
    ids = [entry["id"] for entry in declared]
    rows = con.execute(
        "SELECT classification, code, label, level, level_name, parent, position FROM read_parquet(?) WHERE list_contains(?, classification)", [str(folder / "items.parquet"), ids]
    ).fetchall()
    db.executemany("INSERT INTO classification_items VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    pairs = con.execute("SELECT from_classification, from_code, to_classification, to_code, to_label, note FROM read_parquet(?)", [str(folder / "correspondences.parquet")]).fetchall()
    db.executemany("INSERT INTO classification_correspondences VALUES (?, ?, ?, ?, ?, ?)", pairs)
    log.info("%d classifications, %d items, %d correspondences", len(declared), len(rows), len(pairs))
    classification_datasets(db, con, with_pipeline)


def with_classification(db: sqlite3.Connection, dimension: dict) -> dict:
    """
    A dimension whose values are a classification's codes ({"classification": {"id", "level"}}):
    the codes of that level, with their labels, after the dimension's own values (total) and
    before its last ones ("not_stated"), checked to exist. Own values that group codes (its
    `parents`) go right before the first code they hold.
    """
    linked = dimension["classification"]
    codes = db.execute(
        "SELECT code, label FROM classification_items WHERE classification_id = ? AND level = ? ORDER BY position", [linked["id"], linked["level"]]
    ).fetchall()
    if not codes:
        raise ValueError(f"Dimension {dimension['id']}: classification {linked['id']} has no level {linked['level']} (run the classifications pipeline)")
    own = dimension.get("values", {})
    parents = dimension.get("parents", {})
    groups = set(parents.values())
    first = [code for code in own if code == "total"]
    last = [code for code in own if code != "total" and code not in groups]
    order = [*first]
    for code, _ in codes:
        group = parents.get(code)
        if group and group not in order:
            order.append(group)
        order.append(code)
    return {**dimension, "values": {**own, **dict(codes)}, "order": [*order, *last]}


def check_groupings(db: sqlite3.Connection) -> None:
    """A dimension that groups a classification's codes has correspondences for its values (but totals and the unknown)."""
    for dimension, classification in db.execute("SELECT id, groups_of FROM dimensions WHERE groups_of IS NOT NULL").fetchall():
        values = {row[0] for row in db.execute("SELECT code FROM dimension_values WHERE dimension_id = ?", [dimension])}
        mapped = {
            row[0] for row in db.execute("SELECT DISTINCT from_code FROM classification_correspondences WHERE from_classification = ? AND to_classification = ?", [dimension, classification])
        }
        missing = values - mapped - {"total", "not_stated", "no_previous_job", "unknown"}
        if missing:
            raise ValueError(f"Dimension {dimension} groups {classification} but has no correspondences for {sorted(missing)}")


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

    CHECKSUMS.update(previous_checksums(target))
    KNOWN_LICENSES.update(load_licenses(db))
    db.executemany("INSERT INTO levels VALUES (?, ?, ?, ?)", [(level, rank, es, en) for rank, (level, es, en) in enumerate(LEVELS)])
    entities = territorial_entities(con)
    db.executemany(
        "INSERT INTO entities (id, level, code, name, label, parent_id, searchable, west, south, east, north) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        entities,
    )
    db.execute("INSERT INTO entities_fts (rowid, name, label) SELECT rowid, name, label FROM entities WHERE searchable = 1")
    log.info("%d territorial units", len(entities))
    territorial_units(db, con, entities, target.parent)
    province_names = {row[2]: row[3] for row in entities if row[1] == "province"}
    places = {row[2]: row[7:11] for row in entities if row[1] == "municipality"}

    load_classifications(db, con)
    for path in sorted(PIPELINES_DIR.glob("*/catalog.json")):
        catalog = json.loads(path.read_text())
        pipeline = path.parent.name
        for topic in catalog.get("topics", []):
            db.execute("INSERT OR REPLACE INTO topics VALUES (?, ?, ?, ?)", (topic["id"], label(topic["label"], "es"), label(topic["label"], "en"), topic.get("position", 0)))
        for dimension in catalog.get("dimensions", []):
            linked = dimension.get("classification")
            db.execute(
                "INSERT INTO dimensions VALUES (?, ?, ?, ?, ?)",
                (dimension["id"], label(dimension["label"], "es"), label(dimension["label"], "en"), linked["id"] if linked else None, dimension.get("groups_of")),
            )
            if linked:
                dimension = with_classification(db, dimension)
            order = dimension.get("order", list(dimension["values"]))
            parents = dimension.get("parents", {})
            if not set(parents) | set(parents.values()) <= set(dimension["values"]):
                raise ValueError(f"Dimension {dimension['id']}: parents name values it doesn't have")
            db.executemany(
                "INSERT INTO dimension_values VALUES (?, ?, ?, ?, ?)",
                [(dimension["id"], code, dimension["values"][code], position, parents.get(code)) for position, code in enumerate(order)],
            )
        # Statistical datasets (with a measure) are queryable by level and period; the rest are
        # geometries (with a geometry), listed with their files.
        for dataset in catalog.get("datasets", []):
            if "measure" in dataset:
                rows = coverage(con, dataset["id"], dataset["output"])
                insert_dataset(db, con, dataset, pipeline, "statistics", statistics_files(dataset["output"], rows), rows)
                db.executemany("INSERT INTO coverage VALUES (?, ?, ?, ?, ?)", rows)
                log.info("%s: %d level-periods on disk", dataset["id"], len(rows))
            elif "geometry" in dataset:
                files = output_files(con, dataset, province_names)
                if not files:
                    log.warning("%s: no files on disk, left out", dataset["id"])
                    continue
                insert_dataset(db, con, dataset, pipeline, "geometry", files, places=places)
                log.info("%s: %d files", dataset["id"], len(files))
        for variable in catalog.get("variables", []):
            db.execute(
                "INSERT INTO variables VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    variable.get("measure_of"),
                    variable.get("palette", "sequential"),
                ),
            )
            if variable.get("palette", "sequential") not in PALETTES:
                raise ValueError(f"{variable['id']}: palette {variable['palette']!r}, not one of {PALETTES}")
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

    check_measures(db)
    check_groupings(db)
    db.execute("INSERT INTO build VALUES ('built_at', ?)", (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    db.commit()
    db.close()
    partial.rename(target)
    log.info("Wrote %s", target)
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build()
