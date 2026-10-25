"""
Provinces of Spain from IGN's INSPIRE administrative units, as GeoParquet keyed by INE code.

Steps: download the third-order units from IGN's WFS (raw GeoJSON, kept as is), parse and
validate them, and write one row per province with its catalogue id and its parent's.

    python pipelines/provinces/provinces.py [--refresh]
"""

import argparse
import logging
import re
from datetime import date
from pathlib import Path

import geopandas as gpd

from common import ign
from common.metadata import write_run_metadata
from common.paths import output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "provinces"
DATASET = "ign_au_provinces"

# IGN's national code: "34" (Spain), the INE code of the autonomous community, the INE code
# of the province, and zeros for the levels below.
NATIONAL_CODE = re.compile(r"^34(?P<ccaa>\d{2})(?P<province>\d{2})0{5}$")

# The level also holds "Territorios no asociados a ninguna provincia" (the plazas de soberanía),
# which isn't one of INE's 52 provinces.
EXCLUDED_CODES = {"54"}
EXPECTED_CODES = {f"{n:02d}" for n in range(1, 53)}


def province_id(ine_code: str) -> str:
    return f"es:ine:prov:{ine_code}"


def ccaa_id(ine_code: str) -> str:
    return f"es:ine:ccaa:{ine_code}"


def parse(raw: Path) -> gpd.GeoDataFrame:
    """One row per INE province; fails loudly on unexpected codes or counts."""
    rows = []
    for unit in ign.read_units(raw):
        match = NATIONAL_CODE.match(unit.national_code)
        if not match:
            raise ValueError(f"Unexpected IGN national code: {unit.national_code}")
        code = match["province"]
        if code in EXCLUDED_CODES:
            continue
        rows.append(
            {
                "id": province_id(code),
                "ine_code": code,
                "name": unit.name,
                "ccaa_code": match["ccaa"],
                "parent_id": ccaa_id(match["ccaa"]),
                "ign_code": unit.national_code,
                "geometry": unit.geometry,
            }
        )

    provinces = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").sort_values("id", ignore_index=True)
    codes = set(provinces["ine_code"])
    if codes != EXPECTED_CODES or len(provinces) != len(EXPECTED_CODES):
        raise ValueError(f"Expected INE provinces 01–52 once each; missing {sorted(EXPECTED_CODES - codes)}, extra {sorted(codes - EXPECTED_CODES)}")
    return provinces


def run(refresh: bool = False) -> Path:
    """Downloads (once a day unless `refresh`), parses and writes `provinces.parquet` plus its run metadata."""
    retrieved = date.today().isoformat()
    raw = raw_dir(PIPELINE, retrieved) / "provinces.geojson"
    ign.fetch(ign.PROVINCE, raw, refresh)

    provinces = parse(raw)
    out = output_dir(PIPELINE)
    parquet = out / "provinces.parquet"
    provinces.to_parquet(parquet, compression="zstd", write_covering_bbox=True)
    source = {"url": ign.SOURCE_URL, "params": ign.request_params(ign.PROVINCE)}
    write_run_metadata(out / "provinces.meta.json", DATASET, retrieved, source, raw, len(provinces))
    log.info("Wrote %s (%d provinces, %.1f MB)", parquet, len(provinces), parquet.stat().st_size / 1e6)
    return parquet


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Provinces of Spain as GeoParquet.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(refresh=args.refresh)
