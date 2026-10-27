"""
Tourist dwellings (INE, experimental statistic "Medición del número de viviendas turísticas en España
y su capacidad"): dwellings listed on the main short-let platforms, their beds, and their share of all
dwellings, from census sections to Spain, twice a year since August 2020.

Every level is kept as INE publishes it: sections and districts from one Excel file per period,
municipalities from tables 39363 and 39366, provinces, communities and Spain from 39364 and 39365.
Counts are also checked: each level must add up to the one above.

    python pipelines/housing/tourist_dwellings.py [--refresh]
"""

import argparse
import json
import logging
import re
from datetime import date, datetime, timezone

import pandas as pd
import requests

from common import ine
from common.download import download, sha256
from common.paths import output_dir, raw_dir
from common.rollup import ccaa_by_province, entity_ids, parent_codes, write_levels

log = logging.getLogger(__name__)

PIPELINE = "housing"
DATASET = "tourist_dwellings"
BASE_URL = "https://www.ine.es/experimental/viv_turistica/"
#: The page listing the files by district and section, one per period.
DOWNLOADS_PAGE = BASE_URL + "exp_viv_turistica_descarga.htm"
FILE_PATTERN = re.compile(r"exp_viv_turistica_tabla5_([A-Z]{3})(\d{4})\.xlsx")
MONTHS = {"FEB": 2, "MAY": 5, "AGO": 8, "NOV": 11}
#: Dwellings and beds: municipalities (39363), and Spain, communities and provinces (39364).
COUNT_TABLES = {"municipality": 39363, "regions": 39364}
#: Share of all dwellings: municipalities (39366), and Spain, communities and provinces (39365).
SHARE_TABLES = {"municipality": 39366, "regions": 39365}
MEASURES = {"Viviendas turísticas": "dwellings", "Plazas": "beds"}
#: The Excel files' columns, in lower case (their case changes from file to file); the unit's code is the first.
FILE_COLUMNS = {"vivienda turistica": "dwellings", "plazas": "beds", "porcentaje vivienda turistica": "share"}


def section_files(raw, refresh: bool) -> dict[int, object]:
    """Each period's Excel file (period as YYYYMM), downloaded once a day."""
    page = requests.get(DOWNLOADS_PAGE, timeout=(30, 120))
    page.raise_for_status()
    names = sorted(set(FILE_PATTERN.findall(page.text)))
    if not names:
        raise ValueError(f"No files by section listed in {DOWNLOADS_PAGE}")
    files = {}
    for month, year in names:
        if month not in MONTHS:
            raise ValueError(f"Unknown month {month} in {DOWNLOADS_PAGE}")
        target = raw / f"tabla5_{month}{year}.xlsx"
        if refresh or not target.exists():
            download(BASE_URL + f"exp_viv_turistica_tabla5_{month}{year}.xlsx", target)
        files[int(year) * 100 + MONTHS[month]] = target
    return dict(sorted(files.items()))


def read_file(path, period: int) -> dict[str, pd.DataFrame]:
    """Districts and sections of one file: code, period, measure, value."""
    out = {}
    # Sheets: notes, districts, sections (named differently over the years).
    for sheet, level, length in ((1, "census_district", 7), (2, "census_section", 10)):
        frame = pd.read_excel(path, sheet_name=sheet, dtype=str, engine="calamine")
        frame.columns = frame.columns.str.lower()
        frame = frame.rename(columns={frame.columns[0]: "code", **FILE_COLUMNS})
        if not frame["code"].str.fullmatch(rf"\d{{{length}}}").all():
            raise ValueError(f"{path.name}: {level} codes that aren't {length} digits")
        if set(frame["periodo"]) != {f"{period // 100}M{period % 100:02d}"}:
            raise ValueError(f"{path.name}: periods {sorted(set(frame['periodo']))}, expected {period}")
        if frame["code"].duplicated().any():
            raise ValueError(f"{path.name}: repeated {level} codes")
        long = frame.melt(id_vars="code", value_vars=list(FILE_COLUMNS.values()), var_name="measure", value_name="value")
        long["value"] = pd.to_numeric(long["value"], errors="raise")
        # INE hides the share where the census counted few dwellings (statistical secrecy); counts are always there.
        if long.loc[long["measure"] != "share", "value"].isna().any():
            raise ValueError(f"{path.name}: {level} without dwellings or beds")
        out[level] = long[long["value"].notna()].assign(period=period)
    return out


def read_published(raw, refresh: bool) -> dict[str, pd.DataFrame]:
    """Municipalities, provinces, communities and Spain from INE's tables: code, level, period, measure, value."""
    frames = []
    for scope, table in [*COUNT_TABLES.items(), *SHARE_TABLES.items()]:
        data = ine.read_table(ine.fetch_table(table, raw / f"{table}.csv", refresh))
        is_share = table in SHARE_TABLES.values()
        if not is_share:
            data = data[data["Viviendas y plazas"] != "Plazas por vivienda turística"]
        frame = pd.DataFrame(
            {
                "period": data["Periodo"].str.replace("M", "", regex=False).astype(int),
                "measure": "share" if is_share else data["Viviendas y plazas"].map(MEASURES),
                "value": ine.values(data["Total"]),
            }
        )
        if scope == "municipality":
            # Municipal tables repeat Spain, communities and provinces: only their municipalities are taken.
            frame["code"], frame["level"] = ine.codes(data["Municipios"]), "municipality"
            frame = frame[frame["code"] != ""]
        else:
            levels = [("province", data["Provincias"]), ("autonomous_community", data["Comunidades y Ciudades Autónomas"])]
            frame["code"], frame["level"] = "es", "country"
            for level, column in reversed(levels):
                codes = ine.codes(column)
                frame.loc[codes != "", "code"], frame.loc[codes != "", "level"] = codes[codes != ""], level
        frames.append(frame)
    published = pd.concat(frames, ignore_index=True)
    published = published.drop_duplicates(["level", "code", "period", "measure"])
    # Municipalities that didn't exist in a period have no values.
    published = published[published["value"].notna()]
    return {level: frame.drop(columns="level") for level, frame in published.groupby("level")}


def check_counts(child: pd.DataFrame, parent: pd.DataFrame, level: str, child_level: str, ccaa: pd.Series) -> dict:
    """Dwellings and beds of `child` summed into `level`, against the values published there."""
    counts = child[child["measure"] != "share"]
    summed = counts.assign(code=parent_codes(counts["code"], level, ccaa)).groupby(["code", "period", "measure"], as_index=False)["value"].sum()
    merged = parent.merge(summed, on=["code", "period", "measure"], suffixes=("_published", "_summed"))
    difference = (merged["value_published"] - merged["value_summed"]).abs()
    result = {
        "level": level,
        "from": child_level,
        "compared": int(len(merged)),
        "mismatches": int((difference > 0).sum()),
        "max_difference": float(difference.max()) if len(merged) else 0.0,
    }
    log.info("Check %s against %s: %s", child_level, level, result)
    return result


def run(refresh: bool) -> None:
    raw = raw_dir(PIPELINE, date.today().isoformat())
    files = section_files(raw, refresh)
    small = {"census_district": [], "census_section": []}
    for period, path in files.items():
        for level, frame in read_file(path, period).items():
            small[level].append(frame)
    levels = {level: pd.concat(frames, ignore_index=True) for level, frames in small.items()}
    levels.update(read_published(raw, refresh))
    periods = sorted(files)
    for level, frame in levels.items():
        if sorted(frame["period"].unique()) != periods:
            raise ValueError(f"{level}: periods {sorted(frame['period'].unique())}, the files have {periods}")

    ccaa = ccaa_by_province()
    checks = [
        check_counts(levels["census_section"], levels["census_district"], "census_district", "census_section", ccaa),
        check_counts(levels["census_district"], levels["municipality"], "municipality", "census_district", ccaa),
        check_counts(levels["municipality"], levels["province"], "province", "municipality", ccaa),
        check_counts(levels["province"], levels["autonomous_community"], "autonomous_community", "province", ccaa),
        check_counts(levels["autonomous_community"], levels["country"], "country", "autonomous_community", ccaa),
    ]
    if any(check["mismatches"] for check in checks):
        raise ValueError(f"Counts that don't add up: {checks}")

    frames = {}
    for level in ["census_section", "census_district", "municipality", "province", "autonomous_community", "country"]:
        frame = levels[level][["code", "period", "measure", "value"]].rename(columns={"measure": "tourist_measure"})
        frame.insert(0, "entity_id", entity_ids(frame["code"], level))
        frame["origin"] = "published"
        frames[level] = frame.sort_values(["entity_id", "period", "tourist_measure"], ignore_index=True)

    out = output_dir(PIPELINE) / DATASET
    rows = write_levels(frames, out)
    metadata = {
        "dataset": DATASET,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"files": DOWNLOADS_PAGE, "tables": {"counts": COUNT_TABLES, "shares": SHARE_TABLES}, "url": ine.CSV_URL},
        "raw": {path.name: sha256(path) for path in files.values()},
        "periods": periods,
        "rows_by_level": rows,
        "checks": checks,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s", out, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tourist dwellings, beds and share of dwellings, census sections to Spain.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.refresh)
