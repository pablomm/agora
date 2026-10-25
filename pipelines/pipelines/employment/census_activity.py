"""
Population aged 16 and over by sex and relation with economic activity (employed, unemployed,
pensioners, students, other inactive), by census section, from INE's annual census (2021 on),
aggregated to districts, municipalities, provinces, autonomous communities and Spain.

INE hides small units ("."): sections and municipalities with few residents. They're imputed so
that sections add up to their municipality and municipalities to their province, as INE publishes
them:

- A hidden municipality's cells (INE leaves them empty, or ".") share what its province has left over (the province's value minus
  its known municipalities), in proportion to the municipality's population aged 15 and over that
  year (annual census by sex and age).
- Then a hidden section's cells share what its municipality has left over (published or imputed),
  in proportion to the section's population aged 15 and over, the same way.

Cells are imputed for each sex and activity, rounded so they add up exactly (largest remainder);
totals are sums. Imputed cells are flagged (`origin = "imputed"`).

    python pipelines/employment/census_activity.py [--refresh]
"""

import argparse
import json
import logging
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from common import ine
from common.download import sha256
from common.paths import DATA_DIR, output_dir, raw_dir
from common.rollup import check_against, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "employment"
DATASET = "census_activity"
#: Población de 16 y más años por sexo y relación con la actividad (agrupado): provinces, municipalities and sections.
TABLE = 66594

SEX = {"Hombres": "male", "Mujeres": "female"}
ACTIVITY = {
    "Ocupado/a": "employed",
    "Parado/a": "unemployed",
    "Perceptor/a pensión de incapacidad, jubilación, prejubilación": "pensioner",
    "Estudiante": "student",
    "Otra situación de inactividad": "other_inactive",
}
#: Population aged 15 and over: the weight of each hidden unit (the census has five-year groups).
ADULT_AGES = ["Y15T19", "Y20T24", "Y25T29", "Y30T34", "Y35T39", "Y40T44", "Y45T49", "Y50T54", "Y55T59", "Y60T64", "Y65T69", "Y70T74", "Y75T79", "Y80T84", "Y85T89", "Y90T94", "Y95T99", "Y_GE100"]


def adults(level: str) -> pd.Series:
    """Population aged 15 and over by unit code, period and sex (annual census)."""
    frame = pd.read_parquet(
        DATA_DIR / f"processed/population/population_sex_age/{level}.parquet",
        columns=["code", "period", "sex", "age", "value"],
        filters=[("age", "in", ADULT_AGES), ("sex", "in", list(SEX.values()))],
    )
    return frame.groupby(["code", "period", "sex"], observed=True)["value"].sum()


def share_out(residual: pd.DataFrame, hidden: pd.DataFrame, weights: pd.Series, parent: str) -> pd.Series:
    """
    Integers for the hidden units' cells: each parent's residual (per sex and activity) split
    among its hidden units by weight (equal shares where there's no weight), largest remainder.
    `residual` has parent, period, sex, activity and residual; `hidden` the hidden cells (code,
    parent, period, sex, activity). Returns values indexed like `hidden`.
    """
    keys = [parent, "period", "sex", "activity"]
    frame = hidden.merge(residual, on=keys, how="left")
    frame["residual"] = frame["residual"].fillna(0).clip(lower=0)
    frame["weight"] = weights.reindex(pd.MultiIndex.from_frame(frame[["code", "period", "sex"]])).fillna(0).to_numpy()
    totals = frame.groupby(keys)["weight"].transform("sum")
    count = frame.groupby(keys)["weight"].transform("size")
    share = np.where(totals > 0, frame["weight"] / totals.where(totals > 0, 1), 1 / count)
    exact = frame["residual"] * share
    floor = np.floor(exact)
    frame["value"] = floor
    frame["remainder"] = exact - floor
    left = (frame["residual"] - frame.groupby(keys)["value"].transform("sum")).round().astype(int)
    # The units with the largest remainders get one more until the residual is used up.
    frame["rank"] = frame.groupby(keys)["remainder"].rank(method="first", ascending=False)
    frame["value"] += (frame["rank"] <= left).astype(float)
    return frame.set_index(hidden.index)["value"]


def run(refresh: bool) -> None:
    raw = raw_dir("employment_census", date.today().isoformat())
    path = ine.fetch_table(TABLE, raw / f"{TABLE}.csv", refresh)
    table = ine.read_table(path)
    table = table[table["Sexo"].isin(SEX) & table["Relación con la actividad"].isin(ACTIVITY)]
    table = table.assign(
        sex=table["Sexo"].map(SEX),
        activity=table["Relación con la actividad"].map(ACTIVITY),
        period=table["Periodo"].astype(int),
        value=ine.values(table["Total"]),
        # ".": hidden by INE; empty: the unit didn't exist that year.
        hidden=table["Total"].str.strip() == ".",
    )
    sections = table[table["Secciones"] != ""].assign(code=lambda frame: ine.codes(frame["Secciones"]))
    municipalities = table[(table["Municipios"] != "") & (table["Secciones"] == "")].assign(code=lambda frame: ine.codes(frame["Municipios"]))
    provinces = table[(table["Provincias"] != "") & (table["Municipios"] == "")].assign(code=lambda frame: ine.codes(frame["Provincias"]))
    # A municipality left empty is hidden too (not missing) when its sections exist that year.
    present = set(zip(sections.loc[sections["value"].notna() | sections["hidden"], "code"].str[:5], sections.loc[sections["value"].notna() | sections["hidden"], "period"]))
    empty = municipalities["value"].isna() & ~municipalities["hidden"]
    municipalities.loc[empty, "hidden"] = [(code, period) in present for code, period in zip(municipalities.loc[empty, "code"], municipalities.loc[empty, "period"])]
    columns = ["code", "period", "sex", "activity", "value", "hidden"]
    sections, municipalities, provinces = (frame[columns][frame["value"].notna() | frame["hidden"]].reset_index(drop=True) for frame in (sections, municipalities, provinces))
    stats = {"hidden_municipality_cells": int(municipalities["hidden"].sum()), "hidden_section_cells": int(sections["hidden"].sum())}

    # Hidden municipalities: what their province has left over.
    municipalities["province"] = municipalities["code"].str[:2]
    known = municipalities[~municipalities["hidden"]].groupby(["province", "period", "sex", "activity"])["value"].sum()
    residual = (provinces.set_index(["code", "period", "sex", "activity"])["value"].rename_axis(["province", "period", "sex", "activity"]) - known.reindex(
        provinces.set_index(["code", "period", "sex", "activity"]).index.rename(["province", "period", "sex", "activity"]), fill_value=0
    )).rename("residual").reset_index()
    hidden = municipalities[municipalities["hidden"]]
    municipalities.loc[hidden.index, "value"] = share_out(residual, hidden, adults("municipality"), "province")

    # Hidden sections: what their municipality (published or imputed) has left over.
    sections["municipality"] = sections["code"].str[:5]
    known = sections[~sections["hidden"]].groupby(["municipality", "period", "sex", "activity"])["value"].sum()
    published = municipalities.set_index(["code", "period", "sex", "activity"])["value"].rename_axis(["municipality", "period", "sex", "activity"])
    residual = (published - known.reindex(published.index, fill_value=0)).rename("residual").reset_index()
    hidden = sections[sections["hidden"]]
    sections.loc[hidden.index, "value"] = share_out(residual, hidden, adults("census_section"), "municipality")

    # Every margin (sex total, activity total) as sums, so any filter is a sum of rows.
    base = sections[["code", "period", "sex", "activity", "value", "hidden"]]
    margins = [base]
    for dimension in ("sex", "activity"):
        margins.append(base.groupby([*(column for column in ("code", "period", "sex", "activity") if column != dimension)], as_index=False).agg(value=("value", "sum"), hidden=("hidden", "any")).assign(**{dimension: "total"}))
    margins.append(base.groupby(["code", "period"], as_index=False).agg(value=("value", "sum"), hidden=("hidden", "any")).assign(sex="total", activity="total"))
    base = pd.concat(margins, ignore_index=True)

    levels = rollup(base, "census_section", ["sex", "activity"])
    flags = base.set_index(["code", "period", "sex", "activity"])["hidden"]
    section_level = levels["census_section"]
    section_level["origin"] = np.where(flags.reindex(pd.MultiIndex.from_frame(section_level[["code", "period", "sex", "activity"]])).to_numpy(), "imputed", "published")

    # Municipalities and provinces as INE publishes them, where it does.
    checks = []
    for level, frame in (("municipality", municipalities), ("province", provinces)):
        published = frame[~frame["hidden"]]
        checks.append(check_against(published, levels[level][levels[level]["sex"].isin(SEX.values()) & levels[level]["activity"].isin(ACTIVITY.values())], level, ["sex", "activity"]))
    out = output_dir(PIPELINE) / DATASET
    counts = write_levels(levels, out)
    metadata = {
        "dataset": DATASET,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"publisher": "INE", "table": TABLE, "raw": str(path), "sha256": sha256(path)},
        "periods": sorted(int(period) for period in base["period"].unique()),
        "imputation": stats,
        "checks": checks,
        "rows": counts,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    log.info("Wrote %s: %s", out, counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Population 16+ by sex and relation with activity, by census section (INE annual census).")
    parser.add_argument("--refresh", action="store_true", help="download the table again")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.refresh)
