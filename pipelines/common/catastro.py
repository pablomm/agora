"""
Helpers for Catastro's INSPIRE files (zoning, parcels, buildings): reading their GML, repairing
geometry, and mapping Catastro's municipality codes to INE's.
"""

import logging
import re

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyogrio
import shapely

from .paths import DATA_DIR

log = logging.getLogger(__name__)

#: Rural references: Catastro municipality (5) + a letter + polygon (3) + parcel (5), e.g. 12068A00200237.
#: Urban ones (14 characters too) start with the block and parcel: 0004101 00YL51A.
RURAL_REFERENCE = re.compile(r"^\d{5}[A-Z]\d{8}$")


def read_gml(raw: str, member: str, columns: list[str]) -> gpd.GeoDataFrame:
    """One GML from a zip in data/raw/, every field as text, reprojected to EPSG:4326."""
    # GDAL guesses each field's type file by file: labels like "008" would turn into 8 in some.
    pyogrio.set_gdal_config_options({"GML_FIELDTYPES": "ALWAYS_STRING"})
    frame = pyogrio.read_dataframe(f"/vsizip/{raw}/{member}", columns=columns)
    return frame.to_crs("EPSG:4326")


def polygonal(geometry: gpd.GeoSeries) -> gpd.GeoSeries:
    """
    Invalid geometry repaired with make_valid, keeping only its polygonal parts (make_valid can
    return collections with lines or points). Geometries left without area come back empty.
    """
    invalid = ~geometry.is_valid
    if not invalid.any():
        return geometry
    repaired = shapely.make_valid(geometry[invalid].values)
    parts = [
        geom if geom.geom_type in ("Polygon", "MultiPolygon")
        else shapely.union_all([part for part in shapely.get_parts(geom) if part.geom_type in ("Polygon", "MultiPolygon")])
        for geom in repaired
    ]
    geometry = geometry.copy()
    geometry[invalid] = parts
    return geometry


def municipality_codes(snapshot: str) -> pd.Series:
    """
    Catastro municipality code → INE municipality code, from the cadastral zones (run
    cadastral_zones.py first): the INE municipality most of each Catastro municipality's zones lie in.
    """
    zones = pd.read_parquet(
        DATA_DIR / f"processed/cadastre/cadastral_zones_{snapshot}.parquet",
        columns=["catastro_municipality_code", "municipality_code"],
    )
    counts = zones.groupby(["catastro_municipality_code", "municipality_code"]).size().rename("zones").reset_index()
    best = counts.sort_values("zones", ascending=False).drop_duplicates("catastro_municipality_code")
    return best.set_index("catastro_municipality_code")["municipality_code"]


def merge_pieces(
    frame: gpd.GeoDataFrame, key: pd.Series, consistent: list[str], summed: list[str] | None = None
) -> gpd.GeoDataFrame:
    """
    Units that come as several features with the same key (one per piece): one row each, with the
    pieces' union as geometry. `summed` columns (each piece's own area, say) add up; any other
    column keeps the first piece's value, and the run fails if pieces disagree on a `consistent` one.
    """
    split = key.duplicated(keep=False)
    if not split.any():
        return frame
    pieces = frame[split].assign(_key=key[split])
    # The union fails on invalid pieces: repair them first.
    pieces = pieces.set_geometry(polygonal(pieces.geometry))
    for column, values in pieces.groupby("_key")[consistent].nunique(dropna=False).items():
        if (values > 1).any():
            raise ValueError(f"Pieces of the same unit disagree on {column}")
    summed = summed or []
    for column in summed:
        pieces[column] = pd.to_numeric(pieces[column], errors="coerce")
    aggregation = {column: "sum" if column in summed else "first" for column in pieces.columns if column not in ("_key", pieces.geometry.name)}
    merged = pieces.dissolve(by="_key", aggfunc=aggregation).reset_index(drop=True)
    log.info("Merged %d features into %d units split in pieces", split.sum(), len(merged))
    return gpd.GeoDataFrame(pd.concat([frame[~split], merged], ignore_index=True), crs=frame.crs)


def members_by_province(names: list[str], pattern: re.Pattern) -> dict[str, list[str]]:
    """Zip members matching `pattern` (with a `code` group: the Catastro municipality), grouped by its province."""
    groups: dict[str, list[str]] = {}
    for name in sorted(names):
        match = pattern.match(name)
        if match:
            groups.setdefault(match["code"][:2], []).append(name)
    return groups


#: Column order of the urban parcels dataset, shared by the state Catastro's and the foral cadastres'
#: provinces so they read as one dataset.
PARCEL_COLUMNS = [
    "id",
    "reference",
    "area_m2",
    "valid_from",
    "catastro_municipality_code",
    "municipality_code",
    "zone_id",
    "parent_id",
    "source",
    "geometry",
]


def parcels_schema(parcels: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """The parcels with the dataset's columns, in order and with fixed types (empty columns included)."""
    parcels = parcels[PARCEL_COLUMNS].copy()
    for column in ["id", "reference", "catastro_municipality_code", "municipality_code", "zone_id", "parent_id", "source"]:
        parcels[column] = parcels[column].astype("string")
    parcels["area_m2"] = parcels["area_m2"].astype("Int64")
    # As an Arrow date even when every value is missing (some foral cadastres have no dates).
    parcels["valid_from"] = pd.to_datetime(parcels["valid_from"], errors="coerce").astype(pd.ArrowDtype(pa.timestamp("us"))).astype(pd.ArrowDtype(pa.date32()))
    return parcels
