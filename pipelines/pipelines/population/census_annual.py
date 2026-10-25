"""
Annual Population Census (INE, Censo de Población, every 1 January since 2021), two datasets:

- population_sex_age: by sex and five-year age group, from census sections up to Spain.
- population_sex_age_nationality: by sex, five-year age group and nationality (Spanish/foreign),
  from municipalities up to Spain (INE doesn't cross age and nationality below municipalities).

Only the most detailed level of each is kept; the levels above are aggregated, and checked
against the totals INE publishes in the same tables.

    python pipelines/population/census_annual.py [dataset ...] [--refresh]
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

#: "Población por sexo y edad (grupos quinquenales)" by provinces, municipalities and census
#: sections: one table per province (and a national one), found in INE's operation 463.
SEX_AGE_TABLES = [
    65034, 65042, 69097, 69105, 69109, 69113, 69117, 69121, 69125, 69129, 69133, 69137, 69141, 69145,
    69149, 69153, 69157, 69161, 69165, 69169, 69173, 69177, 69181, 69185, 69189, 69193, 69197, 69201,
    69205, 69209, 69213, 69217, 69221, 69225, 69229, 69233, 69237, 69241, 69245, 69249, 69253, 69257,
    69261, 69265, 69269, 69273, 69277, 69281, 69285, 69289, 69293, 69297, 69345,
]
#: "Población por sexo, edad (grupos quinquenales) y nacionalidad (española/extranjera)" by municipality.
SEX_AGE_NATIONALITY_TABLE = 68535


def tidy(table: pd.DataFrame, geography: str, dimensions: dict[str, str]) -> pd.DataFrame:
    """Rows with `code` (from the `geography` column), `period`, the dimensions as codes, and `value`."""
    frame = pd.DataFrame(
        {
            "code": ine.codes(table[geography]),
            "period": table["Periodo"].astype(int),
            "sex": codelists.mapped(table["Sexo"], codelists.SEX, "sex"),
            "age": table["Edad"].map(codelists.age_group),
        }
    )
    if "nationality" in dimensions:
        frame["nationality"] = codelists.mapped(table[dimensions["nationality"]], codelists.NATIONALITY_SPANISH_FOREIGN, "nationality")
    frame["value"] = ine.values(table["Total"])
    return frame


def sex_age(refresh: bool) -> None:
    raw = raw_dir(PIPELINE, date.today().isoformat()) / "census_sex_age"
    raw.mkdir(exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        paths = list(pool.map(lambda table: ine.fetch_table(table, raw / f"{table}.csv", refresh), SEX_AGE_TABLES))

    sections, municipalities, provinces = [], [], []
    for path in paths:
        table = ine.read_table(path)
        has_municipality = table["Municipios"] != ""
        has_section = table["Secciones"] != ""
        sections.append(tidy(table[has_section], "Secciones", {}))
        municipalities.append(tidy(table[has_municipality & ~has_section], "Municipios", {}))
        provinces.append(tidy(table[(table["Provincias"] != "") & ~has_municipality], "Provincias", {}))
    keys = ["code", "period", "sex", "age"]
    # The national table repeats what the provincial ones have: keep each row once.
    base = pd.concat(sections).drop_duplicates(keys)
    published = {
        "municipality": pd.concat(municipalities).drop_duplicates(keys),
        "province": pd.concat(provinces).drop_duplicates(keys),
    }
    finish("population_sex_age", base, "census_section", ["sex", "age"], published, {"tables": SEX_AGE_TABLES})


def sex_age_nationality(refresh: bool) -> None:
    raw = raw_dir(PIPELINE, date.today().isoformat())
    table = ine.read_table(ine.fetch_table(SEX_AGE_NATIONALITY_TABLE, raw / f"{SEX_AGE_NATIONALITY_TABLE}.csv", refresh))
    has_municipality = table["Municipios"] != ""
    dimensions = {"nationality": "Nacionalidad"}
    base = tidy(table[has_municipality], "Municipios", dimensions)
    published = {"province": tidy(table[(table["Provincias"] != "") & ~has_municipality], "Provincias", dimensions)}
    finish(
        "population_sex_age_nationality",
        base,
        "municipality",
        ["sex", "age", "nationality"],
        published,
        {"tables": [SEX_AGE_NATIONALITY_TABLE]},
    )


def finish(dataset: str, base: pd.DataFrame, level: str, dimensions: list[str], published: dict, source: dict) -> None:
    """Aggregates, checks against INE's published totals, and writes one file per level."""
    missing = base["value"].isna().sum()
    if missing:
        log.warning("%s: %d empty cells at the base level (left out)", dataset, missing)
    base = base[base["value"].notna()]
    levels = rollup(base, level, dimensions)
    checks = [check_against(published[upper], levels[upper], upper, dimensions) for upper in published]
    failed = [check for check in checks if check["mismatches"]]
    if failed:
        raise ValueError(f"{dataset}: aggregated values don't match INE's: {failed}")

    out = output_dir(PIPELINE) / dataset
    rows = write_levels(levels, out)
    metadata = {
        "dataset": dataset,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"operation": "INE Censo de Población (463)", "url": ine.CSV_URL, **source},
        "base_level": level,
        "periods": sorted(int(period) for period in base["period"].unique()),
        "rows_by_level": rows,
        "checks": checks,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s", out, rows)


DATASETS = {"population_sex_age": sex_age, "population_sex_age_nationality": sex_age_nationality}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Annual Population Census by sex, age and nationality, aggregated up.")
    parser.add_argument("datasets", nargs="*", help=f"datasets to build (default: all): {', '.join(DATASETS)}")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in args.datasets or DATASETS:
        DATASETS[name](args.refresh)
