"""
Annual Population Census (INE, since 2021) by sex and nationality or country of birth, four datasets:

- population_nationality: main countries of nationality (about twenty), from census sections up.
- population_nationality_detail: main nationalities (about sixty), from municipalities up.
- population_birth_country, population_birth_country_detail: the same by country of birth.

INE's lists of main countries close each continent or country group with its rest ("Otros países de
África"), so the countries add up to their groups. Each dataset nests them in one dimension
(country → group → continent → foreign → total) with the groups as sums of what they hold, and
checks every sum INE publishes too: the foreign total (total minus Spanish), INE's country groups
(the detail datasets, against INE's "grandes grupos" tables), and the levels above the base one.

    python pipelines/population/census_origin.py [dataset ...] [--refresh]
"""

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

import pandas as pd

from common import codelists, ine
from common.paths import output_dir, raw_dir
from common.rollup import check_against, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "population"

#: "Población por sexo y país de nacionalidad (principales países)" by province, municipality and
#: census section: one table per province (INE's operation 463). INE's national table (65036) has
#: the same rows as these together, so it's left out.
NATIONALITY_SECTION_TABLES = [65040, *range(66375, 66458, 2), 66459, 66461, 66463, *range(66465, 66476, 2)]
#: "Población por sexo y país de nacimiento (principales países)", likewise (national table: 65035).
BIRTH_SECTION_TABLES = [65038, *range(66374, 66457, 2), 66458, 66460, 66462, *range(66464, 66475, 2)]

#: Each group with what it's made of, from the top: the base level's lists and the sums above them.
MAIN_TREE = {
    "abroad": ["europe", "africa", "america", "asia", "oceania", "stateless"],
    "europe": ["FRA", "GBR", "ROU", "UKR", "europe_other"],
    "africa": ["MAR", "africa_other"],
    "america": ["CUB", "DOM", "ARG", "BOL", "COL", "ECU", "PER", "VEN", "america_other"],
    "asia": ["CHN", "asia_other"],
}
DETAIL_TREE = {
    "abroad": ["europe", "africa", "america", "asia", "oceania", "stateless"],
    "europe": ["eu", "europe_non_eu"],
    "eu": ["BEL", "BGR", "DNK", "FIN", "FRA", "IRL", "ITA", "NLD", "POL", "PRT", "DEU", "ROU", "SWE", "LTU", "eu_other"],
    "europe_non_eu": ["NOR", "GBR", "CHE", "UKR", "MDA", "RUS", "europe_non_eu_other"],
    "africa": ["DZA", "GMB", "GHA", "GIN", "GNQ", "MLI", "MAR", "MRT", "NGA", "SEN", "africa_other"],
    "america": ["north_america", "central_america_caribbean", "south_america"],
    "north_america": ["CAN", "USA", "MEX"],
    "central_america_caribbean": ["CUB", "HND", "NIC", "DOM", "central_america_caribbean_other"],
    "south_america": ["ARG", "BOL", "BRA", "COL", "CHL", "ECU", "PRY", "PER", "URY", "VEN", "south_america_other"],
    "asia": ["BGD", "CHN", "PHL", "IND", "PAK", "asia_other"],
}

#: Per dataset: where its tables go, the column with the country, the code list, the tree, the base
#: level, Spain's code and the code of the rest of the world (foreign nationality, born abroad).
DATASETS = {
    "population_nationality": {
        "raw": "population_nationality",
        "tables": NATIONALITY_SECTION_TABLES,
        "column": "País de nacionalidad",
        "codes": codelists.COUNTRY_MAIN,
        "tree": MAIN_TREE,
        "level": "census_section",
        "home": "spanish",
        "abroad": "foreign",
        "dimension": "nationality_main",
    },
    "population_nationality_detail": {
        "raw": "population_nationality",
        # Main nationalities, and INE's country groups to check them against.
        "tables": [66323],
        "groups_table": 68537,
        "column": "País de nacionalidad",
        "codes": codelists.COUNTRY_DETAIL,
        "tree": DETAIL_TREE,
        "level": "municipality",
        "home": "spanish",
        "abroad": "foreign",
        "dimension": "nationality_detail",
    },
    "population_birth_country": {
        "raw": "population_birth_country",
        "tables": BIRTH_SECTION_TABLES,
        "column": "País de nacimiento",
        "codes": codelists.COUNTRY_MAIN,
        "tree": {key: [code for code in codes if code != "stateless"] for key, codes in MAIN_TREE.items()},
        "level": "census_section",
        "home": "spain",
        "abroad": "abroad",
        "dimension": "birth_country_main",
    },
    "population_birth_country_detail": {
        "raw": "population_birth_country",
        "tables": [66322],
        "groups_table": 68538,
        "column": "Lugar de nacimiento (principales países)",
        "codes": codelists.COUNTRY_DETAIL,
        "tree": {key: [code for code in codes if code != "stateless"] for key, codes in DETAIL_TREE.items()},
        "level": "municipality",
        "home": "spain",
        "abroad": "abroad",
        "dimension": "birth_country_detail",
    },
}

#: The geography columns of INE's tables, from the most detailed, with the level each names.
GEOGRAPHY = [("Secciones", "census_section"), ("Municipios", "municipality"), ("Provincias", "province")]


def tidy(table: pd.DataFrame, column: str, codes: dict[str, str], dimension: str) -> dict[str, pd.DataFrame]:
    """The table's rows by level (sections, municipalities, provinces), each with code, period, sex, the country and value."""
    present = [(name, level) for name, level in GEOGRAPHY if name in table]
    out = {}
    for index, (name, level) in enumerate(present):
        # A level's rows: its column filled and the more detailed ones empty.
        rows = table[name] != ""
        for detailed, _ in present[:index]:
            rows &= table[detailed] == ""
        part = table[rows]
        out[level] = pd.DataFrame(
            {
                "code": ine.codes(part[name]),
                "period": part["Periodo"].astype(int),
                "sex": codelists.mapped(part["Sexo"], codelists.SEX, "sex"),
                dimension: codelists.mapped(part[column], codes, column),
                "value": ine.values(part["Total"]),
            }
        )
    return out


def nest(frame: pd.DataFrame, tree: dict[str, list[str]], dimension: str, home: str, abroad: str) -> pd.DataFrame:
    """Adds every group of `tree` as the sum of what it holds (the deepest first), `abroad` being the top."""
    keys = ["code", "period", "sex"]
    frame = frame[frame[dimension] != "total"].copy() if "total" in set(frame[dimension]) else frame
    added = []
    known = frame
    for group, members in reversed(tree.items()):
        code = abroad if group == "abroad" else group
        part = known[known[dimension].isin(members)]
        missing = set(members) - set(part[dimension])
        if missing:
            raise ValueError(f"{group}: no rows for {sorted(missing)}")
        summed = part.groupby(keys, as_index=False, observed=True)["value"].sum().assign(**{dimension: code})
        added.append(summed)
        known = pd.concat([known, summed], ignore_index=True)
    total = known[known[dimension].isin([home, abroad])].groupby(keys, as_index=False, observed=True)["value"].sum().assign(**{dimension: "total"})
    return pd.concat([frame, *added, total], ignore_index=True)


def build(name: str, refresh: bool) -> None:
    spec = DATASETS[name]
    dimension = spec["dimension"]
    raw = raw_dir(spec["raw"], date.today().isoformat())
    folder = raw / "section" if spec["level"] == "census_section" else raw
    folder.mkdir(exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        paths = list(pool.map(lambda table: ine.fetch_table(table, folder / f"{table}.csv", refresh), spec["tables"]))

    # Spain is "España" or "Española" depending on the table.
    codes = {**spec["codes"], "España": spec["home"], "Española": spec["home"]}
    by_level: dict[str, list[pd.DataFrame]] = {}
    for path in paths:
        for level, frame in tidy(ine.read_table(path), spec["column"], codes, dimension).items():
            by_level.setdefault(level, []).append(frame)
    keys = ["code", "period", "sex", dimension]
    # A province's table has its municipalities and sections; keep each row once all the same.
    tables = {level: pd.concat(frames).drop_duplicates(keys) for level, frames in by_level.items()}
    base = tables.pop(spec["level"])

    # Empty cells: units that didn't exist that year. Every cell of a unit-year must be empty then.
    empty = base["value"].isna()
    partial = base[empty].groupby(["code", "period"]).size().rename("empty").to_frame().join(base.groupby(["code", "period"]).size().rename("cells"))
    partial = partial[partial["empty"] != partial["cells"]]
    if len(partial):
        raise ValueError(f"{name}: unit-years with some cells empty, not all: {partial.head().to_dict('index')}")
    log.info("%s: %d empty cells (units that didn't exist that year), left out", name, int(empty.sum()))
    published_total = base[~empty & (base[dimension] == "total")]
    base = nest(base[~empty], spec["tree"], dimension, spec["home"], spec["abroad"])

    # The total from the parts, against INE's: Spanish and foreign make up everyone.
    checks = [check_against(published_total, base[base[dimension] == "total"], spec["level"], ["sex", dimension])]
    levels = rollup(base, spec["level"], ["sex", dimension])
    for level, published in tables.items():
        checks.append(check_against(published[published["value"].notna()], levels[level], level, ["sex", dimension]))
    if "groups_table" in spec:
        path = ine.fetch_table(spec["groups_table"], folder / f"{spec['groups_table']}.csv", refresh)
        groups = ine.read_table(path)
        column = next(column for column in groups.columns if column not in ("Total Nacional", "Provincias", "Municipios", "Sexo", "Periodo", "Total"))
        for level, published in tidy(groups, column, codes, dimension).items():
            published = published[published["value"].notna()]
            checks.append(check_against(published, levels[level], f"{level} (groups, table {spec['groups_table']})", ["sex", dimension]))
    failed = [check for check in checks if check["mismatches"]]
    if failed:
        raise ValueError(f"{name}: sums don't match INE's: {failed}")

    out = output_dir(PIPELINE) / name
    rows = write_levels(levels, out)
    metadata = {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"operation": "INE Censo de Población (463)", "url": ine.CSV_URL, "tables": spec["tables"] + ([spec["groups_table"]] if "groups_table" in spec else [])},
        "base_level": spec["level"],
        "periods": sorted(int(period) for period in base["period"].unique()),
        "rows_by_level": rows,
        "checks": checks,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s", out, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Annual Population Census by sex and nationality or country of birth, aggregated up.")
    parser.add_argument("datasets", nargs="*", help=f"datasets to build (default: all): {', '.join(DATASETS)}")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in args.datasets or DATASETS:
        build(name, args.refresh)
