"""
Annual Population Census (INE, since 2021) by sex and nationality or country of birth, four datasets:

- population_nationality: main countries of nationality (about twenty), from census sections up.
- population_nationality_detail: main nationalities (about sixty), from municipalities up.
- population_birth_country, population_birth_country_detail: the same by country of birth.
- population_birthplace: where residents were born against where they live (same municipality,
  another of the province, another province of the community, another community, abroad), from
  census sections up, with those born in Spain as the sum of the first four.
- population_arrival_spain: when residents came to live in Spain (after 2020, 2011–2020,
  2001–2010, before 2001) or that they always lived here, from census sections up. INE hides
  small sections and municipalities whole: they're imputed (see `impute_hidden`).

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
from common.imputation import share_out
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
#: "abroad" is the foreign nationality, or born abroad (see `rooted`).
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

#: "Población por sexo y relación entre lugar de nacimiento y lugar de residencia", one table per
#: province (national table: 65033).
BIRTHPLACE_SECTION_TABLES = [65041, 69096, *range(69104, 69297, 4), 69344]


#: "Población por año de llegada a España (agregado) y sexo", one table per province (national: 70384).
ARRIVAL_SECTION_TABLES = list(range(70510, 70562))


def rooted(tree: dict[str, list[str]], top: str, leave_out: str | None = None) -> dict[str, list[str]]:
    """The tree with its top ("abroad") named as the dataset names it, and maybe without a value."""
    return {top if group == "abroad" else group: [code for code in members if code != leave_out] for group, members in tree.items()}


#: Per dataset: where its tables go, the column with the categories, the code list, the tree (groups
#: as sums), the parts that make up the total, the base level, and Spain's code in the table if any.
DATASETS = {
    "population_nationality": {
        "raw": "population_nationality",
        "tables": NATIONALITY_SECTION_TABLES,
        "column": "País de nacionalidad",
        "codes": codelists.COUNTRY_MAIN,
        "tree": rooted(MAIN_TREE, "foreign"),
        "parts": ["spanish", "foreign"],
        "level": "census_section",
        "home": "spanish",
        "dimension": "nationality_main",
    },
    "population_nationality_detail": {
        "raw": "population_nationality",
        # Main nationalities, and INE's country groups to check them against.
        "tables": [66323],
        "groups_table": 68537,
        "column": "País de nacionalidad",
        "codes": codelists.COUNTRY_DETAIL,
        "tree": rooted(DETAIL_TREE, "foreign"),
        "parts": ["spanish", "foreign"],
        "level": "municipality",
        "home": "spanish",
        "dimension": "nationality_detail",
    },
    "population_birth_country": {
        "raw": "population_birth_country",
        "tables": BIRTH_SECTION_TABLES,
        "column": "País de nacimiento",
        "codes": codelists.COUNTRY_MAIN,
        "tree": rooted(MAIN_TREE, "abroad", leave_out="stateless"),
        "parts": ["spain", "abroad"],
        "level": "census_section",
        "home": "spain",
        "dimension": "birth_country_main",
    },
    "population_birth_country_detail": {
        "raw": "population_birth_country",
        "tables": [66322],
        "groups_table": 68538,
        "column": "Lugar de nacimiento (principales países)",
        "codes": codelists.COUNTRY_DETAIL,
        "tree": rooted(DETAIL_TREE, "abroad", leave_out="stateless"),
        "parts": ["spain", "abroad"],
        "level": "municipality",
        "home": "spain",
        "dimension": "birth_country_detail",
    },
    "population_birthplace": {
        "raw": "population_birthplace",
        "tables": BIRTHPLACE_SECTION_TABLES,
        "column": "Relación entre lugar de nacimiento y lugar de residencia",
        "codes": codelists.BIRTHPLACE,
        "tree": {"born_in_spain": ["same_municipality", "same_province", "same_community", "other_community"]},
        "parts": ["born_in_spain", "abroad"],
        "level": "census_section",
        "dimension": "birthplace",
    },
    "population_arrival_spain": {
        "raw": "population_migration",
        "tables": ARRIVAL_SECTION_TABLES,
        "column": "Año de llegada a España",
        "codes": codelists.ARRIVAL_SPAIN,
        "tree": {"arrived": ["after_2020", "2011_2020", "2001_2010", "before_2001"]},
        "parts": ["arrived", "always_in_spain"],
        "level": "census_section",
        "dimension": "arrival_spain",
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
                # ".": hidden by INE; empty: the unit didn't exist that year.
                "hidden": part["Total"].str.strip() == ".",
            }
        )
    return out


def population(level: str) -> pd.Series:
    """Residents by unit code, period and sex (annual census): the weight of each hidden unit."""
    frame = pd.read_parquet(
        output_dir(PIPELINE) / f"population_sex_age/{level}.parquet", columns=["code", "period", "sex", "value"], filters=[("age", "==", "total"), ("sex", "in", ["male", "female"])]
    )
    return frame.set_index(["code", "period", "sex"])["value"]


def impute_hidden(base: pd.DataFrame, tables: dict[str, pd.DataFrame], dimension: str) -> tuple[pd.DataFrame, dict]:
    """
    Units INE hides whole (every cell "."): hidden municipalities share what their province has left
    over (the province minus its known municipalities), then hidden sections what their municipality
    (published or imputed) has, in proportion to each unit's residents of each sex. Only the cells of
    each sex and category are imputed; their totals are sums. Returns the base level with values.
    """
    keys = ["period", "sex", dimension]
    leaves = lambda frame: frame[(frame["sex"] != "total") & (frame[dimension] != "total")]

    def fill(units: pd.DataFrame, parents: pd.DataFrame, parent: str, weights: pd.Series) -> pd.DataFrame:
        units = units.assign(**{parent: units["code"].str[: 2 if parent == "province" else 5]})
        hidden = leaves(units[units["hidden"]])
        if hidden.empty:
            return units
        known = leaves(units[~units["hidden"]]).groupby([parent, *keys], observed=True)["value"].sum()
        target = leaves(parents[parents["value"].notna()]).set_index(["code", *keys])["value"].rename_axis([parent, *keys])
        residual = (target - known.reindex(target.index, fill_value=0)).rename("residual").reset_index()
        units.loc[hidden.index, "value"] = share_out(residual, hidden, weights, parent, ["sex", dimension])
        # A hidden unit's totals by sex: the sum of its sexes.
        is_hidden = units["hidden"]
        sexes = units[is_hidden & (units["sex"] != "total")].groupby(["code", "period", dimension], as_index=False, observed=True)["value"].sum()
        totals = units[is_hidden & (units["sex"] == "total")].drop(columns="value").merge(sexes, on=["code", "period", dimension])
        return pd.concat([units[~(is_hidden & (units["sex"] == "total"))], totals], ignore_index=True)

    municipalities = fill(tables["municipality"], tables["province"], "province", population("municipality"))
    return fill(base, municipalities, "municipality", population("census_section")).drop(columns="municipality")


def nest(frame: pd.DataFrame, tree: dict[str, list[str]], dimension: str, parts: list[str]) -> pd.DataFrame:
    """Adds every group of `tree` as the sum of what it holds (the deepest first), and the total as the sum of `parts`."""
    keys = ["code", "period", "sex"]
    frame = frame[frame[dimension] != "total"].copy() if "total" in set(frame[dimension]) else frame
    added = []
    known = frame
    for group, members in reversed(tree.items()):
        part = known[known[dimension].isin(members)]
        missing = set(members) - set(part[dimension])
        if missing:
            raise ValueError(f"{group}: no rows for {sorted(missing)}")
        summed = part.groupby(keys, as_index=False, observed=True)["value"].sum().assign(**{dimension: group})
        added.append(summed)
        known = pd.concat([known, summed], ignore_index=True)
    total = known[known[dimension].isin(parts)].groupby(keys, as_index=False, observed=True)["value"].sum().assign(**{dimension: "total"})
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
    codes = {**spec["codes"], "España": spec["home"], "Española": spec["home"]} if "home" in spec else spec["codes"]
    by_level: dict[str, list[pd.DataFrame]] = {}
    for path in paths:
        for level, frame in tidy(ine.read_table(path), spec["column"], codes, dimension).items():
            by_level.setdefault(level, []).append(frame)
    keys = ["code", "period", "sex", dimension]
    # A province's table has its municipalities and sections; keep each row once all the same.
    tables = {level: pd.concat(frames).drop_duplicates(keys).reset_index(drop=True) for level, frames in by_level.items()}
    base = tables.pop(spec["level"])

    # Empty cells: units that didn't exist that year. Every cell of a unit-year must be empty then.
    empty = base["value"].isna() & ~base["hidden"]
    partial = base[empty].groupby(["code", "period"]).size().rename("empty").to_frame().join(base.groupby(["code", "period"]).size().rename("cells"))
    partial = partial[partial["empty"] != partial["cells"]]
    if len(partial):
        raise ValueError(f"{name}: unit-years with some cells empty, not all: {partial.head().to_dict('index')}")
    log.info("%s: %d empty cells (units that didn't exist that year), left out", name, int(empty.sum()))
    published_total = base[base["value"].notna() & (base[dimension] == "total")]
    base = base[~empty].reset_index(drop=True)
    imputed = set(zip(base.loc[base["hidden"], "code"], base.loc[base["hidden"], "period"]))
    stats = {level: int(frame.loc[frame["hidden"], ["code", "period"]].drop_duplicates().shape[0]) for level, frame in {spec["level"]: base, **tables}.items()}
    if imputed:
        log.info("%s: hidden unit-years, imputed: %s", name, stats)
        base = impute_hidden(base, tables, dimension)
    base = nest(base.drop(columns="hidden"), spec["tree"], dimension, spec["parts"])

    # The total from the parts, against INE's (Spanish and foreign make up everyone).
    checks = [check_against(published_total, base[base[dimension] == "total"], spec["level"], ["sex", dimension])]
    levels = rollup(base, spec["level"], ["sex", dimension])
    if imputed:
        frame = levels[spec["level"]]
        frame.loc[[unit in imputed for unit in zip(frame["code"], frame["period"])], "origin"] = "imputed"
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
        "hidden_unit_years": stats,
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
