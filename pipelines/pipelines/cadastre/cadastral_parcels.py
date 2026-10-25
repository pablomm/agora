"""
Urban cadastral parcels of Spain from Catastro's INSPIRE cadastral parcels, as GeoParquet
partitioned by province, each linked to its urban block and INE municipality.

Reads the parcels copied by import_inspire.py (one GML per Catastro municipality), keeps the urban
ones (rural references look like 12068A00200237), reprojects them to EPSG:4326, links each to the
urban block it lies in, and writes one file per Catastro province, so the 11-odd million parcels
never sit in memory at once. Run cadastral_zones.py first.

    python pipelines/cadastre/cadastral_parcels.py [--snapshot 2023-04] [--workers N]
"""

import argparse
import json
import logging
import os
import re
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime, timezone

import geopandas as gpd
import pandas as pd

from common.catastro import RURAL_REFERENCE, members_by_province, merge_pieces, municipality_codes, parcels_schema, polygonal, read_gml
from common.download import sha256
from common.paths import DATA_DIR, output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre"
DATASET = "catastro_urban_parcels"
SNAPSHOT = "2023-04"
MEMBER = re.compile(r"^A\.ES\.SDGC\.CP\.(?P<code>\d{5})\.cadastralparcel\.gml$")


def parcel_id(catastro_municipality: str, reference: str) -> str:
    # The municipality makes ids unique even for the odd malformed reference in the source.
    return f"es:catastro:parcel:{catastro_municipality}:{reference}"


def read_member(args: tuple[str, str]) -> gpd.GeoDataFrame:
    """One municipality's urban parcels in EPSG:4326 (runs in a worker process)."""
    raw, member = args
    frame = read_gml(raw, member, ["localId", "label", "areaValue", "beginLifespanVersion"])
    frame = frame[~frame["localId"].str.match(RURAL_REFERENCE.pattern)]
    frame["catastro_municipality_code"] = MEMBER.match(member)["code"]
    return frame


def urban_blocks(snapshot: str, catastro_municipalities: list[str]) -> gpd.GeoDataFrame:
    path = DATA_DIR / f"processed/cadastre/cadastral_zones_{snapshot}.parquet"
    zones = gpd.read_parquet(
        path,
        columns=["id", "zone_type", "catastro_municipality_code", "geometry"],
        filters=[("catastro_municipality_code", "in", catastro_municipalities), ("zone_type", "==", "urban_block")],
    )
    return zones.rename(columns={"id": "zone_id", "catastro_municipality_code": "zone_municipality"})


def link_blocks(parcels: gpd.GeoDataFrame, blocks: gpd.GeoDataFrame) -> pd.Series:
    """
    The urban block each parcel lies in (a point inside the parcel, within a block of the same
    municipality), or none. By position: parcel and block references don't always agree on the
    sheet's last letter, and some parcels have a reference format no block has.
    """
    points = gpd.GeoDataFrame({"code": parcels["catastro_municipality_code"]}, geometry=parcels.geometry.representative_point(), crs="EPSG:4326")
    joined = points.sjoin(blocks, how="left", predicate="within")
    joined = joined[joined["zone_municipality"].isna() | (joined["zone_municipality"] == joined["code"])]
    joined = joined[~joined.index.duplicated()]
    return joined["zone_id"].reindex(parcels.index)


def build_province(frames: list[gpd.GeoDataFrame], municipalities: pd.Series, blocks: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    frame = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    # Pieces' labels can differ in padding only ("008" and "08"): labels aren't kept, so no check on them.
    frame = merge_pieces(frame, frame["catastro_municipality_code"] + ":" + frame["localId"], [], summed=["areaValue"])
    geometry = polygonal(frame.geometry)
    keep = ~geometry.is_empty
    frame, geometry = frame[keep.values], geometry[keep.values]

    codes = frame["catastro_municipality_code"]
    references = frame["localId"]
    parcels = gpd.GeoDataFrame(
        {
            "id": [parcel_id(code, reference) for code, reference in zip(codes, references)],
            "reference": references,
            "area_m2": pd.to_numeric(frame["areaValue"], errors="coerce").astype("Int64"),
            "valid_from": pd.to_datetime(frame["beginLifespanVersion"], errors="coerce").dt.date,
            "catastro_municipality_code": codes,
            "municipality_code": codes.map(municipalities),
        },
        geometry=geometry.values,
        crs="EPSG:4326",
    )
    parcels["zone_id"] = link_blocks(parcels, blocks).values
    if parcels["municipality_code"].isna().any():
        missing = sorted(parcels.loc[parcels["municipality_code"].isna(), "catastro_municipality_code"].unique())
        raise ValueError(f"Catastro municipalities with no INE match: {missing[:10]}")
    parcels["parent_id"] = parcels["zone_id"].fillna("es:ine:mun:" + parcels["municipality_code"])
    # The foral cadastres' parcels share this dataset (foral_parcels.py): say whose each one is.
    parcels["source"] = "catastro"
    return parcels_schema(parcels.sort_values("id", ignore_index=True))


def run(snapshot: str, workers: int) -> None:
    raw = raw_dir(PIPELINE, snapshot) / "cadastralparcel.zip"
    if not raw.exists():
        raise SystemExit(f"Missing {raw}: run import_inspire.py parcels first (see the README)")
    municipalities = municipality_codes(snapshot)
    with zipfile.ZipFile(raw) as archive:
        provinces = members_by_province(archive.namelist(), MEMBER)

    out = output_dir(PIPELINE) / f"cadastral_parcels_{snapshot}"
    out.mkdir(exist_ok=True)
    counts, with_zone = {}, 0
    with ProcessPoolExecutor(workers) as pool:
        for province, members in provinces.items():
            frames = list(pool.map(read_member, [(str(raw), member) for member in members], chunksize=4))
            blocks = urban_blocks(snapshot, [MEMBER.match(member)["code"] for member in members])
            parcels = build_province(frames, municipalities, blocks)
            parcels.to_parquet(out / f"{province}.parquet", compression="zstd", write_covering_bbox=True, row_group_size=100_000)
            counts[province] = len(parcels)
            with_zone += parcels["zone_id"].notna().sum()
            log.info("Province %s: %d urban parcels", province, len(parcels))

    total = sum(counts.values())
    metadata = {
        "dataset": DATASET,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieved_at": date.today().isoformat(),
        "source": {"kind": "file", "origin": "Catastro INSPIRE cadastral parcels (ATOM), cadastralparcel", "snapshot": snapshot},
        "raw": {"path": str(raw), "bytes": raw.stat().st_size, "sha256": sha256(raw)},
        "rows": total,
        "rows_by_catastro_province": counts,
        "rows_with_zone": int(with_zone),
    }
    (out.parent / f"cadastral_parcels_{snapshot}.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s (%d urban parcels, %.0f %% linked to their block)", out, total, 100 * with_zone / total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Urban cadastral parcels of Spain as GeoParquet.")
    parser.add_argument("--snapshot", default=SNAPSHOT, help=f"raw folder written by import_inspire.py (default {SNAPSHOT})")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="parallel readers (default: all cores)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.snapshot, args.workers)
