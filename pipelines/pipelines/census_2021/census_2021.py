"""
Censos de Población y Viviendas 2021 (INE): a one-off picture of dwellings and households on
1 January 2021, down to census sections (as they were in 2021). Five datasets:

- dwellings_2021: conventional family dwellings, principal or not, and principal ones by tenure
  (owned, rented, other).
- households_2021: households by size (1 to 5 or more people).
- housing_means_2021: the dwellings' mean floor area (usable, estimated by INE from Catastro's built
  area), floor area per occupant, and mean household size: every level as INE publishes it in its
  census map viewer.
- dwelling_use_2021: dwellings by their electricity use in the year before (empty, very low use,
  sporadic, and by consumption band), in municipalities of 1,000 residents or more and up to Spain.
- electricity_consumption_2021: the dwellings' annual electricity consumption: percentiles by
  census district, the median by municipality (1,000 residents or more) and up.

Sources: the census's section indicators (C2021_Indicadores.csv, tables T18–T22), dwellings by type
and households by size for every municipality (tables 59525 and 59543), principal dwellings by
tenure by province and municipality size (59523), the dwellings' electricity use (59531, by
municipality and up; 59532, by district), and the census map viewer's layers (an ArcGIS service, one
per level, with the means).

Every level as INE publishes it where it does, summed from the level below where it doesn't:

- Sections as published. INE leaves 1,363 blank, nearly all municipalities under 100 residents with
  a single section: each municipality's figures (59525, 59543) less its published sections' are
  shared out among its blank sections by population; their principal dwellings are split by tenure
  like the unpublished rest of their province's municipalities of the same size (59523 less the
  published sections). `origin = "imputed"`.
- Districts summed from sections; municipalities as in 59525 and 59543, tenure summed from sections
  (INE has no municipal table for it); provinces, communities and Spain summed from municipalities.

INE calls the section figures provisional (some dwellings' sections were being updated): in a few
municipalities the sections add up to slightly more or less than the municipal table, recorded in
`meta.json`. The electricity datasets are published, not summed: only municipalities of 1,000
residents or more (INE gives the rest of each province together, "Resto de Almería": left out).

    python pipelines/census_2021/census_2021.py [--refresh]
"""

import argparse
import json
import logging
import re
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import requests

from common import ine
from common.download import download
from common.imputation import share_out
from common.paths import output_dir, raw_dir
from common.rollup import COUNTRY_ID, ID_PREFIX, ccaa_by_province, parent_codes, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "census_2021"
PERIOD = 2021
SECTIONS_URL = "https://www.ine.es/censos2021/C2021_Indicadores.csv"
DWELLINGS_TABLE, HOUSEHOLDS_TABLE, TENURE_TABLE, USE_TABLE, CONSUMPTION_TABLE = 59525, 59543, 59523, 59531, 59532

#: The section indicators' columns: dwellings (T18–T20) and households (T21–T22).
DWELLINGS = {"t18_1": "total", "t19_1": "principal", "t19_2": "non_principal", "t20_1": "owned", "t20_2": "rented", "t20_3": "other_tenure"}
HOUSEHOLDS = {"t21_1": "total", "t22_1": "1", "t22_2": "2", "t22_3": "3", "t22_4": "4", "t22_5": "5_plus"}
TENURE = ["owned", "rented", "other_tenure"]
DWELLING_TYPES = {"Total": "total", "Vivienda principal": "principal", "Vivienda no principal": "non_principal"}
HOUSEHOLD_SIZES = {"Total (tamaño del hogar)": "total", "1 persona": "1", "2 personas": "2", "3 personas": "3", "4 personas": "4", "5 o más personas": "5_plus"}
TENURE_LABELS = {"Total (régimen de tenencia)": "principal", "En propiedad": "owned", "En alquiler": "rented", "Otro régimen de tenencia": "other_tenure"}
#: Electricity use (59531): a partition of the dwellings, with sporadic use in two bands.
USE = {
    "Viviendas totales": "total",
    "Viviendas vacías": "empty",
    "Viviendas con bajo consumo": "very_low",
    "Viviendas de uso esporádico": "sporadic",
    "Viviendas de uso esporádico (entre 251 y 500 kwh)": "sporadic_251_500",
    "Viviendas de uso esporádico (entre 501 y 750 kwh)": "sporadic_501_750",
    "Viviendas con consumo entre 751 y 1.000 kwh": "kwh_751_1000",
    "Viviendas con consumo entre 1.001 y 2.000 kwh": "kwh_1001_2000",
    "Viviendas con consumo entre 2.001 y 3.000 kwh": "kwh_2001_3000",
    "Viviendas con consumo entre 3.001 y 4.000 kwh": "kwh_3001_4000",
    "Viviendas con consumo entre 4.001 y 5.000 kwh": "kwh_4001_5000",
    "Viviendas con consumo entre 5.001 y 6.000 kwh": "kwh_5001_6000",
    "Viviendas con consumo entre 6.001 y 7.000 kwh": "kwh_6001_7000",
    "Viviendas con consumo entre 7.001 y 8.000 kwh": "kwh_7001_8000",
    "Viviendas con consumo entre 8.001 y 9.000 kwh": "kwh_8001_9000",
    "Viviendas con consumo entre 9.001 y 10.000 kwh": "kwh_9001_10000",
    "Viviendas con consumo mayor de 10.000 kwh": "kwh_over_10000",
}
MEDIAN = "Mediana consumo anual"
PERCENTILES = {f"Percentil {n} de consumo eléctrico en kwh": ("median" if n == 50 else f"p{n}") for n in (10, 25, 50, 75, 90)}
#: The census map viewer's layers (ArcGIS feature service), by level, and the field with each unit's code.
VISOR_URL = "https://www.ine.es/servergis/rest/services/Hosted/SAS_seleccion_2021/FeatureServer/{layer}/query"
VISOR_LAYERS = {"country": (1, None), "autonomous_community": (2, "cca"), "province": (3, "cpro"), "municipality": (4, "cumun"), "census_district": (5, "cudis"), "census_section": (6, "cusec")}
#: Each level's unit above, to fill a hidden mean from.
LEVELS_UP = {"autonomous_community": "country", "province": "autonomous_community", "municipality": "province", "census_district": "municipality", "census_section": "census_district"}
MEANS = {"superf_med": "mean_floor_area", "superf_m_1": "floor_area_per_occupant", "tama_hogar": "mean_household_size"}
#: How far the provisional sections may be from the municipal tables before the run stops.
MAX_PROVISIONAL = {"municipalities": 60, "difference": 1000}


def fetch(raw, refresh: bool) -> dict:
    sections = raw / "C2021_Indicadores.csv"
    if refresh or not sections.exists():
        download(SECTIONS_URL, sections)
    tables = {table: ine.fetch_table(table, raw / f"{table}.csv", refresh, url=ine.PX_CSV_URL) for table in (DWELLINGS_TABLE, HOUSEHOLDS_TABLE, TENURE_TABLE, USE_TABLE, CONSUMPTION_TABLE)}
    visor = {}
    for level, (layer, _) in VISOR_LAYERS.items():
        visor[level] = raw / f"visor_{level}.json"
        if refresh or not visor[level].exists():
            visor[level].write_text(json.dumps(query_layer(layer), ensure_ascii=False))
    return {"sections": sections, **tables, "visor": visor}


def query_layer(layer: int) -> list[dict]:
    """Every feature's attributes (no geometry) of one of the viewer's layers, page by page."""
    rows, offset = [], 0
    while True:
        response = requests.get(VISOR_URL.format(layer=layer), params={"where": "1=1", "outFields": "*", "returnGeometry": "false", "resultOffset": offset, "resultRecordCount": 2000, "f": "json"}, timeout=120)
        response.raise_for_status()
        page = response.json()
        if "error" in page:
            raise ValueError(f"Viewer layer {layer}: {page['error']}")
        rows += [feature["attributes"] for feature in page["features"]]
        if not page.get("exceededTransferLimit") and len(page["features"]) < 2000:
            return rows
        offset += len(page["features"])


def housing_means(paths: dict) -> tuple[dict, dict]:
    """
    The viewer's means at every level, as published. A 0 is a hidden figure (a few sections' and
    small municipalities' floor areas): it takes the unit above's, from the top down. A unit without
    households has no mean household size or area per occupant.
    """
    ccaa = ccaa_by_province()
    out, stats = {}, {"inherited": {}, "no_households": 0}
    for level, (_, field) in VISOR_LAYERS.items():
        frame = pd.DataFrame(json.loads(paths[level].read_text()))
        frame.columns = frame.columns.str.lower()
        codes = frame[field] if field else pd.Series("es", index=frame.index)
        long = frame.assign(code=codes).melt(id_vars=["code", "hogares"], value_vars=list(MEANS), var_name="field").assign(housing_indicator=lambda part: part["field"].map(MEANS))
        no_households = (long["hogares"] == 0) & (long["housing_indicator"] != "mean_floor_area")
        stats["no_households"] += int(no_households.sum())
        long = long[~no_households].assign(origin="published")
        hidden = long["value"] <= 0
        if hidden.any():
            if level == "country":
                raise ValueError("Viewer: hidden means for Spain")
            parent = LEVELS_UP[level]
            above = out[parent].set_index(["code", "housing_indicator"])["value"]
            keys = pd.MultiIndex.from_arrays([parent_codes(long.loc[hidden, "code"], parent, ccaa), long.loc[hidden, "housing_indicator"]])
            long.loc[hidden, "value"] = above.reindex(keys).to_numpy()
            long.loc[hidden, "origin"] = "imputed"
            stats["inherited"][level] = int(hidden.sum())
        if long.duplicated(["code", "housing_indicator"]).any():
            raise ValueError(f"Viewer: repeated units at {level}")
        out[level] = long.assign(period=PERIOD)[["code", "period", "housing_indicator", "value", "origin"]]
    levels = {}
    for level, frame in out.items():
        frame = frame.copy()
        frame.insert(0, "entity_id", COUNTRY_ID if level == "country" else ID_PREFIX[level] + frame["code"])
        levels[level] = frame.sort_values(["code", "housing_indicator"], ignore_index=True)
    return levels, stats


def read_sections(path) -> pd.DataFrame:
    """One row per 2021 section: its code, population, and the dwelling and household counts (NaN where blank)."""
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame = pd.DataFrame({"code": table["cpro"] + table["cmun"] + table["dist"] + table["secc"], "population": pd.to_numeric(table["t1_1"])})
    for column in [*DWELLINGS, *HOUSEHOLDS]:
        frame[column] = pd.to_numeric(table[column].replace("", None))
    if frame["code"].str.len().ne(10).any() or frame["code"].duplicated().any():
        raise ValueError("Unexpected section codes")
    return frame.assign(municipality=frame["code"].str[:5])


def read_municipal(path, codes: dict[str, str]) -> pd.DataFrame:
    """A municipal table (and its national row) as code, category, value."""
    table = ine.read_table(path)
    category = codelists_mapped(table.iloc[:, 2], codes, table.columns[2])
    frame = pd.DataFrame({"code": np.where(table["Municipios"] == "", "es", ine.codes(table["Municipios"])), "category": category, "value": ine.values(table["Total"])})
    if frame["value"].isna().any():
        raise ValueError(f"{path.name}: hidden or empty cells")
    return frame


def codelists_mapped(labels: pd.Series, codes: dict[str, str], name: str) -> pd.Series:
    unknown = set(labels) - set(codes)
    if unknown:
        raise ValueError(f"Unknown {name} labels: {sorted(unknown)}")
    return labels.map(codes)


def size_class(label: str) -> tuple[float, float]:
    """INE's municipality sizes ("Menos de 101 habitantes", "De 101 a 500", "Más de 500.000") as [low, high]."""
    number = lambda text: float(text.replace(".", ""))
    if match := re.fullmatch(r"Menos de ([\d.]+) habitantes", label):
        return 0, number(match[1]) - 1
    if match := re.fullmatch(r"De ([\d.]+) a ([\d.]+)( habitantes)?", label):
        return number(match[1]), number(match[2])
    if match := re.fullmatch(r"Más de ([\d.]+)( habitantes)?", label):
        return number(match[1]) + 1, np.inf
    raise ValueError(f"Unknown municipality size: {label!r}")


def impute_counts(sections: pd.DataFrame, municipal: pd.DataFrame, columns: dict[str, str], parts: list[str]) -> pd.DataFrame:
    """
    Blank sections' counts of `parts` (categories that add up to the total): their municipality's
    figure less its published sections', shared out by population. Returns code, category, value.
    """
    names = {category: column for column, category in columns.items()}
    blank = sections[sections[names["total"]].isna()]
    published = sections[sections[names["total"]].notna()]
    long = published.melt(id_vars=["municipality"], value_vars=[names[part] for part in parts], var_name="column")
    summed = long.assign(category=long["column"].map(columns)).groupby(["municipality", "category"], as_index=False)["value"].sum()
    official = municipal[municipal["category"].isin(parts)].rename(columns={"code": "municipality"})
    residual = official.merge(summed, on=["municipality", "category"], how="left", suffixes=("", "_sections")).fillna({"value_sections": 0})
    residual = residual.assign(residual=residual["value"] - residual["value_sections"], period=PERIOD, unit="all")[["municipality", "period", "category", "residual"]]
    hidden = blank[["code", "municipality"]].merge(pd.DataFrame({"category": parts}), how="cross").assign(period=PERIOD, unit="all")
    weights = pd.Series(blank["population"].to_numpy(), index=pd.MultiIndex.from_arrays([blank["code"], np.full(len(blank), PERIOD), np.full(len(blank), "all")]))
    hidden["value"] = share_out(residual, hidden, weights, "municipality", ["category"], by="unit")
    return hidden[["code", "category", "value"]]


def impute_tenure(sections: pd.DataFrame, principal: pd.Series, tenure_table: pd.DataFrame) -> pd.DataFrame:
    """
    Blank sections' principal dwellings by tenure: split like their province's unpublished rest of
    municipalities of the same size (59523 less the published sections), largest remainders.
    """
    population = sections.groupby("municipality")["population"].sum()
    classes = tenure_table[["size", "low", "high"]].drop_duplicates()
    size_of = lambda people: classes.loc[(classes["low"] <= people) & (people <= classes["high"]), "size"].iloc[0]
    sizes = population.map(size_of)
    published = sections[sections["t20_1"].notna()].assign(province=lambda frame: frame["code"].str[:2], size=lambda frame: frame["municipality"].map(sizes))
    summed = published.groupby(["province", "size"])[["t20_1", "t20_2", "t20_3"]].sum().set_axis(TENURE, axis=1)
    totals = tenure_table[tenure_table["category"].isin(TENURE)].pivot_table(index=["province", "size"], columns="category", values="value")[TENURE]
    rest = (totals - summed.reindex(totals.index).fillna(0)).clip(lower=0)
    # Where nothing's left (the published sections already add up), the class's own split.
    shares = rest.div(rest.sum(axis=1), axis=0).where(rest.sum(axis=1) > 0, totals.div(totals.sum(axis=1), axis=0))

    blank = sections[sections["t18_1"].isna()]
    keys = pd.MultiIndex.from_arrays([blank["code"].str[:2], blank["municipality"].map(sizes)])
    split = shares.reindex(keys).to_numpy() * principal.reindex(blank["code"]).to_numpy()[:, None]
    floor = np.floor(split)
    left = (principal.reindex(blank["code"]).to_numpy() - floor.sum(axis=1)).round().astype(int)
    rank = np.argsort(np.argsort(-(split - floor), axis=1), axis=1)
    values = floor + (rank < left[:, None])
    return pd.DataFrame(values, columns=TENURE).assign(code=blank["code"].to_numpy()).melt(id_vars="code", var_name="category")


def provinces_in(labels: pd.Series) -> pd.Series:
    """
    The province code of each label in a column that lists every community followed by its provinces
    ("01 Andalucía", "04 Almería"…; codes overlap): a label is a province when its code belongs to the
    community before it. NaN for Spain and the communities.
    """
    community_of = ccaa_by_province()
    kinds, current = {}, None
    for label in dict.fromkeys(labels):
        code = label[:2]
        if label == "Total Nacional":
            continue
        if current is not None and community_of.get(code) == current:
            kinds[label] = code
        else:
            current, kinds[label] = code, None
    found = {code for code in kinds.values() if code}
    if found != set(community_of.index):
        raise ValueError(f"Provinces not found as expected: {sorted(set(community_of.index) ^ found)}")
    return labels.map(kinds)


def tenure_by_province(path) -> pd.DataFrame:
    """59523: principal dwellings by tenure, province and municipality size (with each size's range)."""
    table = ine.read_table(path)
    frame = pd.DataFrame(
        {
            "province": provinces_in(table["Comunidad Autónoma y Provincia"]),
            "category": codelists_mapped(table["Régimen de tenencia de la vivienda"], TENURE_LABELS, "tenure"),
            "size": table["Tamaño del municipio"],
            "value": ine.values(table["Total"]),
        }
    )
    frame = frame[frame["province"].notna()]
    bounds = frame["size"].map(lambda label: (0, np.inf) if label.startswith("Total") else size_class(label))
    return frame.assign(low=bounds.str[0], high=bounds.str[1])


def counts(sections: pd.DataFrame, columns: dict[str, str], dimension: str, municipal: pd.DataFrame, parts: list[str], tenure: pd.DataFrame | None = None) -> dict:
    """A count dataset by level, and its checks: sections (blank ones imputed) up to Spain."""
    names = {category: column for column, category in columns.items()}
    published = sections[sections[names["total"]].notna()]
    long = published.melt(id_vars=["code"], value_vars=list(columns), var_name="column")
    base = long.assign(category=long["column"].map(columns), origin="published")[["code", "category", "value", "origin"]]
    imputed = impute_counts(sections, municipal, columns, parts)
    totals = imputed.groupby("code", as_index=False)["value"].sum().assign(category="total")
    extra = [imputed, totals]
    if tenure is not None:
        principal = imputed[imputed["category"] == "principal"].set_index("code")["value"]
        extra.append(impute_tenure(sections, principal, tenure))
    base = pd.concat([base, *[frame.assign(origin="imputed") for frame in extra]], ignore_index=True)
    base = base.rename(columns={"category": dimension}).assign(period=PERIOD)
    if base["value"].isna().any():
        raise ValueError(f"{dimension}: empty section cells left")

    by_section = rollup(base, "census_section", [dimension])
    by_section["census_section"]["origin"] = base.set_index(["code", dimension])["origin"].reindex(pd.MultiIndex.from_frame(by_section["census_section"][["code", dimension]])).to_numpy()
    # Municipalities as INE publishes them; what it doesn't (tenure), summed from sections.
    official = municipal[municipal["code"] != "es"].rename(columns={"category": dimension}).assign(period=PERIOD)
    summed = by_section["municipality"]
    rest = summed[~summed[dimension].isin(official[dimension].unique())][["code", "period", dimension, "value"]]
    municipalities = pd.concat([official.assign(origin="published"), rest.assign(origin="aggregated")], ignore_index=True)
    upper = rollup(municipalities, "municipality", [dimension])
    upper["municipality"]["origin"] = municipalities.set_index(["code", dimension])["origin"].reindex(pd.MultiIndex.from_frame(upper["municipality"][["code", dimension]])).to_numpy()

    # The provisional sections against the municipal tables.
    compare = summed.merge(official, on=["code", "period", dimension], suffixes=("_sections", "_municipal"))
    compare["difference"] = compare["value_sections"] - compare["value_municipal"]
    differing = compare[compare["difference"] != 0]
    provisional = {
        "compared": int(len(compare)),
        "municipalities_differing": int(differing["code"].nunique()),
        "max_difference": float(differing["difference"].abs().max()) if len(differing) else 0.0,
        "examples": differing.sort_values("difference", key=abs, ascending=False).head(10)[["code", dimension, "value_sections", "value_municipal"]].to_dict("records"),
    }
    log.info("%s: sections against municipalities: %s", dimension, {key: value for key, value in provisional.items() if key != "examples"})
    if provisional["municipalities_differing"] > MAX_PROVISIONAL["municipalities"] or provisional["max_difference"] > MAX_PROVISIONAL["difference"]:
        raise ValueError(f"{dimension}: sections too far from the municipal tables: {provisional}")
    spain = municipal[municipal["code"] == "es"].set_index("category")["value"]
    country = upper["country"].set_index(dimension)["value"].reindex(spain.index)
    if (country != spain).any():
        raise ValueError(f"{dimension}: municipalities don't add up to Spain: {country.compare(spain)}")
    levels = {"census_section": by_section["census_section"], "census_district": by_section["census_district"], **upper}
    return {"levels": levels, "checks": {"sections_against_municipalities": provisional, "spain": "exact"}, "imputed_sections": int(sections[names["total"]].isna().sum())}


def tenure_check(levels: dict, tenure: pd.DataFrame) -> dict:
    """Provinces' principal dwellings by tenure (summed from sections) against 59523."""
    published = tenure[tenure["size"].str.startswith("Total")].rename(columns={"province": "code"})
    mine = levels["province"].rename(columns={"dwelling": "category"})
    merged = published.merge(mine, on=["code", "category"], suffixes=("_ine", "_here"))
    merged["difference"] = merged["value_here"] - merged["value_ine"]
    out = {"compared": int(len(merged)), "max_difference": float(merged["difference"].abs().max()), "max_relative": round(float((merged["difference"].abs() / merged["value_ine"]).max()), 5)}
    log.info("Provinces' tenure against 59523: %s", out)
    if out["max_relative"] > 0.01:
        raise ValueError(f"Provinces' tenure more than 1% off INE's: {out}")
    return out


def electricity(use_path, consumption_path) -> tuple[dict, dict]:
    """59531 by municipality (1,000 residents or more), province, community and Spain; 59532 by district."""
    table = ine.read_table(use_path)
    ccaa, province, municipality = table["Comunidades y Ciudades Autónomas"], table["Provincias"], table["Municipios"]
    level = np.select([municipality != "", province != "", ccaa != ""], ["municipality", "province", "autonomous_community"], "country")
    code = np.select([municipality != "", province != "", ccaa != ""], [ine.codes(municipality), province.str[:2], ccaa.str[:2]], "es")
    frame = pd.DataFrame({"level": level, "code": code, "label": table["Consumo eléctrico"], "value": ine.values(table["Total"])})
    # "Resto de Almería" (04999): the province's municipalities under 1,000 residents together, not a unit.
    frame = frame[~((frame["level"] == "municipality") & frame["code"].str.endswith("999"))]
    unknown = set(frame["label"]) - set(USE) - {MEDIAN}
    if unknown or frame["value"].isna().any():
        raise ValueError(f"59531: unknown labels {sorted(unknown)} or empty cells")
    use = frame[frame["label"] != MEDIAN].assign(dwelling_use=lambda part: part["label"].map(USE))
    regular = use[use["dwelling_use"].str.startswith("kwh_")].groupby(["level", "code"], as_index=False)["value"].sum().assign(dwelling_use="regular")
    use = pd.concat([use, regular], ignore_index=True)
    wide = use.pivot_table(index=["level", "code"], columns="dwelling_use", values="value")
    parts = wide[["empty", "very_low", "sporadic", "regular"]].sum(axis=1)
    if (parts != wide["total"]).any() or (wide["sporadic_251_500"] + wide["sporadic_501_750"] != wide["sporadic"]).any():
        raise ValueError("59531: the uses don't add up to the dwellings")

    median = frame[frame["label"] == MEDIAN].assign(consumption_statistic="median")
    districts = ine.read_table(consumption_path)
    percentiles = pd.DataFrame({"level": "census_district", "code": ine.codes(districts["Distritos"]), "consumption_statistic": codelists_mapped(districts["Percentil"], PERCENTILES, "Percentil"), "value": ine.values(districts["Total"])})
    if percentiles["value"].isna().any():
        raise ValueError("59532: empty cells")
    consumption = pd.concat([median, percentiles], ignore_index=True)
    return by_level(use, "dwelling_use"), by_level(consumption, "consumption_statistic")


def by_level(frame: pd.DataFrame, dimension: str) -> dict[str, pd.DataFrame]:
    out = {}
    for level, part in frame.groupby("level"):
        part = part.assign(period=PERIOD, origin="published")
        part.insert(0, "entity_id", COUNTRY_ID if level == "country" else ID_PREFIX[level] + part["code"])
        out[level] = part[["entity_id", "code", "period", dimension, "value", "origin"]].sort_values(["code", dimension], ignore_index=True)
    return out


def write(name: str, levels: dict, sources: list, extra: dict) -> None:
    out = output_dir(PIPELINE) / name
    rows = write_levels(levels, out)
    metadata = {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"operation": "INE Censos de Población y Viviendas 2021", "files": sources},
        "period": PERIOD,
        "rows_by_level": rows,
        **extra,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
    log.info("Wrote %s: %s", out, rows)


def build(refresh: bool) -> None:
    paths = fetch(raw_dir(PIPELINE, date.today().isoformat()), refresh)
    sections = read_sections(paths["sections"])
    tenure = tenure_by_province(paths[TENURE_TABLE])

    dwellings = counts(sections, DWELLINGS, "dwelling", read_municipal(paths[DWELLINGS_TABLE], DWELLING_TYPES), ["principal", "non_principal"], tenure)
    dwellings["checks"]["tenure_against_provinces"] = tenure_check(dwellings["levels"], tenure)
    write("dwellings_2021", dwellings["levels"], ["C2021_Indicadores.csv", DWELLINGS_TABLE, TENURE_TABLE], {"checks": dwellings["checks"], "imputed_sections": dwellings["imputed_sections"]})

    households = counts(sections, HOUSEHOLDS, "household_size", read_municipal(paths[HOUSEHOLDS_TABLE], HOUSEHOLD_SIZES), ["1", "2", "3", "4", "5_plus"])
    write("households_2021", households["levels"], ["C2021_Indicadores.csv", HOUSEHOLDS_TABLE], {"checks": households["checks"], "imputed_sections": households["imputed_sections"]})

    means, stats = housing_means(paths["visor"])
    write("housing_means_2021", means, ["census map viewer (SAS_seleccion_2021 feature service)"], stats)

    use, consumption = electricity(paths[USE_TABLE], paths[CONSUMPTION_TABLE])
    write("dwelling_use_2021", use, [USE_TABLE], {"municipalities": int(len(use["municipality"]["code"].unique()))})
    write("electricity_consumption_2021", consumption, [USE_TABLE, CONSUMPTION_TABLE], {"districts": int(len(consumption["census_district"]["code"].unique()))})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Census 2021 (INE): dwellings, households and dwellings' electricity use, down to census sections.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    build(args.refresh)
