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

Two datasets derive from this one and from census_activity_born (the same by birthplace, built by
population/census_origin.py):

- census_activity_groups: both in one `group` dimension (everyone, men, women, born in Spain, born
  abroad), with the active (employed and unemployed) and inactive (the rest) as groups of activity.
- census_activity_gaps: activity, employment and unemployment rates of women minus men, and of
  those born abroad minus those born in Spain, in points.

    python pipelines/employment/census_activity.py [step ...] [--refresh]   # steps: sex, groups, gaps
"""

import argparse
import json
import logging
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from common import ine
from common.download import sha256
from common.imputation import share_out
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
    municipalities.loc[hidden.index, "value"] = share_out(residual, hidden, adults("municipality"), "province", ["sex", "activity"])

    # Hidden sections: what their municipality (published or imputed) has left over.
    sections["municipality"] = sections["code"].str[:5]
    known = sections[~sections["hidden"]].groupby(["municipality", "period", "sex", "activity"])["value"].sum()
    published = municipalities.set_index(["code", "period", "sex", "activity"])["value"].rename_axis(["municipality", "period", "sex", "activity"])
    residual = (published - known.reindex(published.index, fill_value=0)).rename("residual").reset_index()
    hidden = sections[sections["hidden"]]
    sections.loc[hidden.index, "value"] = share_out(residual, hidden, adults("census_section"), "municipality", ["sex", "activity"])

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


#: The groups of `group`: by sex (from census_activity) and by birthplace (from census_activity_born).
BORN_GROUPS = {"spain": "born_spain", "abroad": "born_abroad"}
#: Groups of activity: the active and the inactive.
ACTIVITY_GROUPS = {"active": ["employed", "unemployed"], "inactive": ["pensioner", "student", "other_inactive"]}
#: Each rate: its numerator and denominator, as activities.
RATES = {"activity_rate": (["active"], ["total"]), "employment_rate": (["employed"], ["total"]), "unemployment_rate": (["unemployed"], ["active"])}
#: Gaps: a group minus another.
COMPARISONS = {"women_vs_men": ("female", "male"), "abroad_vs_spain": ("born_abroad", "born_spain")}
LEVELS = ["census_section", "census_district", "municipality", "province", "autonomous_community", "country"]


def groups() -> None:
    """census_activity and census_activity_born in one `group` dimension, with the active and the inactive."""
    folder = output_dir(PIPELINE)
    levels, checks = {}, []
    for level in LEVELS:
        by_sex = pd.read_parquet(folder / f"{DATASET}/{level}.parquet").rename(columns={"sex": "group"})
        born = pd.read_parquet(folder / f"census_activity_born/{level}.parquet")
        # Both tables count the same people: their totals agree where neither is imputed.
        published = by_sex[(by_sex["group"] == "total") & (by_sex["origin"] != "imputed")]
        checks.append(check_against(published, born[born["born"] == "total"].rename(columns={"born": "group"}), f"{level} (totals by sex and by birthplace)", ["group", "activity"]))
        born = born[born["born"] != "total"].assign(group=lambda frame: frame["born"].map(BORN_GROUPS)).drop(columns="born")
        frame = pd.concat([by_sex, born], ignore_index=True)
        keys = ["entity_id", "code", "period", "group"]
        added = [
            frame[frame["activity"].isin(members)].groupby(keys, as_index=False, observed=True).agg(value=("value", "sum"), origin=("origin", "first")).assign(activity=group)
            for group, members in ACTIVITY_GROUPS.items()
        ]
        levels[level] = pd.concat([frame, *added], ignore_index=True)[[*keys, "activity", "value", "origin"]].sort_values([*keys, "activity"], ignore_index=True)
    # Imputed units may differ a little (each table imputed apart); published ones must not.
    failed = [check for check in checks if check["mismatches"] and not check["level"].startswith(("census_section", "census_district", "municipality"))]
    if failed:
        raise ValueError(f"census_activity_groups: totals by sex and by birthplace differ: {failed}")
    write_derived("census_activity_groups", levels, {"derived_from": [DATASET, "census_activity_born"]}, checks)


def gaps() -> None:
    """Rates of women minus men, and of those born abroad minus those born in Spain, in points."""
    folder = output_dir(PIPELINE)
    levels = {}
    for level in LEVELS:
        frame = pd.read_parquet(folder / f"census_activity_groups/{level}.parquet")
        wide = frame.pivot_table(index=["entity_id", "code", "period", "group"], columns="activity", values="value", observed=True)
        rates = pd.DataFrame({rate: wide[numerator].sum(axis=1) / wide[denominator].sum(axis=1) * 100 for rate, (numerator, denominator) in RATES.items()})
        rates = rates.replace([np.inf, -np.inf], np.nan).stack().rename("value").rename_axis([*rates.index.names, "rate"]).reset_index()
        rates = rates.pivot_table(index=["entity_id", "code", "period", "rate"], columns="group", values="value", observed=True)
        out = [(rates[first] - rates[second]).dropna().rename("value").reset_index().assign(comparison=comparison) for comparison, (first, second) in COMPARISONS.items()]
        levels[level] = pd.concat(out, ignore_index=True).assign(origin="derived")[["entity_id", "code", "period", "rate", "comparison", "value", "origin"]]
    write_derived("census_activity_gaps", levels, {"derived_from": "census_activity_groups", "method": "rate of the first group minus the second's, in percentage points"}, [])


def write_derived(dataset: str, levels: dict[str, pd.DataFrame], source: dict, checks: list) -> None:
    out = output_dir(PIPELINE) / dataset
    counts = write_levels(levels, out)
    metadata = {
        "dataset": dataset,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "periods": sorted(int(period) for period in levels["country"]["period"].unique()),
        "checks": checks,
        "rows": counts,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    log.info("Wrote %s: %s", out, counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Population 16+ by sex and relation with activity, by census section (INE annual census), and what derives from it.")
    parser.add_argument("steps", nargs="*", choices=["sex", "groups", "gaps"], help="steps to run (default: all; groups needs census_activity_born)")
    parser.add_argument("--refresh", action="store_true", help="download the table again")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    steps = args.steps or ["sex", "groups", "gaps"]
    if "sex" in steps:
        run(args.refresh)
    if "groups" in steps:
        groups()
    if "gaps" in steps:
        gaps()
