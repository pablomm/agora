"""
Atlas de Distribución de Renta de los Hogares (ADRH, INE operation 353), 2015 on: household income
by census section, district and municipality (one table per province and kind), and by province,
autonomous community and Spain (one national table per kind). Six datasets:

- income_levels: net and gross mean income per person and per household, mean and median income per
  consumption unit (euros).
- income_sources: share of gross income from wages, pensions, unemployment benefits, other benefits
  and other income (%).
- income_inequality: Gini index and the P80/P20 ratio.
- income_demographics: household size, single-person households, and ADRH's population figures.
- income_relative: % of the population with income per consumption unit below 40, 50 or 60% of the
  median or above 140, 160 or 200%, by sex and by age band or nationality.
- income_fixed: the same below 5,000, 7,500 and 10,000 euros.

They're means, medians and shares, not counts: every level is kept as INE publishes it, nothing is
summed. INE hides units with few tax returns ("."); none is left blank (`origin = "imputed"`),
filled from the top down (province, municipality, district, section):

- A breakdown's cell (by sex, age or nationality) whose unit total is known: the unit's total times
  the cell's ratio to the total in the unit above (a section's poverty rate for those under 18 is the
  section's rate times its district's under-18 to overall ratio). Shares are capped at 100.
- Anything else: the value of the unit above (a section's district, else its municipality…).
- Population, a count: what the unit above has beyond its published units, shared among the hidden
  ones by their size in the years they're published.
- With nothing above (foral municipalities before 2020, when their province and Spain aren't
  available): the same unit's value in the nearest year.

A few units in 2015 have the shares above 140, 160 and 200% of the median rising (likely their
complement, published by mistake): taken as hidden.

Cells INE leaves empty or marks ".." (not available: Spain as a whole before 2021, some foral
indicators before 2020) aren't hidden figures, and are left out.

The period is the income year (data published about two years later).

    python pipelines/income/adrh.py [dataset ...] [--refresh]
"""

import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as compute
import pyarrow.csv as csv
import pyarrow.parquet as pq

from common import codelists, ine
from common.imputation import share_out
from common.paths import output_dir, raw_dir
from common.rollup import COUNTRY_ID, ID_PREFIX, ccaa_by_province

log = logging.getLogger(__name__)

PIPELINE = "income"

#: The tables of each kind, as INE's operation 353 lists them: one per province (municipalities,
#: districts, sections) and the national one (Spain, autonomous communities, provinces), last.
TABLES = {
    "income_levels": [
        30656, 30824, 30833, 30842, 30851, 30860, 30869, 30878, 30887, 30896, 30917, 30926, 30935, 30944, 30953, 30962, 30971, 30980, 30989, 30998, 31007,
        31016, 31025, 31034, 31043, 31052, 31061, 31070, 31079, 31088, 31097, 31106, 31115, 31124, 31133, 31142, 31151, 31160, 31169, 31178, 31187, 31196,
        31205, 31214, 31223, 31232, 31241, 31250, 31259, 31268, 31277, 31286, 31295, 53689
    ],
    "income_sources": [
        30813, 30825, 30834, 30843, 30852, 30861, 30870, 30879, 30888, 30897, 30918, 30927, 30936, 30945, 30954, 30963, 30972, 30981, 30990, 30999, 31008,
        31017, 31026, 31035, 31044, 31053, 31062, 31071, 31080, 31089, 31098, 31107, 31116, 31125, 31134, 31143, 31152, 31161, 31170, 31179, 31188, 31197,
        31206, 31215, 31224, 31233, 31242, 31251, 31260, 31269, 31278, 31287, 31296, 53687
    ],
    "fixed_sex": [
        30657, 30826, 30835, 30844, 30853, 30862, 30871, 30880, 30889, 30898, 30919, 30928, 30937, 30946, 30955, 30964, 30973, 30982, 30991, 31000, 31018,
        31027, 31036, 31045, 31054, 31063, 31072, 31081, 31090, 31099, 31108, 31117, 31126, 31135, 31144, 31153, 31162, 31171, 31180, 31189, 31198, 31207,
        31216, 31225, 31234, 31243, 31252, 31261, 31270, 31279, 31288, 31297, 48549, 53690
    ],
    "fixed_age": [
        30659, 30827, 30836, 30845, 30854, 30863, 30872, 30881, 30890, 30899, 30920, 30929, 30938, 30947, 30956, 30965, 30974, 30983, 30992, 31001, 31019,
        31028, 31037, 31046, 31055, 31064, 31073, 31082, 31091, 31100, 31109, 31118, 31127, 31136, 31145, 31154, 31163, 31172, 31181, 31190, 31199, 31208,
        31217, 31226, 31235, 31244, 31253, 31262, 31271, 31280, 31289, 31298, 37728, 53692
    ],
    "fixed_nationality": [
        30660, 30828, 30837, 30846, 30855, 30864, 30873, 30882, 30891, 30900, 30921, 30930, 30939, 30948, 30957, 30966, 30975, 30984, 30993, 31002, 31020,
        31029, 31038, 31047, 31056, 31065, 31074, 31083, 31092, 31101, 31110, 31119, 31128, 31137, 31146, 31155, 31164, 31173, 31182, 31191, 31200, 31209,
        31218, 31227, 31236, 31245, 31254, 31263, 31272, 31281, 31290, 31299, 48439, 53693
    ],
    "relative_sex": [
        30661, 30829, 30838, 30847, 30856, 30865, 30874, 30883, 30892, 30901, 30922, 30931, 30940, 30949, 30958, 30967, 30976, 30985, 30994, 31003, 31021,
        31030, 31039, 31048, 31057, 31066, 31075, 31084, 31093, 31102, 31111, 31120, 31129, 31138, 31147, 31156, 31165, 31174, 31183, 31192, 31201, 31210,
        31219, 31228, 31237, 31246, 31255, 31264, 31273, 31282, 31291, 31300, 37742, 53694
    ],
    "relative_age": [
        30662, 30830, 30839, 30848, 30857, 30866, 30875, 30884, 30893, 30902, 30923, 30932, 30941, 30950, 30959, 30968, 30977, 30986, 30995, 31004, 31022,
        31031, 31040, 31049, 31058, 31067, 31076, 31085, 31094, 31103, 31112, 31121, 31130, 31139, 31148, 31157, 31166, 31175, 31184, 31193, 31202, 31211,
        31220, 31229, 31238, 31247, 31256, 31265, 31274, 31283, 31292, 31301, 37729, 53695
    ],
    "relative_nationality": [
        30663, 30831, 30840, 30849, 30858, 30867, 30876, 30885, 30894, 30903, 30924, 30933, 30942, 30951, 30960, 30969, 30978, 30987, 30996, 31005, 31023,
        31032, 31041, 31050, 31059, 31068, 31077, 31086, 31095, 31104, 31113, 31122, 31131, 31140, 31149, 31158, 31167, 31176, 31185, 31194, 31203, 31212,
        31221, 31230, 31239, 31248, 31257, 31266, 31275, 31284, 31293, 31302, 48550, 53696
    ],
    "gini": [
        37607, 37608, 37677, 37678, 37679, 37680, 37682, 37683, 37684, 37685, 37686, 37687, 37688, 37689, 37690, 37691, 37692, 37693, 37694, 37695, 37697,
        37698, 37699, 37700, 37701, 37702, 37703, 37704, 37705, 37706, 37707, 37708, 37709, 37710, 37711, 37712, 37713, 37714, 37715, 37716, 37717, 37718,
        37719, 37720, 37721, 37722, 37723, 37724, 37727, 37730, 37731, 37732, 37733, 53688
    ],
    "demographics": [
        30814, 30832, 30841, 30850, 30859, 30868, 30877, 30886, 30895, 30904, 30925, 30934, 30943, 30952, 30961, 30970, 30979, 30988, 30997, 31006, 31015,
        31024, 31033, 31042, 31051, 31060, 31069, 31078, 31087, 31096, 31105, 31114, 31123, 31132, 31141, 31150, 31159, 31168, 31177, 31186, 31195, 31204,
        31213, 31222, 31231, 31240, 31249, 31258, 31267, 31276, 31285, 31294, 31303, 53776
    ],
}

INDICATORS = {
    "Renta neta media por persona": "net_per_person",
    "Renta neta media por hogar": "net_per_household",
    "Media de la renta por unidad de consumo": "mean_per_consumption_unit",
    "Mediana de la renta por unidad de consumo": "median_per_consumption_unit",
    "Renta bruta media por persona": "gross_per_person",
    "Renta bruta media por hogar": "gross_per_household",
}
SOURCES = {
    "Fuente de ingreso: salario": "wages",
    "Fuente de ingreso: pensiones": "pensions",
    "Fuente de ingreso: prestaciones por desempleo": "unemployment_benefits",
    "Fuente de ingreso: otras prestaciones": "other_benefits",
    "Fuente de ingreso: otros ingresos": "other_income",
}
INEQUALITY = {"Índice de Gini": "gini", "Distribución de la renta P80/P20": "p80_p20"}
DEMOGRAPHICS = {
    "Edad media de la población": "mean_age",
    "Población": "population",
    "Porcentaje de hogares unipersonales": "single_person_households",
    "Porcentaje de población de 65 y más años": "share_65_plus",
    "Porcentaje de población española": "share_spanish",
    "Porcentaje de población menor de 18 años": "share_under_18",
    "Tamaño medio del hogar": "household_size",
}
RELATIVE = {
    "Población con ingresos por unidad de consumo por debajo 40% de la mediana": "below_40",
    "Población con ingresos por unidad de consumo por debajo 50% de la mediana": "below_50",
    "Población con ingresos por unidad de consumo por debajo 60% de la mediana": "below_60",
    "Población con ingresos por unidad de consumo por encima 140% de la mediana": "above_140",
    "Población con ingresos por unidad de consumo por encima 160% de la mediana": "above_160",
    "Población con ingresos por unidad de consumo por encima 200% de la mediana": "above_200",
}
FIXED = {
    "Población con ingresos por unidad de consumo por debajo de 5.000 Euros": "below_5000",
    "Población con ingresos por unidad de consumo por debajo de 7.500 Euros": "below_7500",
    "Población con ingresos por unidad de consumo por debajo de 10.000 Euros": "below_10000",
}
#: Age bands and nationality, both in one `income_group` dimension (with the total); the code
#: keeps it as `group` until it writes the files.
GROUPS = {
    "Total": "total",
    "Menos de 18 años": "under_18",
    "De 18 a 64 años": "18_64",
    "65 y más años": "65_plus",
    "Española": "spanish",
    "Extranjera": "foreign",
}

#: Autonomous communities and provinces as the national tables name them (no codes there).
CCAA = {
    "Andalucía": "01", "Aragón": "02", "Asturias, Principado de": "03", "Balears, Illes": "04", "Canarias": "05", "Cantabria": "06", "Castilla y León": "07",
    "Castilla - La Mancha": "08", "Cataluña": "09", "Comunitat Valenciana": "10", "Extremadura": "11", "Galicia": "12", "Madrid, Comunidad de": "13",
    "Murcia, Región de": "14", "Navarra, Comunidad Foral de": "15", "País Vasco": "16", "Rioja, La": "17", "Ceuta": "18", "Melilla": "19",
}
PROVINCES = {
    "Araba/Álava": "01", "Albacete": "02", "Alicante/Alacant": "03", "Almería": "04", "Ávila": "05", "Badajoz": "06", "Balears, Illes": "07", "Barcelona": "08",
    "Burgos": "09", "Cáceres": "10", "Cádiz": "11", "Castellón/Castelló": "12", "Ciudad Real": "13", "Córdoba": "14", "Coruña, A": "15", "Cuenca": "16",
    "Girona": "17", "Granada": "18", "Guadalajara": "19", "Gipuzkoa": "20", "Huelva": "21", "Huesca": "22", "Jaén": "23", "León": "24", "Lleida": "25",
    "Rioja, La": "26", "Lugo": "27", "Madrid": "28", "Málaga": "29", "Murcia": "30", "Navarra": "31", "Ourense": "32", "Asturias": "33", "Palencia": "34",
    "Palmas, Las": "35", "Pontevedra": "36", "Salamanca": "37", "Santa Cruz de Tenerife": "38", "Cantabria": "39", "Segovia": "40", "Sevilla": "41",
    "Soria": "42", "Tarragona": "43", "Teruel": "44", "Toledo": "45", "Valencia/València": "46", "Valladolid": "47", "Bizkaia": "48", "Zamora": "49",
    "Zaragoza": "50", "Ceuta": "51", "Melilla": "52",
}

#: Each dataset: the kinds of tables it merges, its measure column and code list, and whether it
#: has a breakdown (sex and group) to impute by ratio.
DATASETS = {
    "income_levels": {"kinds": ["income_levels"], "dimension": "income_indicator", "codes": INDICATORS},
    "income_sources": {"kinds": ["income_sources"], "dimension": "income_source", "codes": SOURCES},
    "income_inequality": {"kinds": ["gini"], "dimension": "inequality_indicator", "codes": INEQUALITY},
    "income_demographics": {"kinds": ["demographics"], "dimension": "household_indicator", "codes": DEMOGRAPHICS},
    "income_relative": {"kinds": ["relative_sex", "relative_age", "relative_nationality"], "dimension": "income_threshold", "codes": RELATIVE, "breakdown": True},
    "income_fixed": {"kinds": ["fixed_sex", "fixed_age", "fixed_nationality"], "dimension": "income_threshold_fixed", "codes": FIXED, "breakdown": True},
}
#: Levels from the top: each is filled from the one above (and, missing that, the next one up).
LEVELS = ["country", "autonomous_community", "province", "municipality", "census_district", "census_section"]
GEOGRAPHY = {"Secciones": "census_section", "Distritos": "census_district", "Municipios": "municipality"}
NATIONAL = {"Islas": None, "Provincias": "province", "Comunidades y Ciudades Autónomas": "autonomous_community"}


def read(path: Path, dimension: str, codes: dict[str, str]) -> pd.DataFrame:
    """One table's rows: level, code, period, sex and group (totals where the table has none), the dimension, value and hidden."""
    table = csv.read_csv(
        path,
        parse_options=csv.ParseOptions(delimiter=";"),
        convert_options=csv.ConvertOptions(strings_can_be_null=False, column_types={"Total": "string"}, auto_dict_encode=True),
    )
    names = table.column_names
    period = "Periodo" if "Periodo" in names else "Period"
    # The measure is the column that's neither geography nor a breakdown.
    measure = next(name for name in names if name not in (*GEOGRAPHY, *NATIONAL, "Total Nacional", "Sexo", "Tramos de edad", "Nacionalidad", period, "Total"))
    frame = table.to_pandas()
    english = period == "Period"
    raw = frame["Total"].astype(str).str.strip()
    numbers = raw.str.replace(",", "", regex=False) if english else raw.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    out = pd.DataFrame({"period": frame[period].astype(int), dimension: codelists.mapped(frame[measure].astype(str), codes, measure)})
    out["value"] = pd.to_numeric(numbers.where(raw != "."), errors="coerce")
    out["hidden"] = (raw == ".").to_numpy()
    # Empty: the unit didn't exist that year; "..": not available (foral territories before they
    # joined, Spain before 2021). Neither is hidden: there's nothing to fill.
    out["empty"] = raw.isin(["", ".."]).to_numpy()
    out["sex"] = codelists.mapped(frame["Sexo"].astype(str), codelists.SEX, "Sexo") if "Sexo" in names else "total"
    group = next((name for name in ("Tramos de edad", "Nacionalidad") if name in names), None)
    out["group"] = codelists.mapped(frame[group].astype(str), GROUPS, group) if group else "total"

    if "Total Nacional" in names:
        ccaa, province, islands = (frame[name].astype(str) for name in ("Comunidades y Ciudades Autónomas", "Provincias", "Islas"))
        out["level"] = np.select([islands != "", province != "", ccaa != ""], ["island", "province", "autonomous_community"], "country")
        out["code"] = np.select([province != "", ccaa != ""], [province.map(PROVINCES), ccaa.map(CCAA)], "es")
        out = out[out["level"] != "island"]
        unknown = out["code"].isna()
        if unknown.any():
            raise ValueError(f"{path.name}: unknown places {sorted(set(province[out.index[unknown]]) | set(ccaa[out.index[unknown]]))}")
    else:
        section, district, municipality = (frame[name].astype(str) for name in GEOGRAPHY)
        out["level"] = np.select([section != "", district != ""], ["census_section", "census_district"], "municipality")
        out["code"] = ine.codes(pd.Series(np.select([section != "", district != ""], [section, district], municipality), index=frame.index))
    return out


def parents(codes: pd.Series, level: str, ccaa: pd.Series) -> list[pd.Series]:
    """The codes of the units above, nearest first, for falling back when one is missing."""
    chain = {
        "census_section": [("census_district", 7), ("municipality", 5), ("province", 2)],
        "census_district": [("municipality", 5), ("province", 2)],
        "municipality": [("province", 2)],
    }
    if level in chain:
        out = [(name, codes.str[:length]) for name, length in chain[level]]
        return [*out, ("autonomous_community", codes.str[:2].map(ccaa)), ("country", pd.Series("es", index=codes.index))]
    if level == "province":
        return [("autonomous_community", codes.map(ccaa)), ("country", pd.Series("es", index=codes.index))]
    return [("country", pd.Series("es", index=codes.index))]


def impute(frame: pd.DataFrame, dimension: str, breakdown: bool, shares: bool) -> pd.DataFrame:
    """Fills hidden cells from the top down (see the module's docstring)."""
    keys = ["period", "sex", "group", dimension]
    ccaa = ccaa_by_province()
    filled = {}
    for level in LEVELS:
        part = frame[frame["level"] == level].copy()
        hidden = part["hidden"].to_numpy()
        if level == "country" or not hidden.any():
            filled[level] = part
            continue
        # The value of the nearest unit above that has one.
        above = pd.Series(np.nan, index=part.index)
        above_total = pd.Series(np.nan, index=part.index)
        for name, codes in parents(part["code"], level, ccaa):
            if name not in filled:
                continue
            source = filled[name].set_index(["code", *keys])["value"]
            lookup = pd.MultiIndex.from_arrays([codes, *(part[key] for key in keys)])
            found = pd.Series(source.reindex(lookup).to_numpy(), index=part.index)
            missing = above.isna()
            above[missing] = found[missing]
            if breakdown:
                totals = pd.MultiIndex.from_arrays([codes, part["period"], pd.Series("total", index=part.index), pd.Series("total", index=part.index), part[dimension]])
                found_total = pd.Series(source.reindex(totals).to_numpy(), index=part.index)
                above_total[missing] = found_total[missing]
        values = above.copy()
        if breakdown:
            # The unit's own total for the same threshold, where INE gives it (or it was filled).
            totals = part[(part["sex"] == "total") & (part["group"] == "total")]
            own = totals.set_index(["code", "period", dimension])["value"]
            own_total = pd.Series(own.reindex(pd.MultiIndex.from_frame(part[["code", "period", dimension]])).to_numpy(), index=part.index)
            # Totals are filled first (from above); then cells scale them by the ratio above.
            is_total = (part["sex"] == "total") & (part["group"] == "total")
            own_total[is_total & hidden] = above[is_total & hidden]
            ratio = above / above_total.where(above_total > 0)
            scaled = own_total * ratio
            values = scaled.where(scaled.notna() & ~is_total, above)
        if shares:
            values = values.clip(upper=100)
        part.loc[hidden, "value"] = values[hidden]
        part.loc[hidden, "origin"] = "imputed"
        if dimension == "household_indicator":
            counts = hidden & (part[dimension] == "population").to_numpy()
            if counts.any():
                part.loc[counts, "value"] = share_counts(part, counts, filled, level, ccaa, dimension)
        filled[level] = part
    return pd.concat(filled.values(), ignore_index=True)


def share_counts(part: pd.DataFrame, rows: np.ndarray, filled: dict, level: str, ccaa: pd.Series, dimension: str) -> pd.Series:
    """
    Hidden populations: the nearest unit above's, less its published units', shared among its hidden
    ones by their mean published size (equally without one). NaN where the unit above has none.
    """
    name, codes = next((name, codes) for name, codes in parents(part["code"], level, ccaa) if name in filled)
    population = part[part[dimension] == "population"].assign(parent=codes)
    published = population[~population["hidden"]]
    above = filled[name][filled[name][dimension] == "population"].set_index(["code", "period"])["value"].rename_axis(["parent", "period"])
    residual = above.sub(published.groupby(["parent", "period"])["value"].sum(), fill_value=0).reindex(above.index)
    residual = residual.rename("residual").reset_index().assign(**{dimension: "population"})
    hidden = part[rows].assign(parent=codes[rows])
    size = published.groupby("code")["value"].mean()
    weights = pd.Series(size.reindex(hidden["code"]).to_numpy(), index=pd.MultiIndex.from_frame(hidden[["code", "period", "sex"]]))
    values = share_out(residual, hidden[["code", "parent", "period", dimension, "sex"]], weights, "parent", [dimension])
    known = pd.MultiIndex.from_frame(hidden[["parent", "period"]]).isin(above.dropna().index)
    return values.where(known)


def reversed_shares(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Units whose share above 140% of the median is below the one above 200%: their "above" shares, hidden."""
    if dimension != "income_threshold":
        return frame
    keys = ["level", "code", "period", "sex", "group"]
    above = frame[frame[dimension].isin(["above_140", "above_200"])].pivot_table(index=keys, columns=dimension, values="value", observed=True)
    wrong = above.index[above["above_140"] < above["above_200"]]
    if wrong.empty:
        return frame
    log.warning("%d units with reversed 'above' shares, taken as hidden: %s", len(wrong), wrong[:3].tolist())
    rows = pd.MultiIndex.from_frame(frame[keys]).isin(wrong) & frame[dimension].astype(str).str.startswith("above").to_numpy()
    frame.loc[rows, "value"] = np.nan
    frame.loc[rows, "hidden"] = True
    return frame


#: The national tables (Spain, autonomous communities, provinces), one per kind.
NATIONAL_TABLES = {tables[-1] for tables in TABLES.values()}
#: Each kind also has a table with every municipality of Spain: the 52 provincial ones together, row
#: by row, so it's left out.
ALL_MUNICIPALITIES = {30824, 30825, 30826, 30827, 30828, 30829, 30830, 30831, 37677, 30832}
TABLES = {kind: [table for table in tables if table not in ALL_MUNICIPALITIES] for kind, tables in TABLES.items()}


def province_of(path: Path) -> str:
    """The province a provincial table is about: its first municipality's code."""
    with path.open(encoding="utf-8-sig") as file:
        file.readline()
        return file.readline()[:2]


def nearest_year(frame: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Cells still empty take the same unit's value in the nearest year with one (the later on a tie)."""
    left = frame["value"].isna()
    if not left.any():
        return frame
    keys = ["level", "code", "sex", "group", dimension]
    known = frame[~frame["value"].isna()][[*keys, "period", "value"]]
    candidates = frame[left][[*keys, "period"]].reset_index().merge(known, on=keys, suffixes=("", "_known"))
    candidates["distance"] = (candidates["period"] - candidates["period_known"]).abs() * 2 - (candidates["period_known"] > candidates["period"])
    best = candidates.sort_values("distance").drop_duplicates("index").set_index("index")["value"]
    frame.loc[best.index, "value"] = best
    frame.loc[best.index, "origin"] = "imputed"
    return frame


def build(name: str, refresh: bool) -> None:
    spec = DATASETS[name]
    dimension = spec["dimension"]
    raw = raw_dir(PIPELINE, date.today().isoformat())
    jobs = [(kind, table) for kind in spec["kinds"] for table in TABLES[kind]]
    for kind in spec["kinds"]:
        (raw / kind).mkdir(exist_ok=True)
    with ThreadPoolExecutor(4) as pool:
        paths = list(pool.map(lambda job: ine.fetch_table(job[1], raw / job[0] / f"{job[1]}.csv", refresh), jobs))
    # Spain, communities and provinces first (the national tables); then each province's
    # municipalities, districts and sections on top of them, one province at a time.
    national = [path for path in paths if int(path.stem) in NATIONAL_TABLES]
    by_province: dict[str, list[Path]] = {}
    for path in paths:
        if path not in national:
            by_province.setdefault(province_of(path), []).append(path)
    breakdown, shares = spec.get("breakdown", False), name in ("income_sources", "income_relative", "income_fixed")
    stats = {"hidden": {}}

    def prepare(group: list[Path]) -> pd.DataFrame:
        frame = pd.concat([read(path, dimension, spec["codes"]) for path in group], ignore_index=True)
        # The breakdown tables repeat their totals (by sex): keep each once. Units that didn't exist are empty.
        frame = frame[~frame["empty"]].drop_duplicates(["level", "code", "period", "sex", "group", dimension]).drop(columns="empty")
        frame = reversed_shares(frame, dimension)
        for level, count in frame[frame["hidden"]].groupby("level").size().items():
            stats["hidden"][level] = stats["hidden"].get(level, 0) + int(count)
        return frame.assign(origin="published")

    columns = ["code", "period", *(["sex", "group"] if breakdown else []), dimension, "value", "origin"]
    chunks: dict[str, list[pa.Table]] = {level: [] for level in LEVELS}
    stats.update(left_blank=0, imputed={}, periods=set())

    def keep(frame: pd.DataFrame) -> None:
        """Sets a part aside by level, as compact Arrow tables (strings as dictionaries), with its counts."""
        left = frame["value"].isna()
        if left.any():
            stats["left_blank"] += int(left.sum())
            log.warning("%s: %d cells with nothing to fill them from: %s", name, int(left.sum()), frame[left].head(3).to_dict("records"))
        frame = frame[~left]
        stats["periods"] |= set(frame["period"].unique().tolist())
        for level, count in frame[frame["origin"] == "imputed"].groupby("level").size().items():
            stats["imputed"][level] = stats["imputed"].get(level, 0) + int(count)
        for level, part in frame.groupby("level"):
            table = pa.Table.from_pandas(part[columns].rename(columns={"group": "income_group"}), preserve_index=False)
            chunks[level].append(pa.table({key: (column.dictionary_encode() if pa.types.is_string(column.type) else column) for key, column in zip(table.column_names, table.columns)}))

    upper = impute(prepare(national), dimension, breakdown, shares)
    upper["hidden"] = False
    keep(nearest_year(upper.copy(), dimension))
    for province, group in sorted(by_province.items()):
        local = impute(pd.concat([upper, prepare(group)], ignore_index=True), dimension, breakdown, shares)
        keep(nearest_year(local[local["level"].isin(["municipality", "census_district", "census_section"])].copy(), dimension))
        log.info("%s: province %s done", name, province)

    out = output_dir(PIPELINE) / name
    out.mkdir(parents=True, exist_ok=True)
    rows = {}
    for level in LEVELS:
        # Sorted and written straight from Arrow: tens of millions of rows don't go through pandas.
        table = pa.concat_tables(chunks[level], promote_options="permissive")
        table = pa.table({key: (column.cast(pa.string()) if pa.types.is_dictionary(column.type) else column) for key, column in zip(table.column_names, table.columns)})
        table = table.sort_by([(key, "ascending") for key in table.column_names if key not in ("value", "origin")])
        if level == "country":
            ids = pa.array([COUNTRY_ID] * table.num_rows)
        else:
            text = pa.large_string()
            ids = compute.binary_join_element_wise(pa.scalar(ID_PREFIX[level], text), table["code"].cast(text), pa.scalar("", text))
        table = table.add_column(0, "entity_id", ids)
        pq.write_table(table, out / f"{level}.parquet", compression="zstd")
        rows[level] = table.num_rows
        chunks[level] = []
    metadata = {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"operation": "INE Atlas de distribución de renta de los hogares (353)", "url": ine.CSV_URL, "tables": [table for kind in spec["kinds"] for table in TABLES[kind]]},
        "periods": sorted(int(period) for period in stats.pop("periods")),
        "rows_by_level": rows,
        "imputed_by_level": stats.pop("imputed"),
        **stats,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s; imputed %s", out, rows, metadata["imputed_by_level"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="INE's household income atlas (ADRH) by census section up to Spain.")
    parser.add_argument("datasets", nargs="*", help=f"datasets to build (default: all): {', '.join(DATASETS)}")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in args.datasets or DATASETS:
        build(name, args.refresh)
