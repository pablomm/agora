"""
Census sections and census districts of Spain from INE's yearly cartography, as GeoParquet keyed
by INE code. Districts aren't published as such: they're the union of their sections.

Steps: download one edition's shapefile (zip, kept as is), validate the codes, reproject to
EPSG:4326, write the sections, and dissolve them into districts.

    python pipelines/census_sections/census_sections.py [--year 2026] [--refresh]
"""

import argparse
import logging
from datetime import date
from pathlib import Path

import geopandas as gpd
import shapely

from common.download import download
from common.metadata import write_run_metadata
from common.paths import output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "census_sections"
SECTIONS_DATASET = "ine_census_sections"
DISTRICTS_DATASET = "ine_census_districts"

#: Latest edition when this was written: sections as of 1 January 2026, published March 2026.
LATEST_YEAR = 2026
URL = "https://www.ine.es/prodyser/cartografia/seccionado_{year}.zip"
# Inside the zip: one shapefile for the whole country, in ETRS89 / UTM 30N (Canarias included).
SHAPEFILE = "España_Seccionado{year}_ETRS89H30/SECC_CE_{year}0101.shp"


def section_id(code: str) -> str:
    return f"es:ine:sec:{code}"


def district_id(code: str) -> str:
    return f"es:ine:dist:{code}"


def municipality_id(code: str) -> str:
    return f"es:ine:mun:{code}"


def fetch(year: int, refresh: bool) -> Path:
    target = raw_dir(PIPELINE, date.today().isoformat()) / f"seccionado_{year}.zip"
    if target.exists() and not refresh:
        log.info("Using today's download %s", target)
    else:
        download(URL.format(year=year), target)
    return target


def read_sections(raw: Path, year: int) -> gpd.GeoDataFrame:
    """One row per section in EPSG:4326, with valid geometry; fails loudly on inconsistent codes."""
    frame = gpd.read_file(f"/vsizip/{raw}/{SHAPEFILE.format(year=year)}")
    # Each code is built from the ones above it: province (2) + municipality (3) + district (2) + section (3).
    checks = {
        "CUMUN = CPRO + CMUN": frame["CUMUN"] == frame["CPRO"] + frame["CMUN"],
        "CUDIS = CUMUN + CDIS": frame["CUDIS"] == frame["CUMUN"] + frame["CDIS"],
        "CUSEC = CUDIS + CSEC": frame["CUSEC"] == frame["CUDIS"] + frame["CSEC"],
        "CUSEC has 10 digits": frame["CUSEC"].str.fullmatch(r"\d{10}"),
    }
    for rule, ok in checks.items():
        if not ok.all():
            raise ValueError(f"{(~ok).sum()} sections break '{rule}', e.g. {frame.loc[~ok, 'CUSEC'].head(3).tolist()}")
    duplicated = frame["CUSEC"][frame["CUSEC"].duplicated()]
    if not duplicated.empty:
        raise ValueError(f"Duplicated section codes: {sorted(duplicated)[:10]}")

    invalid = ~frame.is_valid
    if invalid.any():
        log.info("Repairing %d invalid geometries", invalid.sum())
        frame.loc[invalid, "geometry"] = shapely.make_valid(frame.loc[invalid, "geometry"].values)
    frame = frame.to_crs("EPSG:4326")
    if not frame.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Non-polygonal section geometry after repair")

    sections = gpd.GeoDataFrame(
        {
            "id": frame["CUSEC"].map(section_id),
            "ine_code": frame["CUSEC"],
            "section_code": frame["CSEC"],
            "district_code": frame["CDIS"],
            "municipality_code": frame["CUMUN"],
            "province_code": frame["CPRO"],
            "ccaa_code": frame["CCA"],
            # As INE writes it (articles at the end: "Roda, La"); join by code, not by name.
            "municipality_name": frame["NMUN"],
            "parent_id": frame["CUDIS"].map(district_id),
            "year": year,
        },
        geometry=frame.geometry.values,
        crs="EPSG:4326",
    )
    return sections.sort_values("id", ignore_index=True)


def dissolve_districts(sections: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per district: the union of its sections."""
    sections = sections.assign(district=sections["municipality_code"] + sections["district_code"])
    districts = sections.dissolve(
        by="district",
        aggfunc={
            "district_code": "first",
            "municipality_code": "first",
            "province_code": "first",
            "ccaa_code": "first",
            "municipality_name": "first",
            "year": "first",
        },
    ).reset_index(names="ine_code")
    districts.insert(0, "id", districts["ine_code"].map(district_id))
    districts["parent_id"] = districts["municipality_code"].map(municipality_id)
    columns = ["id", "ine_code", "district_code", "municipality_code", "province_code", "ccaa_code", "municipality_name", "parent_id", "year", "geometry"]
    return districts[columns].sort_values("id", ignore_index=True)


def run(year: int = LATEST_YEAR, refresh: bool = False) -> None:
    raw = fetch(year, refresh)
    sections = read_sections(raw, year)
    districts = dissolve_districts(sections)

    out = output_dir(PIPELINE)
    source = {"url": URL.format(year=year), "file": SHAPEFILE.format(year=year), "edition": year}
    for name, dataset, frame in (
        (f"census_sections_{year}", SECTIONS_DATASET, sections),
        (f"census_districts_{year}", DISTRICTS_DATASET, districts),
    ):
        parquet = out / f"{name}.parquet"
        frame.to_parquet(parquet, compression="zstd", write_covering_bbox=True)
        write_run_metadata(out / f"{name}.meta.json", dataset, date.today().isoformat(), source, raw, len(frame))
        log.info("Wrote %s (%d rows, %.1f MB)", parquet, len(frame), parquet.stat().st_size / 1e6)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Census sections and districts of Spain as GeoParquet.")
    parser.add_argument("--year", type=int, default=LATEST_YEAR, help=f"edition (sections as of 1 January; default {LATEST_YEAR})")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.year, args.refresh)
