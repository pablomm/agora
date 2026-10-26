"""
Annual Population Census (INE, 2021 on): residents aged 16 and over by marital status (single,
married, widowed, divorced or separated, not stated), in every municipality and up to Spain:

- population_marital_status: by sex.
- population_marital_status_age: by sex and age (16–34, 35–54, 55–74, 75 and over).

INE publishes no census sections. By municipality: those of 500 residents or more by sex and age
(76306), of 50 to 500 by sex (76312), none under 50. By province, community and Spain: by sex
(76288) and by sex and age (76291). Every municipality is filled, and the levels above summed from
them and checked against INE's:

- By sex, municipalities under 50 residents take their province's residual (its figures less its
  published municipalities', by sex and marital status), shared out by their residents aged 16 and
  over (population_sex_age: 20 and over, plus four fifths of 15–19), as integers.
- By age, every municipality under 500 residents is a row whose total by sex and marital status is
  known (published, or imputed as above) and its province's residual by age a column total: the
  cells are fitted to both (iterative proportional fitting from the municipality's residents by
  age) and rounded so that both still hold exactly (a max flow per province, year, sex and status).

Imputed cells have `origin = "imputed"`.

    python pipelines/population/census_marital.py [--refresh]
"""

import argparse
import json
import logging
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import scipy.sparse as sparse
from scipy.sparse.csgraph import maximum_flow

from common import codelists, ine
from common.imputation import share_out
from common.paths import output_dir, raw_dir
from common.rollup import check_against, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "population"
RAW = "population_marital_status"
#: Municipalities of 500 residents or more (by sex and age), and of 50 to 500 (by sex).
LARGE_TABLE, SMALL_TABLE = 76306, 76312
#: Spain, autonomous communities and provinces: by sex, and by sex, age and nationality.
NATIONAL_TABLE, NATIONAL_AGE_TABLE = 76288, 76291
STATUSES = [code for code in codelists.MARITAL_STATUS.values() if code != "total"]
SEXES = ["male", "female"]
#: The age bands, from the census's five-year groups (16–19 as four fifths of 15–19).
BANDS = {
    "Y16T34": {"Y15T19": 0.8, "Y20T24": 1, "Y25T29": 1, "Y30T34": 1},
    "Y35T54": {"Y35T39": 1, "Y40T44": 1, "Y45T49": 1, "Y50T54": 1},
    "Y55T74": {"Y55T59": 1, "Y60T64": 1, "Y65T69": 1, "Y70T74": 1},
    "Y_GE75": {"Y75T79": 1, "Y80T84": 1, "Y85T89": 1, "Y90T94": 1, "Y95T99": 1, "Y_GE100": 1},
}


def read(path) -> dict[str, pd.DataFrame]:
    """A table's rows by level: code, period, sex, age, marital_status, value (all nationalities)."""
    table = ine.read_table(path)
    if (table["Total"].str.strip() == ".").any():
        raise ValueError(f"{path.name}: hidden cells; this pipeline expects none")
    if "Nacionalidad" in table:
        table = table[table["Nacionalidad"] == "Total"]
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


def residents(periods: list[int]) -> pd.DataFrame:
    """Residents by municipality, year, sex (male, female) and age band, and aged 16 and over (`total`)."""
    frame = pd.read_parquet(
        output_dir(PIPELINE) / "population_sex_age/municipality.parquet",
        columns=["code", "period", "sex", "age", "value"],
        filters=[("period", "in", periods), ("sex", "in", SEXES)],
    )
    bands = [frame.assign(age=band, value=frame["value"] * frame["age"].map(groups).fillna(0)) for band, groups in BANDS.items()]
    out = pd.concat(bands).groupby(["code", "period", "sex", "age"], as_index=False)["value"].sum()
    adults = out.groupby(["code", "period", "sex"], as_index=False)["value"].sum().assign(age="total")
    return pd.concat([out, adults], ignore_index=True)


def by_sex(published: pd.DataFrame, provinces: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """Every municipality by sex and marital status: those under 50 residents share out their province's residual."""
    known = set(zip(published["code"], published["period"]))
    units = weights[["code", "period"]].drop_duplicates()
    hidden = units[[unit not in known for unit in zip(units["code"], units["period"])]].assign(province=lambda frame: frame["code"].str[:2])
    log.info("%d municipalities and years not published (under 50 residents)", len(hidden))

    keys = ["province", "period", "sex", "marital_status"]
    residual = residuals(published, provinces, keys)
    cells = hidden.merge(pd.DataFrame({"sex": SEXES}), how="cross").merge(pd.DataFrame({"marital_status": STATUSES}), how="cross")
    weight = weights[weights["age"] == "total"].set_index(["code", "period", "sex"])["value"]
    cells["value"] = share_out(residual, cells, weight, "province", ["sex", "marital_status"])
    return pd.concat([published.assign(imputed=False), totals(cells.assign(age="total", imputed=True), ["sex", "marital_status"])], ignore_index=True)


def residuals(published: pd.DataFrame, provinces: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Each province's figures less its published municipalities', by `keys` (sexes and statuses, no totals)."""
    parts = published[published["sex"].isin(SEXES) & published["marital_status"].isin(STATUSES) & (published["age"] != "total" if "age" in keys else True)]
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


def by_age(large: pd.DataFrame, everyone: pd.DataFrame, provinces: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    """Every municipality by sex, age and marital status: under 500 residents, fitted to their totals and their province's residual by age."""
    large_units = set(zip(large["code"], large["period"]))
    small = everyone[[unit not in large_units for unit in zip(everyone["code"], everyone["period"])]]
    rows = small[small["sex"].isin(SEXES) & small["marital_status"].isin(STATUSES)][["code", "period", "sex", "marital_status", "value"]]
    rows = rows.assign(province=rows["code"].str[:2]).rename(columns={"value": "row_total"})
    group = ["province", "period", "sex", "marital_status"]
    columns = residuals(large, provinces[provinces["age"] != "total"], [*group, "age"]).rename(columns={"residual": "column_total"})

    cells = rows.merge(pd.DataFrame({"age": list(BANDS)}), how="cross")
    cells = cells.merge(columns, on=[*group, "age"], how="left").fillna({"column_total": 0})
    seed = weights.set_index(["code", "period", "sex", "age"])["value"]
    # A little everywhere, so that no cell a total needs is stuck at zero.
    cells["value"] = seed.reindex(pd.MultiIndex.from_frame(cells[["code", "period", "sex", "age"]])).fillna(0).to_numpy() + 0.01
    sums = (cells.groupby(group)[["row_total"]].sum() / len(BANDS)).join(columns.groupby(group)[["column_total"]].sum(), how="outer").fillna(0)
    if ((sums["row_total"] - sums["column_total"]).abs() > 1e-6).any():
        raise ValueError("Municipalities' totals and their province's residual by age don't agree")
    cells["value"] = fitted(cells, group)
    cells["value"] = rounded(cells, group)
    small_cells = totals(cells[["code", "period", "sex", "age", "marital_status", "value"]], ["sex", "age", "marital_status"])
    # Their totals by sex and status are the ones by_sex has (published from 50 residents).
    published_totals = set(zip(*(small.loc[~small["imputed"], column] for column in ("code", "period"))))
    published = (small_cells["age"] == "total") & pd.Series([unit in published_totals for unit in zip(small_cells["code"], small_cells["period"])], index=small_cells.index)
    return pd.concat([large.assign(imputed=False), small_cells.assign(imputed=~published)], ignore_index=True)


def fitted(cells: pd.DataFrame, group: list[str]) -> np.ndarray:
    """Iterative proportional fitting of each group's municipality × age table to its row and column totals."""
    row = cells.groupby([*group, "code"], sort=False).ngroup().to_numpy()
    column = cells.groupby([*group, "age"], sort=False).ngroup().to_numpy()
    row_total = cells.groupby(row)["row_total"].first().to_numpy()
    column_total = cells.groupby(column)["column_total"].first().to_numpy()
    value = cells["value"].to_numpy(dtype=float)
    for iteration in range(500):
        sums = np.bincount(row, value)
        value = value * np.divide(row_total, sums, out=np.zeros_like(sums), where=sums > 0)[row]
        sums = np.bincount(column, value)
        value = value * np.divide(column_total, sums, out=np.zeros_like(sums), where=sums > 0)[column]
        error = np.abs(np.bincount(row, value) - row_total).max()
        if error < 1e-6:
            break
    log.info("Fitted by age in %d iterations (largest row error %.2g)", iteration + 1, error)
    if error > 1e-3:
        raise ValueError(f"The fit by age didn't converge: a row {error} off its total")
    return value


def rounded(cells: pd.DataFrame, group: list[str]) -> np.ndarray:
    """
    Each cell to its floor or ceiling so that every row and column keeps its (integer) total: in
    each group, the cells rounded up are a maximum flow from rows to columns along fractional cells.
    """
    value = cells["value"].to_numpy()
    out = np.floor(value + 1e-9)
    fraction = value - out
    for indices in cells.groupby(group, sort=False).indices.values():
        part = cells.iloc[indices]
        rows, row = np.unique(part["code"].to_numpy(), return_inverse=True)
        ages, age = np.unique(part["age"].to_numpy(), return_inverse=True)
        floor = out[indices]
        row_need = np.rint(part.groupby(row)["row_total"].first().to_numpy() - np.bincount(row, floor, len(rows))).astype(int)
        column_need = np.rint(part.groupby(age)["column_total"].first().to_numpy() - np.bincount(age, floor, len(ages))).astype(int)
        if row_need.sum() == 0:
            continue
        # Nodes: source, rows, columns, sink.
        source, sink = 0, 1 + len(rows) + len(ages)
        up = fraction[indices] > 1e-9
        tails = np.r_[np.zeros(len(rows), int), 1 + row[up], 1 + len(rows) + np.arange(len(ages))]
        heads = np.r_[1 + np.arange(len(rows)), 1 + len(rows) + age[up], np.full(len(ages), sink)]
        capacity = np.r_[row_need, np.ones(up.sum(), int), column_need].astype(np.int32)
        graph = sparse.csr_array((capacity, (tails, heads)), shape=(sink + 1, sink + 1))
        result = maximum_flow(graph, source, sink)
        if result.flow_value != row_need.sum():
            raise ValueError(f"No rounding keeps the totals for {part.iloc[0][group].to_dict()}")
        flow = result.flow.tocsr()
        out[indices[up]] += np.asarray(flow[1 + row[up], 1 + len(rows) + age[up]]).ravel() > 0
    return out


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
    paths = {table: ine.fetch_table(table, raw / f"{table}.csv", refresh) for table in (LARGE_TABLE, SMALL_TABLE, NATIONAL_TABLE, NATIONAL_AGE_TABLE)}
    large = read(paths[LARGE_TABLE])["municipality"]
    small = read(paths[SMALL_TABLE])["municipality"]
    upper, upper_age = read(paths[NATIONAL_TABLE]), read(paths[NATIONAL_AGE_TABLE])
    published = pd.concat([large[large["age"] == "total"], small], ignore_index=True)
    if published.duplicated(["code", "period", "sex", "marital_status"]).any():
        raise ValueError("A municipality in both municipal tables")
    weights = residents(sorted(published["period"].unique().tolist()))

    everyone = by_sex(published, upper["province"], weights)
    finish("population_marital_status", everyone.drop(columns="age"), ["sex", "marital_status"], {level: frame.drop(columns="age") for level, frame in upper.items()}, [LARGE_TABLE, SMALL_TABLE, NATIONAL_TABLE])
    ages = by_age(large, everyone, upper_age["province"], weights)
    finish("population_marital_status_age", ages, ["sex", "age", "marital_status"], upper_age, [LARGE_TABLE, SMALL_TABLE, NATIONAL_AGE_TABLE])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Annual Population Census by marital status, sex and age, every municipality up to Spain.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build(args.refresh)
