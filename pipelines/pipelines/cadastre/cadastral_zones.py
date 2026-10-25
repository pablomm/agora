"""
Cadastral zones (masas) of Spain: Catastro's urban blocks (manzanas) and rural polygons
(polígonos), as GeoParquet, each linked to the INE municipality it lies in.

Reads the zoning copied by import_inspire.py (one GML per Catastro municipality, each in its own
UTM zone), reprojects everything to EPSG:4326, and joins each zone to an IGN municipality by
position: Catastro numbers municipalities its own way, not with INE codes.

    python pipelines/cadastre/cadastral_zones.py [--snapshot 2023-04] [--workers N]
"""

import argparse
import logging
import os
import re
import zipfile
from concurrent.futures import ProcessPoolExecutor
from datetime import date

import geopandas as gpd
import pandas as pd

from common.catastro import polygonal, read_gml
from common.metadata import write_run_metadata
from common.paths import DATA_DIR, output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre"
DATASET = "catastro_cadastral_zones"
SNAPSHOT = "2023-04"

# A.ES.SDGC.CP.{Catastro municipality code}.cadastralzoning.gml
MEMBER = re.compile(r"^A\.ES\.SDGC\.CP\.(?P<code>\d{5})\.cadastralzoning\.gml$")
ZONE_TYPES = {"MANZANA": "urban_block", "POLIGONO": "rural_polygon"}


def zone_id(catastro_municipality: str, reference: str) -> str:
    # Urban references are only unique within their municipality: the id carries both.
    return f"es:catastro:zone:{catastro_municipality}:{reference}"


def municipality_id(ine_code: str) -> str:
    return f"es:ine:mun:{ine_code}"


def read_member(args: tuple[str, str]) -> gpd.GeoDataFrame:
    """One municipality's zones in EPSG:4326 (runs in a worker process)."""
    raw, member = args
    frame = read_gml(raw, member, ["localId", "label", "LocalisedCharacterString", "beginLifespanVersion"])
    frame["catastro_municipality_code"] = MEMBER.match(member)["code"]
    return frame


def read_zones(raw, workers: int) -> gpd.GeoDataFrame:
    with zipfile.ZipFile(raw) as archive:
        members = sorted(name for name in archive.namelist() if MEMBER.match(name))
    log.info("Reading %d municipalities with %d workers", len(members), workers)
    with ProcessPoolExecutor(workers) as pool:
        frames = list(pool.map(read_member, [(str(raw), member) for member in members], chunksize=20))
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def merge_split_zones(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Some zones come as several features with the same reference in the same municipality (one per
    piece): one row each, with the pieces' union as geometry.
    """
    key = frame["catastro_municipality_code"] + ":" + frame["localId"]
    split = key.duplicated(keep=False)
    if not split.any():
        return frame
    pieces = frame[split].assign(key=key[split])
    for column, values in pieces.groupby("key")[["label", "LocalisedCharacterString"]].nunique().items():
        if (values > 1).any():
            raise ValueError(f"Pieces of the same zone disagree on {column}")
    merged = pieces.dissolve(by="key", aggfunc="first").reset_index(drop=True)
    log.info("Merged %d features into %d zones split in pieces", split.sum(), len(merged))
    return gpd.GeoDataFrame(pd.concat([frame[~split], merged], ignore_index=True), crs=frame.crs)


def parse(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Validated zones, one row each; fails loudly on unexpected types."""
    kinds = frame["LocalisedCharacterString"].str.strip()
    unknown = set(kinds) - set(ZONE_TYPES)
    if unknown:
        raise ValueError(f"Unexpected zone types: {sorted(unknown)}")
    frame = merge_split_zones(frame)
    kinds = frame["LocalisedCharacterString"].str.strip()

    log.info("Repairing %d invalid geometries", (~frame.geometry.is_valid).sum())
    geometry = polygonal(frame.geometry)
    empty = geometry.is_empty
    if empty.any():
        log.info("Dropping %d zones left without area", empty.sum())

    zones = gpd.GeoDataFrame(
        {
            "id": [zone_id(code, reference) for code, reference in zip(frame["catastro_municipality_code"], frame["localId"])],
            "reference": frame["localId"],
            "zone_type": kinds.map(ZONE_TYPES),
            "label": frame["label"],
            "catastro_municipality_code": frame["catastro_municipality_code"],
            "valid_from": pd.to_datetime(frame["beginLifespanVersion"]).dt.date,
        },
        geometry=geometry.values,
        crs="EPSG:4326",
    )
    zones = zones[~empty.values].reset_index(drop=True)
    duplicated = zones["id"][zones["id"].duplicated()]
    if not duplicated.empty:
        raise ValueError(f"Duplicated zone ids: {sorted(duplicated)[:5]}")
    return zones


def link_municipalities(zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The IGN municipality each zone lies in, by a point inside it (nearest one off the coastline)."""
    municipalities = gpd.read_parquet(DATA_DIR / "processed/municipalities/municipalities.parquet", columns=["ine_code", "geometry"])
    points = gpd.GeoDataFrame(geometry=zones.geometry.representative_point(), crs="EPSG:4326")
    joined = points.sjoin(municipalities, how="left", predicate="within")
    joined = joined[~joined.index.duplicated()]
    outside = joined["ine_code"].isna()
    if outside.any():
        log.info("%d zones outside IGN's municipalities: using the nearest one", outside.sum())
        nearest = points[outside].to_crs("EPSG:3035").sjoin_nearest(municipalities.to_crs("EPSG:3035"), how="left")
        nearest = nearest[~nearest.index.duplicated()]
        joined.loc[outside, "ine_code"] = nearest["ine_code"]
    zones["municipality_code"] = joined["ine_code"].values
    zones["parent_id"] = zones["municipality_code"].map(municipality_id)
    return zones


def run(snapshot: str, workers: int) -> None:
    raw = raw_dir(PIPELINE, snapshot) / "cadastralzoning.zip"
    if not raw.exists():
        raise SystemExit(f"Missing {raw}: run import_inspire.py zoning first (see the README)")
    zones = link_municipalities(parse(read_zones(raw, workers)))
    zones = zones.sort_values("id", ignore_index=True)

    out = output_dir(PIPELINE)
    parquet = out / f"cadastral_zones_{snapshot}.parquet"
    zones.to_parquet(parquet, compression="zstd", write_covering_bbox=True, row_group_size=100_000)
    source = {"kind": "file", "origin": "Catastro INSPIRE cadastral parcels (ATOM), cadastralzoning", "snapshot": snapshot}
    write_run_metadata(out / f"cadastral_zones_{snapshot}.meta.json", DATASET, date.today().isoformat(), source, raw, len(zones))
    counts = zones["zone_type"].value_counts().to_dict()
    log.info("Wrote %s (%d zones: %s; %.0f MB)", parquet, len(zones), counts, parquet.stat().st_size / 1e6)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cadastral zones (masas) of Spain as GeoParquet.")
    parser.add_argument("--snapshot", default=SNAPSHOT, help=f"raw folder written by import_inspire.py (default {SNAPSHOT})")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="parallel readers (default: all cores)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.snapshot, args.workers)
