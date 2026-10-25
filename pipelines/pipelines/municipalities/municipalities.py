"""
Municipalities of Spain from IGN's INSPIRE administrative units, as GeoParquet keyed by INE code.

Steps: download the fourth-order units from IGN's WFS (raw GeoJSON, kept as is), sort them into
municipalities and shared territories (condominiums), validate them, and write one file for each.

    python pipelines/municipalities/municipalities.py [--refresh]
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

PIPELINE = "municipalities"
DATASET = "ign_au_municipalities"
SHARED_DATASET = "ign_au_shared_territories"

# IGN's national code: "34" (Spain), the INE codes of the autonomous community and the province,
# then the unit's own five digits. For a municipality those are its INE code (province + three
# digits); shared territories have "53" where the province would repeat.
NATIONAL_CODE = re.compile(r"^34(?P<ccaa>\d{2})(?P<province>\d{2})(?P<unit>\d{5})$")
SHARED_TERRITORY_MARK = "53"

# Province 54 holds the "Territorios no asociados a ninguna provincia": the plazas de soberanía,
# the Isla de los Faisanes and Gibraltar. None is an INE municipality.
EXCLUDED_PROVINCES = {"54"}
PROVINCE_CODES = {f"{n:02d}" for n in range(1, 53)}

# INE's count when this pipeline was written (2026-10-25). A different count isn't necessarily
# wrong (municipalities are created and merged), but it needs a look before the output is used.
EXPECTED_MUNICIPALITIES = 8132


def municipality_id(ine_code: str) -> str:
    return f"es:ine:mun:{ine_code}"


def province_id(ine_code: str) -> str:
    return f"es:ine:prov:{ine_code}"


def shared_territory_id(ign_code: str) -> str:
    # No INE code: they aren't municipalities. IGN's national code is the only stable key.
    return f"es:ign:au:{ign_code}"


def parse(raw: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Municipalities and shared territories; fails loudly on unexpected codes or counts."""
    municipalities, shared = [], []
    for unit in ign.read_units(raw):
        match = NATIONAL_CODE.match(unit.national_code)
        if not match:
            raise ValueError(f"Unexpected IGN national code: {unit.national_code}")
        province, code = match["province"], match["unit"]
        if province in EXCLUDED_PROVINCES:
            continue
        if province not in PROVINCE_CODES:
            raise ValueError(f"Unexpected province {province} in {unit.national_code}")
        row = {
            "name": unit.name,
            "province_code": province,
            "ccaa_code": match["ccaa"],
            "parent_id": province_id(province),
            "ign_code": unit.national_code,
            "geometry": unit.geometry,
        }
        if code[:2] == SHARED_TERRITORY_MARK:
            shared.append({"id": shared_territory_id(unit.national_code), **row})
        elif code[:2] == province:
            municipalities.append({"id": municipality_id(code), "ine_code": code, **row})
        else:
            raise ValueError(f"Municipality code {code} doesn't start with its province {province} ({unit.national_code})")

    municipalities = gpd.GeoDataFrame(municipalities, geometry="geometry", crs="EPSG:4326").sort_values("id", ignore_index=True)
    shared = gpd.GeoDataFrame(shared, geometry="geometry", crs="EPSG:4326").sort_values("id", ignore_index=True)

    duplicated = municipalities["ine_code"][municipalities["ine_code"].duplicated()]
    if not duplicated.empty:
        raise ValueError(f"Duplicated INE codes: {sorted(duplicated)}")
    missing = PROVINCE_CODES - set(municipalities["province_code"])
    if missing:
        raise ValueError(f"Provinces without municipalities: {sorted(missing)}")
    if len(municipalities) != EXPECTED_MUNICIPALITIES:
        raise ValueError(
            f"Expected {EXPECTED_MUNICIPALITIES} municipalities, got {len(municipalities)}: check INE's current list "
            "and update EXPECTED_MUNICIPALITIES if the change is real"
        )
    return municipalities, shared


def run(refresh: bool = False) -> tuple[Path, Path]:
    """Downloads (once a day unless `refresh`), parses and writes both files plus their run metadata."""
    retrieved = date.today().isoformat()
    raw = raw_dir(PIPELINE, retrieved) / "municipalities.geojson"
    ign.fetch(ign.MUNICIPALITY, raw, refresh)

    municipalities, shared = parse(raw)
    out = output_dir(PIPELINE)
    source = {"url": ign.SOURCE_URL, "params": ign.request_params(ign.MUNICIPALITY)}
    paths = []
    for name, dataset, frame in (
        ("municipalities", DATASET, municipalities),
        ("shared_territories", SHARED_DATASET, shared),
    ):
        parquet = out / f"{name}.parquet"
        frame.to_parquet(parquet, compression="zstd", write_covering_bbox=True)
        write_run_metadata(out / f"{name}.meta.json", dataset, retrieved, source, raw, len(frame))
        log.info("Wrote %s (%d rows, %.1f MB)", parquet, len(frame), parquet.stat().st_size / 1e6)
        paths.append(parquet)
    return paths[0], paths[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Municipalities of Spain as GeoParquet.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(refresh=args.refresh)
