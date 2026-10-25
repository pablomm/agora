"""
Urban buildings of Spain from Catastro's INSPIRE buildings, as GeoParquet partitioned by province:
one row per building (its parts are folded into it), linked to its parcel and INE municipality.

Reads the buildings and building parts copied by import_inspire.py (one pair of GMLs per Catastro
municipality), keeps the urban ones, takes each building's floors from its parts (the highest
part), reprojects to EPSG:4326 and writes one file per Catastro province.

    python pipelines/cadastre/buildings.py [--snapshot 2023-04] [--workers N]
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
import pyogrio

from common.catastro import RURAL_REFERENCE, members_by_province, merge_pieces, municipality_codes, polygonal, read_gml
from common.download import sha256
from common.paths import output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre"
DATASET = "catastro_urban_buildings"
SNAPSHOT = "2023-04"
MEMBER = re.compile(r"^A\.ES\.SDGC\.BU\.(?P<code>\d{5})\.building\.gml$")
BUILDING_COLUMNS = [
    "localId",
    "currentUse",
    "numberOfBuildingUnits",
    "numberOfDwellings",
    "value",
    "beginning",
    "conditionOfConstruction",
    "beginLifespanVersion",
]


def building_id(catastro_municipality: str, reference: str) -> str:
    return f"es:catastro:building:{catastro_municipality}:{reference}"


def integers(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("Int64")


def read_member(args: tuple[str, str]) -> gpd.GeoDataFrame:
    """One municipality's urban buildings, with their floors, in EPSG:4326 (runs in a worker process)."""
    raw, member = args
    frame = read_gml(raw, member, BUILDING_COLUMNS)
    frame = frame[~frame["localId"].str.match(RURAL_REFERENCE.pattern)]
    parts = pyogrio.read_dataframe(
        f"/vsizip/{raw}/{member.replace('.building.gml', '.buildingpart.gml')}",
        columns=["localId", "numberOfFloorsAboveGround", "numberOfFloorsBelowGround"],
        read_geometry=False,
    )
    # Parts are "{building}_part{n}": a building is as high (and as deep) as its highest (deepest) part.
    parts["building"] = parts["localId"].str.replace(r"_part\d+$", "", regex=True)
    floors = parts.assign(
        above=integers(parts["numberOfFloorsAboveGround"]),
        below=integers(parts["numberOfFloorsBelowGround"]),
    ).groupby("building")[["above", "below"]].max()
    frame = frame.join(floors, on="localId")
    frame["catastro_municipality_code"] = MEMBER.match(member)["code"]
    return frame


def build_province(frames: list[gpd.GeoDataFrame], municipalities: pd.Series) -> gpd.GeoDataFrame:
    frame = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    frame = merge_pieces(frame, frame["catastro_municipality_code"] + ":" + frame["localId"], ["currentUse", "value"])
    geometry = polygonal(frame.geometry)
    keep = ~geometry.is_empty
    frame, geometry = frame[keep.values], geometry[keep.values]

    codes = frame["catastro_municipality_code"]
    references = frame["localId"]
    built = pd.to_datetime(frame["beginning"], errors="coerce")
    buildings = gpd.GeoDataFrame(
        {
            "id": [building_id(code, reference) for code, reference in zip(codes, references)],
            "reference": references,
            # INSPIRE's use codes: 1_residential, 2_agriculture, 3_industrial, 4_1_office, 4_2_retail, 4_3_publicServices.
            "current_use": frame["currentUse"].where(frame["currentUse"].str.match(r"^\d"), None),
            "dwellings": integers(frame["numberOfDwellings"]),
            "building_units": integers(frame["numberOfBuildingUnits"]),
            "floor_area_m2": integers(frame["value"]),
            "floors_above": frame["above"].astype("Int64"),
            "floors_below": frame["below"].astype("Int64"),
            "year_built": built.dt.year.astype("Int64"),
            "condition": frame["conditionOfConstruction"].where(frame["conditionOfConstruction"] != "-", None),
            "valid_from": pd.to_datetime(frame["beginLifespanVersion"], errors="coerce").dt.date,
            "catastro_municipality_code": codes,
            "municipality_code": codes.map(municipalities),
            # A building's reference is its parcel's.
            "parent_id": [f"es:catastro:parcel:{code}:{reference}" for code, reference in zip(codes, references)],
        },
        geometry=geometry.values,
        crs="EPSG:4326",
    )
    if buildings["municipality_code"].isna().any():
        missing = sorted(buildings.loc[buildings["municipality_code"].isna(), "catastro_municipality_code"].unique())
        raise ValueError(f"Catastro municipalities with no INE match: {missing[:10]}")
    return buildings.sort_values("id", ignore_index=True)


def run(snapshot: str, workers: int) -> None:
    raw = raw_dir(PIPELINE, snapshot) / "buildings.zip"
    if not raw.exists():
        raise SystemExit(f"Missing {raw}: run import_inspire.py buildings first (see the README)")
    municipalities = municipality_codes(snapshot)
    with zipfile.ZipFile(raw) as archive:
        provinces = members_by_province(archive.namelist(), MEMBER)

    out = output_dir(PIPELINE) / f"buildings_{snapshot}"
    out.mkdir(exist_ok=True)
    counts = {}
    with ProcessPoolExecutor(workers) as pool:
        for province, members in provinces.items():
            frames = list(pool.map(read_member, [(str(raw), member) for member in members], chunksize=4))
            buildings = build_province(frames, municipalities)
            buildings.to_parquet(out / f"{province}.parquet", compression="zstd", write_covering_bbox=True, row_group_size=100_000)
            counts[province] = len(buildings)
            log.info("Province %s: %d urban buildings", province, len(buildings))

    total = sum(counts.values())
    metadata = {
        "dataset": DATASET,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "retrieved_at": date.today().isoformat(),
        "source": {"kind": "file", "origin": "Catastro INSPIRE buildings (ATOM), building + buildingpart", "snapshot": snapshot},
        "raw": {"path": str(raw), "bytes": raw.stat().st_size, "sha256": sha256(raw)},
        "rows": total,
        "rows_by_catastro_province": counts,
    }
    (out.parent / f"buildings_{snapshot}.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s (%d urban buildings)", out, total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Urban buildings of Spain as GeoParquet.")
    parser.add_argument("--snapshot", default=SNAPSHOT, help=f"raw folder written by import_inspire.py (default {SNAPSHOT})")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="parallel readers (default: all cores)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.snapshot, args.workers)
