"""
Vector tiles (PMTiles) of the administrative boundaries, one file per layer, built with tippecanoe
from the outputs of the autonomous_communities, provinces, municipalities, census_sections,
postal_codes and cadastre pipelines.

Each layer has its own zoom range: tiles are built up to its max zoom, and the map scales the
last level up beyond it (overzoom). One file per layer is what makes that work: a single file
has a single max zoom, past which coarser layers would vanish instead of scaling.

Features carry only their catalogue id, name, kind and, for census units, their district and
section numbers;
statistics are joined in the browser.

    python pipelines/tiles/admin_boundaries.py [layer ...]
"""

import argparse
import json
import logging
import subprocess
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common.paths import DATA_DIR, output_dir

log = logging.getLogger(__name__)

PIPELINE = "tiles"
ATTRIBUTION_IGN = '<a href="https://www.ign.es" target="_blank">CC BY 4.0 ign.es</a>'
ATTRIBUTION_INE = '<a href="https://www.ine.es" target="_blank">Elaboración propia con datos del INE</a>'
ATTRIBUTION_CATASTRO = '<a href="https://www.catastro.hacienda.gob.es" target="_blank">Dirección General del Catastro</a>'
# Urban parcels also come from the foral cadastres (see the cadastre README for each one's terms).
ATTRIBUTION_PARCELS = (
    ATTRIBUTION_CATASTRO
    + ", Información geográfica propiedad del Gobierno de Navarra"
    + ", Diputación Foral de Álava, Diputación Foral de Bizkaia, Diputación Foral de Gipuzkoa"
)
# Provenance of the postal code areas is still to be documented (see the postal_codes README).
ATTRIBUTION_POSTAL_CODES = "Códigos postales: elaboración propia"


#: Census edition the census layers are built from (see the census_sections pipeline), redrawn to
#: IGN's municipal boundaries by align_to_municipalities.py so they meet the municipalities layer.
CENSUS_YEAR = 2026
#: Catastro snapshot the urban parcels are built from (see the cadastre pipeline).
CADASTRE_SNAPSHOT = "2023-04"




def read(path: str, kind: str) -> gpd.GeoDataFrame:
    """A pipeline output (relative to processed/) as tile features: id, name, kind."""
    frame = gpd.read_parquet(DATA_DIR / "processed" / path, columns=["id", "name", "geometry"])
    return frame.assign(kind=kind)


def read_postal_codes() -> gpd.GeoDataFrame:
    """Postal code areas as tile features: the code is their name."""
    frame = gpd.read_parquet(DATA_DIR / "processed/postal_codes/postal_codes.parquet", columns=["id", "postal_code", "geometry"])
    return frame.rename(columns={"postal_code": "name"}).assign(kind="postal_code")


def municipality_names() -> pd.DataFrame:
    return pd.read_parquet(DATA_DIR / "processed/municipalities/municipalities.parquet", columns=["ine_code", "name"])


def by_province(dataset: str, columns: list[str]) -> Iterable[gpd.GeoDataFrame]:
    """A province-partitioned cadastre output, one province at a time (they don't fit in memory together)."""
    for path in sorted((DATA_DIR / f"processed/cadastre/{dataset}_{CADASTRE_SNAPSHOT}").glob("*.parquet")):
        yield gpd.read_parquet(path, columns=[*columns, "municipality_code", "geometry"]).merge(
            municipality_names(), left_on="municipality_code", right_on="ine_code", how="left"
        )


def read_rural_polygons() -> gpd.GeoDataFrame:
    """Cadastral polygons as tile features: id, kind, polygon number and their municipality's name."""
    frame = gpd.read_parquet(DATA_DIR / "processed/cadastre/rural_polygons_2023.parquet", columns=["id", "polygon", "municipality_code", "geometry"])
    frame = frame.merge(municipality_names(), left_on="municipality_code", right_on="ine_code", how="left")
    return frame[["id", "name", "polygon", "geometry"]].assign(kind="rural_polygon")


def read_parcels() -> Iterable[gpd.GeoDataFrame]:
    """Urban parcels as tile features: id, kind, reference and their municipality's name."""
    for frame in by_province("cadastral_parcels", ["id", "reference"]):
        yield frame[["id", "name", "reference", "geometry"]].assign(kind="cadastral_parcel")


def read_census(path: str, kind: str, numbers: dict[str, str]) -> gpd.GeoDataFrame:
    """
    Census units as tile features: id, kind, their numbers for the label (`numbers` maps output
    property to column: the district's, and for sections also their own) and, as `name`, their
    municipality's name as IGN writes it, like the municipalities layer.
    """
    frame = gpd.read_parquet(DATA_DIR / "processed" / path, columns=["id", *numbers.values(), "municipality_code", "geometry"])
    frame = frame.merge(municipality_names(), left_on="municipality_code", right_on="ine_code", how="left")
    if frame["name"].isna().any():
        missing = sorted(frame.loc[frame["name"].isna(), "municipality_code"].unique())
        raise ValueError(f"Census units in municipalities IGN doesn't have: {missing[:10]}")
    frame = frame.rename(columns={column: name for name, column in numbers.items()})
    return frame[["id", "name", *numbers, "geometry"]].assign(kind=kind)


#: Max zoom of every layer of the administrative and census hierarchy (autonomous communities down to
#: sections). Their boundaries coincide (each level is the union of the next), but a layer whose
#: tiles stop at a lower zoom is scaled up from coarser, more simplified lines, which then miss
#: the finer layers' lines drawn over them. With one max zoom, no layer is scaled up under another.
HIERARCHY_MAX_ZOOM = 14


@dataclass
class Layer:
    #: Tileset and vector layer name; the tile server serves it under this name.
    name: str
    description: str
    #: The layer's features: id, name, kind (and optionally more properties) plus geometry, in
    #: EPSG:4326. Big layers yield them in chunks (one per province), written one file each.
    load: Callable[[], gpd.GeoDataFrame | Iterable[gpd.GeoDataFrame]]
    min_zoom: int
    #: Tiles are built up to here; the map overzooms past it.
    max_zoom: int
    attribution: str = ATTRIBUTION_IGN
    #: Part of the administrative and census hierarchy: its shared borders must match the other levels'.
    hierarchy: bool = True


LAYERS = [
    Layer(
        name="autonomous_communities",
        description="Autonomous communities and autonomous cities (IGN)",
        load=lambda: read("autonomous_communities/autonomous_communities.parquet", "autonomous_community"),
        min_zoom=0,
        max_zoom=HIERARCHY_MAX_ZOOM,
    ),
    Layer(
        name="provinces",
        description="Provinces (IGN)",
        load=lambda: read("provinces/provinces.parquet", "province"),
        min_zoom=0,
        max_zoom=HIERARCHY_MAX_ZOOM,
    ),
    Layer(
        name="municipalities",
        description="Municipalities and the shared territories between them (IGN)",
        load=lambda: pd.concat(
            [
                read("municipalities/municipalities.parquet", "municipality"),
                # Without them the layer would have holes (5.7 % of Navarra).
                read("municipalities/shared_territories.parquet", "shared_territory"),
            ],
            ignore_index=True,
        ),
        min_zoom=4,
        max_zoom=HIERARCHY_MAX_ZOOM,
    ),
    Layer(
        name="census_districts",
        description=f"Census districts, {CENSUS_YEAR} edition (INE)",
        load=lambda: read_census(f"census_sections/census_districts_{CENSUS_YEAR}_aligned.parquet", "census_district", {"district": "district_code"}),
        min_zoom=5,
        max_zoom=HIERARCHY_MAX_ZOOM,
        attribution=ATTRIBUTION_INE,
    ),
    Layer(
        name="census_sections",
        description=f"Census sections, {CENSUS_YEAR} edition (INE)",
        load=lambda: read_census(f"census_sections/census_sections_{CENSUS_YEAR}_aligned.parquet", "census_section", {"district": "district_code", "section": "section_code"}),
        min_zoom=6,
        max_zoom=HIERARCHY_MAX_ZOOM,
        attribution=ATTRIBUTION_INE,
    ),
    Layer(
        name="cadastral_parcels",
        description=f"Urban cadastral parcels: Catastro {CADASTRE_SNAPSHOT} and the foral cadastres of Navarra and the Basque Country",
        load=read_parcels,
        min_zoom=15,
        max_zoom=17,
        attribution=ATTRIBUTION_PARCELS,
        hierarchy=False,
    ),
    Layer(
        name="rural_polygons",
        description="Cadastral polygons (rural zoning): Catastro 2023-04 and the foral cadastres of Navarra and the Basque Country",
        load=read_rural_polygons,
        min_zoom=8,
        max_zoom=14,
        attribution=ATTRIBUTION_PARCELS,
        hierarchy=False,
    ),
    Layer(
        name="postal_codes",
        description="Postal code areas (snapshot of January 2024)",
        load=read_postal_codes,
        min_zoom=5,
        max_zoom=13,
        attribution=ATTRIBUTION_POSTAL_CODES,
        hierarchy=False,
    ),
]


def tippecanoe_version() -> str:
    result = subprocess.run(["tippecanoe", "--version"], capture_output=True, text=True, check=True)
    return (result.stdout or result.stderr).strip()


def write_features(layer: Layer, workdir: Path) -> tuple[list[Path], int]:
    """
    The layer's features as newline-delimited GeoJSON, which tippecanoe reads in parallel: one file,
    or one per chunk for layers that come in chunks.
    """
    loaded = layer.load()
    chunks = [loaded] if isinstance(loaded, gpd.GeoDataFrame) else loaded
    files, count = [], 0
    for index, chunk in enumerate(chunks):
        target = workdir / f"{layer.name}.{index:03d}.geojsonl"
        gpd.GeoDataFrame(chunk, geometry="geometry", crs="EPSG:4326").to_file(target, driver="GeoJSONSeq")
        files.append(target)
        count += len(chunk)
    return files, count


def build(layer: Layer, workdir: Path, out: Path) -> dict:
    features, count = write_features(layer, workdir)
    target = out / f"{layer.name}.pmtiles"
    command = [
        "tippecanoe",
        "--output", str(target),
        "--force",
        "--layer", layer.name,
        "--name", layer.name,
        "--description", layer.description,
        "--attribution", layer.attribution,
        "--minimum-zoom", str(layer.min_zoom),
        "--maximum-zoom", str(layer.max_zoom),
        # Neighbours share each border: simplify it once, so they don't gap or overlap.
        "--detect-shared-borders",
        # Keep the nodes where borders meet, in every hierarchy layer: the same border then
        # simplifies the same way in each level (a province's edge, and its municipalities').
        *(["--no-simplification-of-shared-nodes"] if layer.hierarchy else []),
        # A choropleth can't lose units: keep every feature, however dense the tile.
        "--no-feature-limit",
        "--no-tile-size-limit",
        "--read-parallel",
        "--quiet",
        *map(str, features),
    ]
    log.info("Building %s (%d features, z%d–%d)", target.name, count, layer.min_zoom, layer.max_zoom)
    subprocess.run(command, check=True)
    log.info("Wrote %s (%.1f MB)", target, target.stat().st_size / 1e6)
    return {
        "name": layer.name,
        "description": layer.description,
        "min_zoom": layer.min_zoom,
        "max_zoom": layer.max_zoom,
        "features": count,
        "bytes": target.stat().st_size,
    }


def run(names: list[str]) -> None:
    layers = [layer for layer in LAYERS if not names or layer.name in names]
    unknown = set(names) - {layer.name for layer in LAYERS}
    if unknown:
        raise SystemExit(f"Unknown layers: {sorted(unknown)}; available: {[layer.name for layer in LAYERS]}")
    out = output_dir(PIPELINE)
    with tempfile.TemporaryDirectory(dir=DATA_DIR) as workdir:
        built = [build(layer, Path(workdir), out) for layer in layers]
    # Layers not rebuilt this time keep their entry from the last build.
    meta_path = out / "admin_boundaries.meta.json"
    previous = json.loads(meta_path.read_text())["layers"] if meta_path.exists() else []
    rebuilt = {layer["name"] for layer in built}
    order = [layer.name for layer in LAYERS]
    entries = [layer for layer in previous if layer["name"] not in rebuilt and layer["name"] in order] + built
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tippecanoe": tippecanoe_version(),
        "layers": sorted(entries, key=lambda layer: order.index(layer["name"])),
    }
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Vector tiles of the administrative boundaries.")
    parser.add_argument("layers", nargs="*", help="layers to build (default: all)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.layers)
