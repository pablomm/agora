"""
Annual Population Census (INE, 2021 on): residents aged 16 and over by marital status (single,
married, widowed, divorced or separated, not stated) and sex, in every municipality and up to Spain:
population_marital_status. By age too, only in municipalities of 500 residents or more:
population_marital_status_age, in census_municipal.py.

INE publishes no census sections. By municipality: those of 500 residents or more (76306, total of
its ages) and of 50 to 500 (76312), none under 50; by province, community and Spain, 76288.
Municipalities under 50 residents take their province's residual (its figures less its published
municipalities', by sex and marital status), shared out by their residents aged 16 and over
(population_sex_age: 20 and over, plus four fifths of 15–19), as integers (`origin = "imputed"`).
The levels above are summed from municipalities and checked against 76288.

    python pipelines/population/census_marital.py [--refresh]
"""

import argparse
import json
import logging
from datetime import date, datetime, timezone

import pandas as pd

from common import codelists, ine
from common.imputation import share_out
from common.paths import output_dir, raw_dir
from common.rollup import check_against, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "population"
RAW = "population_marital_status"
#: Municipalities of 500 residents or more (by sex and age), and of 50 to 500 (by sex).
LARGE_TABLE, SMALL_TABLE = 76306, 76312
#: Spain, autonomous communities and provinces.
NATIONAL_TABLE = 76288
STATUSES = [code for code in codelists.MARITAL_STATUS.values() if code != "total"]
SEXES = ["male", "female"]
def read(path) -> dict[str, pd.DataFrame]:
    """A table's rows by level: code, period, sex, age, marital_status, value."""
    table = ine.read_table(path)
    if (table["Total"].str.strip() == ".").any():
        raise ValueError(f"{path.name}: hidden cells; this pipeline expects none")
    if "Total Nacional" in table:
        ccaa, province = table["Comunidades y Ciudades Autónomas"], table["Provincias"]
        level = ["province" if p else "autonomous_community" if c else "country" for c, p in zip(ccaa, province)]
        code = [p[:2] if p else c[:2] if c else "es" for c, p in zip(ccaa, province)]
    else:
        level, code = "municipality", ine.codes(table.iloc[:, 0])
    frame = pd.DataFrame(
        {
            "level": level,
            "code": code,
            "period": table["Periodo"].astype(int),
            "sex": codelists.mapped(table["Sexo"], codelists.SEX, "Sexo"),
            "age": table["Edad"].map(lambda label: "total" if label == "16 y más años" else codelists.age_group(label)) if "Edad" in table else "total",
            "marital_status": codelists.mapped(table["Estado civil"], codelists.MARITAL_STATUS, "Estado civil"),
            "value": ine.values(table["Total"]),
        }
    )
    return {level: part.drop(columns="level").reset_index(drop=True) for level, part in frame.groupby("level")}


def adults(periods: list[int]) -> pd.Series:
    """Residents aged 16 and over by municipality, year and sex: 20 and over, plus four fifths of 15–19."""
    frame = pd.read_parquet(
        output_dir(PIPELINE) / "population_sex_age/municipality.parquet",
        columns=["code", "period", "sex", "age", "value"],
        filters=[("period", "in", periods), ("sex", "in", SEXES)],
    )
    share = frame["age"].map(lambda age: 0 if age in ("total", "Y0T4", "Y5T9", "Y10T14") else 0.8 if age == "Y15T19" else 1)
    return (frame["value"] * share).groupby([frame["code"], frame["period"], frame["sex"]]).sum()


def by_sex(published: pd.DataFrame, provinces: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    """Every municipality by sex and marital status: those under 50 residents share out their province's residual."""
    known = set(zip(published["code"], published["period"]))
    units = weights.index.droplevel("sex").unique().to_frame(index=False)
    hidden = units[[unit not in known for unit in zip(units["code"], units["period"])]].assign(province=lambda frame: frame["code"].str[:2])
    log.info("%d municipalities and years not published (under 50 residents)", len(hidden))

    keys = ["province", "period", "sex", "marital_status"]
    residual = residuals(published, provinces, keys)
    cells = hidden.merge(pd.DataFrame({"sex": SEXES}), how="cross").merge(pd.DataFrame({"marital_status": STATUSES}), how="cross")
    cells["value"] = share_out(residual, cells, weights, "province", ["sex", "marital_status"])
    return pd.concat([published.assign(imputed=False), totals(cells.assign(age="total", imputed=True), ["sex", "marital_status"])], ignore_index=True)


def residuals(published: pd.DataFrame, provinces: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Each province's figures less its published municipalities', by `keys` (sexes and statuses, no totals)."""
    parts = published[published["sex"].isin(SEXES) & published["marital_status"].isin(STATUSES)]
    summed = parts.assign(province=parts["code"].str[:2]).groupby(keys, as_index=False)["value"].sum()
    out = provinces.rename(columns={"code": "province"}).merge(summed, on=keys, how="inner", suffixes=("", "_municipal"))
    out["residual"] = out["value"] - out["value_municipal"]
    if (out["residual"] < 0).any():
        raise ValueError(f"Municipalities add up to more than their province: {out[out['residual'] < 0].head(3).to_dict('records')}")
    return out[[*keys, "residual"]]


def totals(cells: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    """Adds the totals of each dimension (in order, so that totals of totals are there too)."""
    for dimension in dimensions:
        rest = [column for column in cells.columns if column not in (dimension, "value")]
        summed = cells.groupby(rest, as_index=False, dropna=False)["value"].sum().assign(**{dimension: "total"})
        cells = pd.concat([cells, summed], ignore_index=True)
    return cells


def finish(name: str, base: pd.DataFrame, dimensions: list[str], published: dict[str, pd.DataFrame], tables: list[int]) -> None:
    """Sums the levels up, checks every breakdown and INE's levels, and writes them."""
    levels = rollup(base, "municipality", dimensions)
    imputed = base[base["imputed"]].set_index(["code", "period", *dimensions]).index
    municipalities = levels["municipality"]
    municipalities.loc[pd.MultiIndex.from_frame(municipalities[["code", "period", *dimensions]]).isin(imputed), "origin"] = "imputed"

    checks = []
    for dimension in dimensions:
        rest = [column for column in dimensions if column != dimension]
        parts = municipalities[municipalities[dimension] != "total"].groupby(["code", "period", *rest], as_index=False)["value"].sum().assign(**{dimension: "total"})
        checks.append(check_against(municipalities[municipalities[dimension] == "total"], parts, f"municipality ({dimension})", dimensions))
    checks += [check_against(published[level], levels[level], level, dimensions) for level in ("province", "autonomous_community", "country")]
    failed = [check for check in checks if check["mismatches"]]
    if failed:
        raise ValueError(f"{name}: doesn't add up to INE's figures: {failed}")

    out = output_dir(PIPELINE) / name
    rows = write_levels(levels, out)
    metadata = {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"operation": "INE Censo de Población (463)", "url": ine.CSV_URL, "tables": tables},
        "base_level": "municipality",
        "periods": sorted(int(period) for period in base["period"].unique()),
        "imputed_cells": int(municipalities["origin"].eq("imputed").sum()),
        "rows_by_level": rows,
        "checks": checks,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s", out, rows)


def build(refresh: bool) -> None:
    raw = raw_dir(RAW, date.today().isoformat())
    paths = {table: ine.fetch_table(table, raw / f"{table}.csv", refresh) for table in (LARGE_TABLE, SMALL_TABLE, NATIONAL_TABLE)}
    large = read(paths[LARGE_TABLE])["municipality"]
    small = read(paths[SMALL_TABLE])["municipality"]
    upper = read(paths[NATIONAL_TABLE])
    published = pd.concat([large[large["age"] == "total"], small], ignore_index=True)
    if published.duplicated(["code", "period", "sex", "marital_status"]).any():
        raise ValueError("A municipality in both municipal tables")
    weights = adults(sorted(published["period"].unique().tolist()))

    everyone = by_sex(published, upper["province"], weights)
    finish("population_marital_status", everyone.drop(columns="age"), ["sex", "marital_status"], {level: frame.drop(columns="age") for level, frame in upper.items()}, [LARGE_TABLE, SMALL_TABLE, NATIONAL_TABLE])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Annual Population Census by marital status and sex, every municipality up to Spain.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build(args.refresh)
