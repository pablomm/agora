"""
Autonomous communities of Spain from IGN's INSPIRE administrative units, as GeoParquet keyed by INE code.

Steps: download the second-order units from IGN's WFS (raw GeoJSON, kept as is), parse and
validate them, and write one row per autonomous community with its catalogue id.

    python pipelines/autonomous_communities/autonomous_communities.py [--refresh]
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

PIPELINE = "autonomous_communities"
DATASET = "ign_au_autonomous_communities"

# IGN's national code: "34" (Spain), the INE code of the autonomous community, and zeros for the levels below.
NATIONAL_CODE = re.compile(r"^34(?P<ccaa>\d{2})0{7}$")

# The level also holds "Territorios no asociados a ninguna autonomía" (the plazas de soberanía),
# which isn't one of INE's autonomous communities.
EXCLUDED_CODES = {"20"}
# 17 autonomous communities, plus the autonomous cities of Ceuta (18) and Melilla (19).
EXPECTED_CODES = {f"{n:02d}" for n in range(1, 20)}


def ccaa_id(ine_code: str) -> str:
    return f"es:ine:ccaa:{ine_code}"


def parse(raw: Path) -> gpd.GeoDataFrame:
    """One row per INE autonomous community or city; fails loudly on unexpected codes or counts."""
    rows = []
    for unit in ign.read_units(raw):
        match = NATIONAL_CODE.match(unit.national_code)
        if not match:
            raise ValueError(f"Unexpected IGN national code: {unit.national_code}")
        code = match["ccaa"]
        if code in EXCLUDED_CODES:
            continue
        rows.append(
            {
                "id": ccaa_id(code),
                "ine_code": code,
                "name": unit.name,
                "ign_code": unit.national_code,
                "geometry": unit.geometry,
            }
        )

    communities = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").sort_values("id", ignore_index=True)
    codes = set(communities["ine_code"])
    if codes != EXPECTED_CODES or len(communities) != len(EXPECTED_CODES):
        raise ValueError(f"Expected INE autonomous communities 01–19 once each; missing {sorted(EXPECTED_CODES - codes)}, extra {sorted(codes - EXPECTED_CODES)}")
    return communities


def run(refresh: bool = False) -> Path:
    """Downloads (once a day unless `refresh`), parses and writes `autonomous_communities.parquet` plus its run metadata."""
    retrieved = date.today().isoformat()
    raw = raw_dir(PIPELINE, retrieved) / "autonomous_communities.geojson"
    ign.fetch(ign.AUTONOMOUS_COMMUNITY, raw, refresh)

    communities = parse(raw)
    out = output_dir(PIPELINE)
    parquet = out / "autonomous_communities.parquet"
    communities.to_parquet(parquet, compression="zstd", write_covering_bbox=True)
    source = {"url": ign.SOURCE_URL, "params": ign.request_params(ign.AUTONOMOUS_COMMUNITY)}
    write_run_metadata(out / "autonomous_communities.meta.json", DATASET, retrieved, source, raw, len(communities))
    log.info("Wrote %s (%d autonomous communities, %.1f MB)", parquet, len(communities), parquet.stat().st_size / 1e6)
    return parquet


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous communities of Spain as GeoParquet.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(refresh=args.refresh)
