"""
Census 2021 detail by census section, from INE's custom tables tool (downloaded by
custom_tables.py): dwellings by year of construction, building type, floor area and floors, and
their mean age; households by structure, type, nuclei, families and members of each age or
activity; family nuclei by type, couples by kind and sexes, nuclei by number of children and their
mean number of children.

The tool answers for groups of municipalities (rows: municipality → district → section, plus the
group's total), shows only sections of about 500 units or more (dwellings, households, nuclei),
and perturbs its cells slightly (statistical disclosure control). Its districts, municipalities and
group add up their shown sections only, so a hidden section's own figures are nowhere. So, for
each table:

- Counts: a shown section keeps its split by category; a hidden one takes its district's (else
  its municipality's, else the group's: the split of the shown sections around it). Each section's
  split is then fitted to its total, as integers (largest remainders), which also takes the tool's
  noise out: the official dwellings or households (dwellings_2021, households_2021); nuclei, the
  tool's own, and for a hidden section its households' nuclei (households_by_nuclei_2021: one,
  two, three for "3 or more"). Districts and every level up are summed from sections.
- Means (dwellings' age, children per nucleus): as the tool gives them for shown sections; a hidden
  one takes its district's, else its municipality's, else the group's. Every level up is weighted
  by what the mean is of (dwellings of each use, nuclei of each type).

Shown sections are `origin = "published"` (fitted to the official totals), hidden ones `imputed`.

    python pipelines/census_2021/census_2021_detail.py [dataset ...]
"""

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from common.paths import output_dir, raw_dir
from custom_tables import read_px
from common.rollup import COUNTRY_ID, ID_PREFIX, LEVELS, ccaa_by_province, parent_codes, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "census_2021"
PERIOD = 2021
RAW = raw_dir(PIPELINE, "2026-10-26") / "custom"

#: Each dataset: its tables (custom_tables.py), its dimension, the tool's labels as codes, groups
#: of codes (summed), what its counts are fitted to, and whether it's a mean.
DATASETS = {
    "dwellings_by_year_2021": {
        "tables": {"dwellings_year": None},
        "dimension": "construction_period",
        "codes": {
            "Antes de 1900": "before_1900", "1900 a 1920": "1900_1920", "1921 a 1940": "1921_1940", "1941 a 1950": "1941_1950",
            "1951 a 1960": "1951_1960", "1961 a 1970": "1961_1970", "1971 a 1980": "1971_1980", "1981 a 1990": "1981_1990",
            "1991 a 2000": "1991_2000", "2001 a 2010": "2001_2010", "2011 a 2020": "2011_2020", "No consta": "not_stated",
        },
        "groups": {
            "before_1951": ["before_1900", "1900_1920", "1921_1940", "1941_1950"],
            "1951_1980": ["1951_1960", "1961_1970", "1971_1980"],
            "1981_2000": ["1981_1990", "1991_2000"],
            "2001_2020": ["2001_2010", "2011_2020"],
        },
        "base": "dwellings",
    },
    "dwellings_by_building_2021": {
        "tables": {"dwellings_building": None},
        "dimension": "building_type",
        "codes": {
            "Vivienda en edificio residencial con una vivienda": "one_dwelling",
            "Vivienda en edificio residencial con dos viviendas": "two_dwellings",
            "Vivienda en edificio residencial con tres viviendas o más": "three_or_more",
            "Vivienda en edificio no residencial": "non_residential",
            "No consta": "not_stated",
        },
        "groups": {},
        "base": "dwellings",
    },
    "dwellings_by_floor_area_2021": {
        "tables": {"dwellings_floor_area": None},
        "dimension": "floor_area_band",
        "codes": {
            "Hasta 30 m2": "up_to_30", "30-45 m2": "30_45", "46-60 m2": "46_60", "61-75 m2": "61_75", "76-90 m2": "76_90",
            "91-105 m2": "91_105", "106-120 m2": "106_120", "121-150 m2": "121_150", "151-180 m2": "151_180", "Más de 180 m2": "over_180", "No consta": "not_stated",
        },
        "groups": {"up_to_60": ["up_to_30", "30_45", "46_60"], "61_90": ["61_75", "76_90"], "91_120": ["91_105", "106_120"], "over_120": ["121_150", "151_180", "over_180"]},
        "base": "dwellings",
    },
    "dwellings_by_floors_2021": {
        "tables": {"dwellings_floors": None},
        "dimension": "building_floors",
        "codes": {**{str(n): f"floors_{n}" for n in range(1, 10)}, "10 o más": "floors_10_plus", "No consta": "not_stated"},
        "groups": {"floors_1_2": ["floors_1", "floors_2"], "floors_3_5": ["floors_3", "floors_4", "floors_5"], "floors_6_9": ["floors_6", "floors_7", "floors_8", "floors_9"]},
        "base": "dwellings",
    },
    "dwellings_mean_age_2021": {
        "tables": {"dwellings_mean_age": None},
        "dimension": "dwelling",
        "codes": {"TOTAL": "total", "Viviendas principales": "principal", "Viviendas no principales": "non_principal"},
        "mean": {"dataset": "dwellings_2021", "dimension": "dwelling"},
    },
    "households_by_structure_2021": {
        "tables": {"households_structure": None},
        "dimension": "household_structure",
        "codes": {
            "Hogar con una mujer sola menor de 65 años": "woman_alone_under_65",
            "Hogar con un hombre solo menor de 65 años": "man_alone_under_65",
            "Hogar con una mujer sola de 65 años o más": "woman_alone_65_plus",
            "Hogar con un hombre solo de 65 años o más": "man_alone_65_plus",
            "Hogar con un solo progenitor que convive con algún hijo menor de 25 años": "lone_parent_young_children",
            "Hogar con un solo progenitor que convive con todos sus hijos de 25 años o más": "lone_parent_adult_children",
            "Hogar formado por pareja sin hijos": "couple_no_children",
            "Hogar formado por pareja con hijos en donde algún hijo es menor de 25 años": "couple_young_children",
            "Hogar formado por pareja con hijos en donde todos los hijos de 25 años o más": "couple_adult_children",
            "Hogar formado por pareja o un solo progenitor que convive con algún hijo menor de 25 años y otra(s) persona(a)": "parents_children_others",
            "Otro tipo de hogar": "other",
        },
        "groups": {
            "alone_under_65": ["woman_alone_under_65", "man_alone_under_65"],
            "alone_65_plus": ["woman_alone_65_plus", "man_alone_65_plus"],
            "living_alone": ["alone_under_65", "alone_65_plus"],
            "lone_parent": ["lone_parent_young_children", "lone_parent_adult_children"],
            "couple_with_children": ["couple_young_children", "couple_adult_children"],
        },
        "base": "households",
    },
    "households_by_type_2021": {
        "tables": {"households_type": None},
        "dimension": "household_type",
        "codes": {
            "Hogar unipersonal": "one_person",
            "Hogar multipersonal pero que no forma familia": "no_family",
            "Hogar de una familia sin otras personas adicionales y ningún núcleo": "family_no_nucleus",
            "Hogar de una familia sin otras personas adicionales y sólo un núcleo": "family_one_nucleus",
            "Hogar de una familia sin otras personas adicionales y un núcleo y otras personas": "family_nucleus_and_others",
            "Hogar de una familia sin otras personas adicionales y dos núcleos o más": "family_two_nuclei",
            "Hogar de una familia, con otras personas no emparentadas": "family_and_unrelated",
            "Hogar de dos o más familias": "two_or_more_families",
        },
        "groups": {"one_family": ["family_no_nucleus", "family_one_nucleus", "family_nucleus_and_others", "family_two_nuclei", "family_and_unrelated"]},
        "base": "households",
    },
    "households_by_nuclei_2021": {
        "tables": {"households_nuclei": None},
        "dimension": "household_nuclei",
        "codes": {"0": "nuclei_0", "1": "nuclei_1", "2": "nuclei_2", "3 o más": "nuclei_3_plus"},
        "groups": {"nuclei_2_plus": ["nuclei_2", "nuclei_3_plus"]},
        "base": "households",
    },
    "households_by_families_2021": {
        "tables": {"households_families": None},
        "dimension": "household_families",
        "codes": {"0": "families_0", "1": "families_1", "2 ó más": "families_2_plus"},
        "groups": {},
        "base": "households",
    },
    "households_by_members_2021": {
        # One table per group of members; `member_group` tells them apart.
        "tables": {
            "households_aged_0_4": "aged_0_4",
            "households_aged_5_15": "aged_5_15",
            "households_aged_65_84": "aged_65_84",
            "households_aged_85_plus": "aged_85_plus",
            "households_working": "working",
            "households_unemployed": "unemployed",
        },
        "dimension": "members",
        "codes": {"0": "members_0", "1": "members_1", "2": "members_2", "3 o más": "members_3_plus"},
        "groups": {"members_1_plus": ["members_1", "members_2", "members_3_plus"]},
        "base": "households",
    },
    "nuclei_by_type_2021": {
        "tables": {"nuclei_type": None},
        "dimension": "nucleus_type",
        "codes": {"Pareja sin hijos": "couple_no_children", "Pareja con hijos": "couple_with_children", "Progenitor 1 con hijo(s)": "parent_1", "Progenitor 2 con hijo(s)": "parent_2"},
        "groups": {"couple": ["couple_no_children", "couple_with_children"], "lone_parent": ["parent_1", "parent_2"]},
        "base": "nuclei",
    },
    "nuclei_by_couple_kind_2021": {
        "tables": {"nuclei_couple_kind": None},
        "dimension": "couple_kind",
        "codes": {"Pareja de derecho": "married", "Pareja de hecho (ambos solteros)": "cohabiting_single", "Pareja de hecho (otro tipo)": "cohabiting_other", "Núcleo que no es pareja": "not_couple"},
        "groups": {"cohabiting": ["cohabiting_single", "cohabiting_other"], "couple": ["married", "cohabiting"]},
        "base": "nuclei",
    },
    "nuclei_by_couple_sexes_2021": {
        "tables": {"nuclei_couple_sexes": None},
        "dimension": "couple_sexes",
        "codes": {"Pareja de distinto sexo": "different_sex", "Pareja del mismo sexo, femenino": "same_sex_female", "Pareja del mismo sexo, masculino": "same_sex_male", "Núcleo que no es pareja": "not_couple"},
        "groups": {"same_sex": ["same_sex_female", "same_sex_male"], "couple": ["different_sex", "same_sex"]},
        "base": "nuclei",
    },
    "nuclei_by_children_2021": {
        "tables": {"nuclei_children": None},
        "dimension": "children",
        "codes": {"0": "children_0", "1": "children_1", "2": "children_2", "3": "children_3", "4 ó más": "children_4_plus"},
        "groups": {"children_3_plus": ["children_3", "children_4_plus"]},
        "base": "nuclei",
    },
    "nuclei_mean_children_2021": {
        "tables": {"nuclei_mean_children": None},
        "dimension": "nucleus_type",
        "codes": {"TOTAL": "total", "Pareja sin hijos": "couple_no_children", "Pareja con hijos": "couple_with_children", "Progenitor 1 con hijo(s)": "parent_1", "Progenitor 2 con hijo(s)": "parent_2"},
        "mean": {"dataset": "nuclei_by_type_2021", "dimension": "nucleus_type"},
    },
}


def coded(frame: pd.DataFrame, codes: dict[str, str], table: str) -> pd.DataFrame:
    """The tool's labels as codes ("No consta" and "No Consta" alike); "TOTAL" stays."""
    lower = {label.lower(): code for label, code in codes.items()}
    labels = [column for column in frame.columns if column not in ("municipality", "district", "section", "TOTAL")]
    unknown = [label for label in labels if label.lower() not in lower]
    if unknown:
        raise ValueError(f"{table}: unknown labels {sorted(unknown)}")
    renamed = {label: lower[label.lower()] for label in labels}
    if "total" in lower:
        renamed["TOTAL"] = lower["total"]
    return frame.rename(columns=renamed)


def units(chunk: dict, sections: pd.Series) -> pd.DataFrame:
    """Every 2021 section of a chunk's municipalities, with its weight."""
    out = sections[sections.index.str[:5].isin(chunk["codes"])].rename("weight").to_frame()
    return out.assign(municipality=out.index.str[:5], district=out.index.str[:7])


def counts(table: pd.DataFrame, chunk_units: pd.DataFrame, categories: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """
    Each section's counts by category (floats): shown ones as given; a hidden one, its district's
    (else its municipality's, else the chunk's) as a split to scale. The tool's districts,
    municipalities and chunk add up their shown sections only (plus noise), so there is no remainder
    to share out. Returns them and whether each was shown.
    """
    total = table[table["municipality"].isna()][categories].iloc[0].clip(lower=0)
    towns = table[table["municipality"].notna() & table["district"].isna()].set_index("municipality")[categories].clip(lower=0)
    districts = table[table["district"].notna() & table["section"].isna()].set_index("district")[categories].clip(lower=0)
    shown = table[table["section"].notna()].set_index("section")[categories]
    index = chunk_units.index
    out = shown.reindex(index)
    for codes, source in ((index.str[:7], districts), (index.str[:5], towns)):
        out = out.fillna(pd.DataFrame(source.reindex(codes).to_numpy(), index=index, columns=categories))
    out = out.fillna(pd.DataFrame([total.to_numpy()] * len(index), index=index, columns=categories))
    return out, pd.Series(index.isin(shown.index), index=index)


def fitted(frame: pd.DataFrame, totals: pd.Series, fallback: pd.DataFrame) -> pd.DataFrame:
    """Each section's split scaled to its total, as integers (largest remainders); a section with nothing to split takes `fallback`'s."""
    split = frame.to_numpy(dtype=float, copy=True)
    sums = split.sum(axis=1)
    empty = sums <= 0
    split[empty] = fallback.reindex(frame.index[empty]).to_numpy()
    sums = split.sum(axis=1)
    shares = np.divide(split, sums[:, None], out=np.zeros_like(split), where=sums[:, None] > 0)
    exact = shares * totals.reindex(frame.index).fillna(0).to_numpy()[:, None]
    floor = np.floor(exact)
    left = (np.round(exact.sum(axis=1)) - floor.sum(axis=1)).astype(int)
    rank = np.argsort(np.argsort(-(exact - floor), axis=1), axis=1)
    return pd.DataFrame(floor + (rank < left[:, None]), index=frame.index, columns=frame.columns)


def means(table: pd.DataFrame, chunk_units: pd.DataFrame, categories: list[str]) -> tuple[pd.DataFrame, pd.Series]:
    """Section means: as given, else their district's, municipality's or the chunk's (which are of shown sections only)."""
    values, shown = counts(table, chunk_units, categories)
    # A mean of 0 is a unit with nothing to average (no non-principal dwellings…): missing.
    return values.where(values > 0), shown


def official(dataset: str, dimension: str, category: str = "total") -> pd.Series:
    frame = pd.read_parquet(output_dir(PIPELINE) / dataset / "census_section.parquet")
    return frame[frame[dimension] == category].set_index("code")["value"]


def nuclei_estimate() -> pd.Series:
    """Each section's nuclei from its households by number of nuclei (three for "3 or more")."""
    frame = pd.read_parquet(output_dir(PIPELINE) / "households_by_nuclei_2021" / "census_section.parquet")
    frame = frame.set_index(["code", "household_nuclei"])["value"].unstack()
    return frame["nuclei_1"] + 2 * frame["nuclei_2"] + 3 * frame["nuclei_3_plus"]


def long(frame: pd.DataFrame, dimension: str, shown: pd.Series, extra: dict | None = None) -> pd.DataFrame:
    out = frame.rename_axis("code").reset_index().melt(id_vars="code", var_name=dimension)
    out["origin"] = np.where(out["code"].map(shown), "published", "imputed")
    return out.assign(period=PERIOD, **(extra or {}))


def build_counts(name: str, spec: dict, chunks: list[dict], weights: pd.Series, bases: dict) -> dict:
    dimension = spec["dimension"]
    leaves = list(dict.fromkeys(spec["codes"].values()))
    parts = []
    for table, group in spec["tables"].items():
        sections, shown_all, nucleus_totals = [], [], []
        for chunk in chunks:
            path = RAW / table / f"{chunk['id']}.px"
            if not path.exists():
                raise FileNotFoundError(path)
            frame = coded(read_px(path), spec["codes"], table)
            categories = [column for column in frame.columns if column in leaves]
            chunk_units = units(chunk, weights)
            values, shown = counts(frame, chunk_units, categories + ["TOTAL"])
            sections.append(values)
            shown_all.append(shown)
        values = pd.concat(sections)
        shown = pd.concat(shown_all)
        categories = [column for column in values.columns if column != "TOTAL"]
        # What each section's split adds up to: the official dwellings or households; nuclei, the tool's own (hidden: estimated from households).
        totals = bases[spec["base"]] if spec["base"] != "nuclei" else values["TOTAL"].round().where(shown, bases["nuclei"])
        district_split = values[categories].groupby(values.index.str[:7]).transform("sum")
        fit = fitted(values[categories], totals, district_split)
        fit["total"] = fit.sum(axis=1)
        parts.append(long(fit, dimension, shown, {"member_group": group} if group else None))
    base = pd.concat(parts, ignore_index=True)
    keys = ["code", "period", *(["member_group"] if "member_group" in base else []), dimension]
    for group_code, members in spec["groups"].items():
        summed = base[base[dimension].isin(members)].groupby([key for key in keys if key != dimension], as_index=False).agg(value=("value", "sum"), origin=("origin", "first"))
        base = pd.concat([base, summed.assign(**{dimension: group_code})], ignore_index=True)
    dimensions = [key for key in keys if key not in ("code", "period")]
    levels = rollup(base, "census_section", dimensions)
    levels["census_section"]["origin"] = base.set_index(["code", *dimensions])["origin"].reindex(pd.MultiIndex.from_frame(levels["census_section"][["code", *dimensions]])).to_numpy()
    return levels


def build_means(name: str, spec: dict, chunks: list[dict], weights: pd.Series) -> dict:
    dimension = spec["dimension"]
    table = next(iter(spec["tables"]))
    sections, shown_all = [], []
    for chunk in chunks:
        frame = coded(read_px(RAW / table / f"{chunk['id']}.px"), spec["codes"], table)
        categories = [code for code in dict.fromkeys(spec["codes"].values()) if code in frame.columns]
        values, shown = means(frame, units(chunk, weights), categories)
        sections.append(values)
        shown_all.append(shown)
    values, shown = pd.concat(sections), pd.concat(shown_all)
    base = long(values, dimension, shown).dropna(subset=["value"])
    # Weights for the levels above: the counts the means are of.
    of = spec["mean"]
    counts = pd.read_parquet(output_dir(PIPELINE) / of["dataset"] / "census_section.parquet")
    counts = counts.set_index(["code", of["dimension"]])["value"]
    base["weight"] = counts.reindex(pd.MultiIndex.from_frame(base[["code", dimension]])).fillna(0).to_numpy()
    ccaa = ccaa_by_province()
    levels = {"census_section": base}
    for level in LEVELS[1:]:
        grouped = base.assign(code=parent_codes(base["code"], level, ccaa), product=base["value"] * base["weight"])
        summed = grouped.groupby(["code", dimension], as_index=False)[["product", "weight"]].sum()
        frame = summed.assign(value=summed["product"] / summed["weight"].where(summed["weight"] > 0), period=PERIOD, origin="aggregated").dropna(subset=["value"])
        levels[level] = frame[["code", "period", dimension, "value", "origin"]]
    for level, frame in levels.items():
        frame = frame[["code", "period", dimension, "value", "origin"]].copy()
        frame.insert(0, "entity_id", COUNTRY_ID if level == "country" else ID_PREFIX[level] + frame["code"])
        levels[level] = frame.sort_values(["code", dimension], ignore_index=True)
    return levels


def main(names: list[str]) -> None:
    chunks = json.loads((RAW / "chunks.json").read_text())
    bases = {"dwellings": official("dwellings_2021", "dwelling"), "households": official("households_2021", "household_size")}
    if (output_dir(PIPELINE) / "households_by_nuclei_2021").exists():
        bases["nuclei"] = nuclei_estimate()
    stats = {}
    for name, spec in DATASETS.items():
        if names and name not in names:
            continue
        weights = bases["dwellings"] if spec.get("base", "dwellings") == "dwellings" and "mean" not in spec else bases["households"]
        if "mean" in spec:
            levels = build_means(name, spec, chunks, bases["dwellings"] if spec["mean"]["dataset"].startswith("dwellings") else bases["households"])
        else:
            levels = build_counts(name, spec, chunks, weights, bases)
        out = output_dir(PIPELINE) / name
        rows = write_levels(levels, out)
        if name == "households_by_nuclei_2021":
            bases["nuclei"] = nuclei_estimate()
        sections = levels["census_section"]
        stats[name] = {"rows_by_level": rows, "imputed_share": round(float((sections["origin"] == "imputed").mean()), 4)}
        metadata = {
            "dataset": name,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": {"operation": "INE Censos de Población y Viviendas 2021, custom tables (Crear tablas)", "tables": list(spec["tables"]), "raw": str(RAW)},
            "period": PERIOD,
            **stats[name],
        }
        (out / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
        log.info("Wrote %s: %s", out, stats[name])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Census 2021 detail by section, from INE's custom tables.")
    parser.add_argument("datasets", nargs="*", help=f"datasets to build (default: all): {', '.join(DATASETS)}")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main(args.datasets)
