"""
Urban parcels of the foral cadastres (Navarra, Álava, Bizkaia, Gipuzkoa), in the same schema as
the state Catastro's urban parcels and next to them, so the whole country is in one dataset.

Each Diputación publishes its cadastre its own way; one reader per territory turns it into rows of
id, reference, municipality and geometry. Files copied by import_foral.py.

    python pipelines/cadastre/foral_parcels.py [--snapshot 2023-05]
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

from common.catastro import merge_pieces, parcels_schema, polygonal
from common.paths import DATA_DIR, output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre_foral"
SNAPSHOT = "2023-05"
#: The state Catastro's parcels dataset these join (see cadastral_parcels.py).
CATASTRO_SNAPSHOT = "2023-04"
#: Working CRS of all four sources (ETRS89 / UTM 30N), where areas are measured.
SOURCE_CRS = "EPSG:25830"

#: INE province of each territory. Each source numbers its municipalities on its own; with the
#: province in front, that's mostly INE's code, but not always (Álava's 26 and 35 aren't INE's).
PROVINCES = {"alava": "01", "gipuzkoa": "20", "navarra": "31", "bizkaia": "48"}


def source_code(territory: str, number) -> str:
    """The source's municipality number as a five-digit code (province + three digits)."""
    return PROVINCES[territory] + str(int(number)).zfill(3)


def read_navarra(folder: Path) -> gpd.GeoDataFrame:
    # Only urban parcels: mixed ones (ParcelaMixta) are mostly rural land with some urban part.
    layer = "CATAST_Pol_ParcelaUrba — CATAST_Pol_ParcelaUrba.shp"
    frame = pyogrio.read_dataframe(folder / "Catastro.gpkg", layer=layer, columns=["REFCAT", "CMUNICIPIO", "BEGINLIFE"])
    return gpd.GeoDataFrame(
        {
            "source_municipality_code": [source_code("navarra", number) for number in frame["CMUNICIPIO"]],
            # Navarra's cadastral reference: polygon and parcel within the municipality.
            "reference": frame["REFCAT"].astype(str),
            "valid_from": pd.to_datetime(frame["BEGINLIFE"], format="%d/%m/%Y", errors="coerce").dt.date,
        },
        geometry=frame.geometry,
    )


def read_alava(folder: Path) -> gpd.GeoDataFrame:
    frames = []
    for archive in sorted(folder.glob("*_CatastroAlava.zip")):
        frame = pyogrio.read_dataframe(f"/vsizip/{archive}/parcela_urbana.shp", columns=["Municipio", "Poligono", "Parcela"])
        frames.append(
            gpd.GeoDataFrame(
                {
                    "source_municipality_code": [source_code("alava", number) for number in frame["Municipio"]],
                    "reference": [f"{int(polygon)}-{int(parcel)}" for polygon, parcel in zip(frame["Poligono"], frame["Parcela"])],
                    "valid_from": None,
                },
                geometry=frame.geometry,
            )
        )
    return pd.concat(frames, ignore_index=True)


def read_bizkaia(folder: Path) -> gpd.GeoDataFrame:
    """
    Bizkaia marks urban land on subparcels, not parcels. A parcel counts as urban when it has an
    urban subparcel ('Urb') that isn't scattered ('Diseminado'): houses on large rural estates are
    left out, as the state Catastro leaves them in rural parcels.
    """
    frames = []
    key = ["Codigo_Pol", "Codigo_Par"]
    for archive in sorted(folder.glob("*_SHP_*.zip")):
        code = re.match(r"^(\d{3})_", archive.name)[1]
        subparcels = pyogrio.read_dataframe(
            f"/vsizip/{archive}/{code}_Subparcela.shp", columns=[*key, "Codigo_Nat", "Diseminado"], read_geometry=False
        )
        urban = subparcels[(subparcels["Codigo_Nat"] == "Urb") & (subparcels["Diseminado"] == 0)][key].drop_duplicates()
        parcels = pyogrio.read_dataframe(f"/vsizip/{archive}/{code}_Parcela.shp", columns=["Codigo_Mun", *key])
        parcels = parcels.merge(urban, on=key)
        frames.append(
            gpd.GeoDataFrame(
                {
                    "source_municipality_code": [source_code("bizkaia", number) for number in parcels["Codigo_Mun"]],
                    "reference": [f"{int(polygon)}-{int(parcel)}" for polygon, parcel in zip(parcels["Codigo_Pol"], parcels["Codigo_Par"])],
                    "valid_from": None,
                },
                geometry=parcels.geometry,
            )
        )
    return pd.concat(frames, ignore_index=True)


def read_gipuzkoa(folder: Path) -> gpd.GeoDataFrame:
    frame = pyogrio.read_dataframe(f"/vsizip/{folder}/KATASTROA_CATASTRO.zip/HIRILUR_URBANO.shp", columns=["Erreferentz", "Herria"])
    return gpd.GeoDataFrame(
        {
            "source_municipality_code": [source_code("gipuzkoa", number) for number in frame["Herria"]],
            "reference": frame["Erreferentz"].astype(str),
            "valid_from": None,
        },
        geometry=frame.geometry,
    )


READERS = {"alava": read_alava, "gipuzkoa": read_gipuzkoa, "navarra": read_navarra, "bizkaia": read_bizkaia}


def build(territory: str, frame: gpd.GeoDataFrame, municipalities: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    frame = gpd.GeoDataFrame(frame, geometry="geometry", crs=SOURCE_CRS)
    frame = merge_pieces(frame, frame["source_municipality_code"] + ":" + frame["reference"], [])
    frame = frame.set_geometry(polygonal(frame.geometry))
    frame = frame[~frame.geometry.is_empty].reset_index(drop=True)
    area = frame.geometry.area.round().astype("Int64")
    frame = frame.to_crs("EPSG:4326")

    # The INE municipality, by position (a point inside the parcel; the nearest one off the coastline).
    points = gpd.GeoDataFrame(geometry=frame.geometry.representative_point(), crs="EPSG:4326")
    located = points.sjoin(municipalities, how="left", predicate="within")
    located = located[~located.index.duplicated()]["ine_code"].reindex(frame.index)
    outside = located.isna()
    if outside.any():
        nearest = points[outside].to_crs(SOURCE_CRS).sjoin_nearest(municipalities.to_crs(SOURCE_CRS), how="left")
        located[outside] = nearest[~nearest.index.duplicated()]["ine_code"]
    frame["municipality_code"] = located
    agreement = (located == frame["source_municipality_code"]).mean()
    log.info("%s: the source's municipality number is INE's for %.2f %% of parcels", territory, 100 * agreement)

    parcels = gpd.GeoDataFrame(
        {
            # The source's own municipality number: stable in the source, unlike INE's match.
            "id": [f"es:{territory}:parcel:{code}:{reference}" for code, reference in zip(frame["source_municipality_code"], frame["reference"])],
            "reference": frame["reference"],
            "area_m2": area,
            "valid_from": frame["valid_from"],
            "catastro_municipality_code": None,
            "municipality_code": frame["municipality_code"],
            # Foral cadastres have no blocks.
            "zone_id": None,
            "parent_id": "es:ine:mun:" + frame["municipality_code"],
            "source": territory,
        },
        geometry=frame.geometry.values,
        crs="EPSG:4326",
    )
    duplicated = parcels["id"][parcels["id"].duplicated()]
    if not duplicated.empty:
        raise ValueError(f"{territory}: duplicated ids, e.g. {sorted(duplicated)[:5]}")
    return parcels_schema(parcels.sort_values("id", ignore_index=True))


def run(snapshot: str) -> None:
    raw = raw_dir(PIPELINE, snapshot)
    if not (raw / "import.json").exists():
        raise SystemExit(f"Missing {raw}: run import_foral.py first (see the README)")
    municipalities = gpd.read_parquet(DATA_DIR / "processed/municipalities/municipalities.parquet", columns=["ine_code", "geometry"])
    # Next to the state Catastro's provinces, so the dataset covers the whole country.
    out = output_dir("cadastre") / f"cadastral_parcels_{CATASTRO_SNAPSHOT}"
    out.mkdir(exist_ok=True)
    counts = {}
    for territory, reader in READERS.items():
        parcels = build(territory, reader(raw / territory), municipalities)
        parcels.to_parquet(out / f"{PROVINCES[territory]}.parquet", compression="zstd", write_covering_bbox=True, row_group_size=100_000)
        counts[territory] = len(parcels)
        log.info("%s: %d urban parcels", territory, len(parcels))
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "snapshot": snapshot,
        "rows_by_territory": counts,
    }
    (out.parent / f"foral_parcels_{snapshot}.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Urban parcels of the foral cadastres, next to the state Catastro's.")
    parser.add_argument("--snapshot", default=SNAPSHOT, help=f"raw folder written by import_foral.py (default {SNAPSHOT})")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.snapshot)
