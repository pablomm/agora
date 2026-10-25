"""
Postal code areas of Spain, as GeoParquet keyed by postal code.

The source is a GeoParquet from an earlier project (January 2024), not a download: it lives in
data/raw/postal_codes/{snapshot}/ and is the only copy, so keep a backup. See the README.

Steps: read the snapshot, validate codes and geometry, and write one row per postal code with its
catalogue id and its province's.

    python pipelines/postal_codes/postal_codes.py
"""

import argparse
import logging
from datetime import date

import geopandas as gpd
import shapely

from common.metadata import write_run_metadata
from common.paths import output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "postal_codes"
DATASET = "postal_code_areas_2024"

#: Folder under data/raw/postal_codes/ holding the snapshot (the files' date).
SNAPSHOT = "2024-01-08"
SOURCE_FILE = "postal-codes.geo.parquet"
PROVINCE_CODES = {f"{n:02d}" for n in range(1, 53)}


def postal_code_id(code: str) -> str:
    return f"es:correos:cp:{code}"


def province_id(ine_code: str) -> str:
    return f"es:ine:prov:{ine_code}"


def parse(source: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """One row per postal code, with valid polygonal geometry; fails loudly on anything unexpected."""
    codes = source["postal_code"]
    if not codes.str.fullmatch(r"\d{5}").all():
        raise ValueError(f"Postal codes that aren't five digits: {codes[~codes.str.fullmatch(r'\d{5}')].head(5).tolist()}")
    duplicated = codes[codes.duplicated()]
    if not duplicated.empty:
        raise ValueError(f"Duplicated postal codes: {sorted(duplicated)[:10]}")
    # A Spanish postal code starts with its province's INE code.
    provinces = codes.str[:2]
    if not provinces.isin(PROVINCE_CODES).all():
        raise ValueError(f"Postal codes with no INE province prefix: {codes[~provinces.isin(PROVINCE_CODES)].head(5).tolist()}")
    if not (provinces.astype(int) == source["province_id"]).all():
        raise ValueError("The source's province_id doesn't match the postal code prefix")

    geometry = source.geometry
    invalid = ~geometry.is_valid
    if invalid.any():
        log.info("Repairing %d invalid geometries", invalid.sum())
        geometry = geometry.where(~invalid, shapely.make_valid(geometry.values))
    if not geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Non-polygonal postal code geometry after repair")

    # Dropped: `name` ("CP 01001", nothing more than the code), `postal_id` (the code as a number),
    # `area` (derivable) and `lng`/`lat` (a centroid, outside its own polygon in 4.5 % of codes).
    return gpd.GeoDataFrame(
        {
            "id": codes.map(postal_code_id),
            "postal_code": codes,
            "province_code": provinces,
            "parent_id": provinces.map(province_id),
        },
        geometry=geometry.values,
        crs="EPSG:4326",
    ).sort_values("id", ignore_index=True)


def run() -> None:
    raw = raw_dir(PIPELINE, SNAPSHOT) / SOURCE_FILE
    if not raw.exists():
        raise SystemExit(f"Missing {raw}: this source isn't downloaded, it has to be put there (see the README)")
    source = gpd.read_parquet(raw).to_crs("EPSG:4326")
    postal_codes = parse(source)

    out = output_dir(PIPELINE)
    parquet = out / "postal_codes.parquet"
    postal_codes.to_parquet(parquet, compression="zstd", write_covering_bbox=True)
    source_info = {"kind": "file", "origin": "earlier project", "snapshot": SNAPSHOT, "file": SOURCE_FILE}
    write_run_metadata(out / "postal_codes.meta.json", DATASET, date.today().isoformat(), source_info, raw, len(postal_codes))
    log.info("Wrote %s (%d postal codes, %.1f MB)", parquet, len(postal_codes), parquet.stat().st_size / 1e6)


if __name__ == "__main__":
    argparse.ArgumentParser(description="Postal code areas of Spain as GeoParquet.").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
