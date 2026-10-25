"""
Cadastral polygons (polígonos: the rural zoning that numbers rural parcels) of all of Spain: the
state Catastro's, from the cadastral zones, and the foral cadastres', in one GeoParquet linked to
INE municipalities.

    python pipelines/cadastre/rural_polygons.py

Needs cadastral_zones.py's output and the foral files copied by import_foral.py.
"""

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio

from common.catastro import merge_pieces, polygonal
from common.paths import DATA_DIR, output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre"
CATASTRO_SNAPSHOT = "2023-04"
FORAL_SNAPSHOT = "2023-05"
#: Working CRS of the foral sources (ETRS89 / UTM 30N).
SOURCE_CRS = "EPSG:25830"
PROVINCES = {"alava": "01", "gipuzkoa": "20", "navarra": "31", "bizkaia": "48"}


def source_code(territory: str, number) -> str:
    return PROVINCES[territory] + str(int(number)).zfill(3)


def foral_frame(territory: str, municipalities, polygons, geometry) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "source_municipality_code": [source_code(territory, number) for number in municipalities],
            "polygon": [str(int(number)).zfill(3) for number in polygons],
            "source": territory,
        },
        geometry=geometry,
        crs=SOURCE_CRS,
    )


def read_navarra(folder: Path) -> gpd.GeoDataFrame:
    layer = "CATAST_Pol_Poligono — CATAST_Pol_Poligono.shp"
    frame = pyogrio.read_dataframe(folder / "Catastro.gpkg", layer=layer, columns=["CMUNICIPIO", "POLIGONO"])
    return foral_frame("navarra", frame["CMUNICIPIO"], frame["POLIGONO"], frame.geometry)


def read_alava(folder: Path) -> gpd.GeoDataFrame:
    frames = []
    for archive in sorted(folder.glob("*_CatastroAlava.zip")):
        frame = pyogrio.read_dataframe(f"/vsizip/{archive}/poligono.shp", columns=["Municipio", "Poligono"])
        frames.append(foral_frame("alava", frame["Municipio"], frame["Poligono"], frame.geometry))
    return pd.concat(frames, ignore_index=True)


def read_bizkaia(folder: Path) -> gpd.GeoDataFrame:
    frames = []
    for archive in sorted(folder.glob("*_SHP_*.zip")):
        code = re.match(r"^(\d{3})_", archive.name)[1]
        frame = pyogrio.read_dataframe(f"/vsizip/{archive}/{code}_Poligono.shp", columns=["Codigo_Mun", "Codigo_Pol"])
        frames.append(foral_frame("bizkaia", frame["Codigo_Mun"], frame["Codigo_Pol"], frame.geometry))
    return pd.concat(frames, ignore_index=True)


def read_gipuzkoa(folder: Path) -> gpd.GeoDataFrame:
    """
    Gipuzkoa publishes no polygon layer: each polygon is the union of its rural parcels, whose
    references are "{polygon}-{parcel}" (01-370). So its polygons cover rural land only.
    """
    parcels = pyogrio.read_dataframe(f"/vsizip/{folder}/KATASTROA_CATASTRO.zip/LANDALUR_RUSTICA.shp", columns=["Erreferentz", "Herria"])
    parcels = parcels[parcels["Erreferentz"].str.match(r"^\d+-")]
    parcels["polygon"] = parcels["Erreferentz"].str.split("-").str[0]
    parcels = parcels.set_geometry(polygonal(parcels.geometry))
    dissolved = parcels.dissolve(by=["Herria", "polygon"]).reset_index()
    return foral_frame("gipuzkoa", dissolved["Herria"], dissolved["polygon"], dissolved.geometry)


READERS = {"alava": read_alava, "gipuzkoa": read_gipuzkoa, "navarra": read_navarra, "bizkaia": read_bizkaia}


def locate(frame: gpd.GeoDataFrame, municipalities: gpd.GeoDataFrame) -> pd.Series:
    """The INE municipality each polygon lies in, by a point inside it (nearest one off the coastline)."""
    points = gpd.GeoDataFrame(geometry=frame.geometry.representative_point(), crs=frame.crs)
    located = points.sjoin(municipalities, how="left", predicate="within")
    located = located[~located.index.duplicated()]["ine_code"].reindex(frame.index)
    outside = located.isna()
    if outside.any():
        nearest = points[outside].to_crs("EPSG:3035").sjoin_nearest(municipalities.to_crs("EPSG:3035"), how="left")
        located[outside] = nearest[~nearest.index.duplicated()]["ine_code"]
    return located


def foral_polygons(territory: str, frame: gpd.GeoDataFrame, municipalities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    key = frame["source_municipality_code"] + ":" + frame["polygon"]
    frame = merge_pieces(frame, key, [])
    frame = frame.set_geometry(polygonal(frame.geometry))
    frame = frame[~frame.geometry.is_empty].to_crs("EPSG:4326").reset_index(drop=True)
    frame["municipality_code"] = locate(frame, municipalities)
    frame["id"] = [f"es:{territory}:polygon:{code}:{polygon}" for code, polygon in zip(frame["source_municipality_code"], frame["polygon"])]
    log.info("%s: %d polygons", territory, len(frame))
    return frame


def catastro_polygons() -> gpd.GeoDataFrame:
    zones = gpd.read_parquet(
        DATA_DIR / f"processed/cadastre/cadastral_zones_{CATASTRO_SNAPSHOT}.parquet",
        columns=["id", "label", "catastro_municipality_code", "municipality_code", "geometry"],
        filters=[("zone_type", "==", "rural_polygon")],
    )
    log.info("catastro: %d polygons", len(zones))
    return zones.rename(columns={"label": "polygon", "catastro_municipality_code": "source_municipality_code"}).assign(source="catastro")


def run() -> None:
    raw = raw_dir("cadastre_foral", FORAL_SNAPSHOT)
    if not (raw / "import.json").exists():
        raise SystemExit(f"Missing {raw}: run import_foral.py first (see the README)")
    municipalities = gpd.read_parquet(DATA_DIR / "processed/municipalities/municipalities.parquet", columns=["ine_code", "geometry"])
    frames = [catastro_polygons()] + [foral_polygons(territory, reader(raw / territory), municipalities) for territory, reader in READERS.items()]
    columns = ["id", "polygon", "source_municipality_code", "municipality_code", "source", "geometry"]
    polygons = gpd.GeoDataFrame(pd.concat([frame[columns] for frame in frames], ignore_index=True), crs="EPSG:4326")
    polygons["parent_id"] = "es:ine:mun:" + polygons["municipality_code"]
    duplicated = polygons["id"][polygons["id"].duplicated()]
    if not duplicated.empty:
        raise ValueError(f"Duplicated polygon ids, e.g. {sorted(duplicated)[:5]}")
    polygons = polygons.sort_values("id", ignore_index=True)

    out = output_dir(PIPELINE)
    parquet = out / "rural_polygons_2023.parquet"
    polygons.to_parquet(parquet, compression="zstd", write_covering_bbox=True)
    counts = polygons["source"].value_counts().to_dict()
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshots": {"catastro": CATASTRO_SNAPSHOT, "foral": FORAL_SNAPSHOT},
        "rows": len(polygons),
        "rows_by_source": counts,
        "municipalities_covered": int(polygons["municipality_code"].nunique()),
    }
    (out / "rural_polygons_2023.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s (%d polygons: %s; %d municipalities)", parquet, len(polygons), counts, metadata["municipalities_covered"])


if __name__ == "__main__":
    argparse.ArgumentParser(description="Cadastral polygons of all of Spain as GeoParquet.").parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run()
