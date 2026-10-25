"""
Census sections and districts redrawn to IGN's municipal boundaries, so they tile each
municipality exactly (INE's cartography isn't IGN's: lines don't meet, and a few sections spill
into neighbours or shared territories).

For each municipality: every section of it is clipped to IGN's polygon, and what's left of the
municipality uncovered (gaps between INE's lines and IGN's) goes to the section it shares the
longest border with (or the nearest one if it touches none). Districts are then the union of
their redrawn sections. INE's own geometry stays in census_sections_{year}.parquet.

A section IGN places entirely in another municipality (two of Mislata's in 2026, inside València)
can't be clipped to its own: it keeps INE's geometry, flagged `aligned = False`.

    python pipelines/census_sections/align_to_municipalities.py [--year 2026] [--workers N]
"""

import argparse
import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from common.catastro import polygonal
from common.paths import DATA_DIR, output_dir

log = logging.getLogger(__name__)

PIPELINE = "census_sections"
LATEST_YEAR = 2026
#: Equal-area projection for Europe: overlays, borders and areas are measured here.
WORK_CRS = "EPSG:3035"
#: Gap pieces smaller than this (m²) are numerical noise of the overlay; they still get assigned.
MIN_REPORTED_GAP = 1.0


def align_municipality(args: tuple[shapely.Geometry, list[str], list[shapely.Geometry]]) -> tuple[list[shapely.Geometry], dict]:
    """One municipality's sections clipped to it and its gaps assigned (runs in a worker process)."""
    municipality, ids, sections = args
    clipped = [polygonal(gpd.GeoSeries([shapely.intersection(section, municipality)])).iloc[0] for section in sections]
    covered = shapely.union_all(clipped)
    gaps = [part for part in shapely.get_parts(shapely.difference(municipality, covered)) if part.geom_type == "Polygon" and part.area > 0]

    assigned: list[list[shapely.Geometry]] = [[] for _ in ids]
    for gap in gaps:
        borders = np.array([shapely.intersection(gap.boundary, section).length if not section.is_empty else 0.0 for section in clipped])
        if borders.max() > 0:
            target = int(borders.argmax())
        else:
            distances = np.array([gap.distance(section) if not section.is_empty else np.inf for section in clipped])
            target = int(distances.argmin())
        assigned[target].append(gap)

    aligned = [shapely.union_all([section, *pieces]) if pieces else section for section, pieces in zip(clipped, assigned)]
    # Nothing of the section inside its municipality: keep INE's geometry rather than lose the section.
    aligned = [original if section.is_empty else section for original, section in zip(sections, aligned)]
    stats = {
        "removed_m2": sum(section.area for section in sections) - sum(section.area for section in clipped),
        "gaps": sum(1 for gap in gaps if gap.area >= MIN_REPORTED_GAP),
        "gap_m2": sum(gap.area for gap in gaps),
        "emptied": [section_id for section_id, section in zip(ids, clipped) if section.is_empty],
    }
    return aligned, stats


def run(year: int, workers: int) -> None:
    folder = DATA_DIR / "processed" / PIPELINE
    sections = gpd.read_parquet(folder / f"census_sections_{year}.parquet").to_crs(WORK_CRS)
    municipalities = gpd.read_parquet(DATA_DIR / "processed/municipalities/municipalities.parquet", columns=["ine_code", "geometry"])
    municipalities = municipalities.to_crs(WORK_CRS).set_index("ine_code")
    missing = set(sections["municipality_code"]) - set(municipalities.index)
    if missing:
        raise ValueError(f"Sections in municipalities IGN doesn't have: {sorted(missing)[:10]}")

    groups = list(sections.groupby("municipality_code"))
    tasks = [(municipalities.geometry[code], group["id"].tolist(), group.geometry.tolist()) for code, group in groups]
    log.info("Aligning %d sections in %d municipalities", len(sections), len(groups))
    with ProcessPoolExecutor(workers) as pool:
        results = list(pool.map(align_municipality, tasks, chunksize=50))

    geometry = pd.Series(index=sections.index, dtype=object)
    totals = {"removed_m2": 0.0, "gaps": 0, "gap_m2": 0.0, "emptied": []}
    for (_, group), (aligned, stats) in zip(groups, results):
        geometry[group.index] = aligned
        for key in totals:
            totals[key] += stats[key]
    if totals["emptied"]:
        log.warning("Sections entirely outside their municipality, kept as INE draws them: %s", totals["emptied"])

    aligned = sections.set_geometry(gpd.GeoSeries(geometry, crs=WORK_CRS))
    aligned = aligned.set_geometry(polygonal(aligned.geometry))
    aligned["aligned"] = ~aligned["id"].isin(totals["emptied"])
    # Every municipality is now exactly the union of its (aligned) sections.
    check = aligned[aligned["aligned"]].dissolve("municipality_code").geometry
    difference = check.symmetric_difference(municipalities.geometry[check.index]).area / municipalities.geometry[check.index].area
    log.info("Largest difference between a municipality and its sections: %.6f %%", 100 * difference.max())

    # Districts are dissolved in the working CRS, before reprojecting (reprojection can leave tiny invalidities).
    districts = aligned.assign(district=aligned["municipality_code"] + aligned["district_code"]).dissolve(
        by="district",
        aggfunc={column: "first" for column in ["district_code", "municipality_code", "province_code", "ccaa_code", "municipality_name", "year"]},
    ).reset_index(names="ine_code")
    districts.insert(0, "id", "es:ine:dist:" + districts["ine_code"])
    districts["parent_id"] = "es:ine:mun:" + districts["municipality_code"]
    columns = ["id", "ine_code", "district_code", "municipality_code", "province_code", "ccaa_code", "municipality_name", "parent_id", "year", "geometry"]
    districts = districts[columns].sort_values("id", ignore_index=True)

    out = output_dir(PIPELINE)
    for frame, name in ((aligned, "sections"), (districts, "districts")):
        frame = frame.to_crs("EPSG:4326")
        frame = frame.set_geometry(polygonal(frame.geometry))
        frame.to_parquet(out / f"census_{name}_{year}_aligned.parquet", compression="zstd", write_covering_bbox=True)

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "year": year,
        "sections": len(aligned),
        "districts": len(districts),
        "area_removed_km2": round(totals["removed_m2"] / 1e6, 3),
        "gaps_filled": totals["gaps"],
        "gap_area_km2": round(totals["gap_m2"] / 1e6, 3),
        "max_municipality_difference_pct": float(100 * difference.max()),
        "not_aligned": totals["emptied"],
    }
    (out / f"census_{year}_aligned.meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info(
        "Wrote aligned sections and districts: %.1f km² cut off (outside their municipality), %d gaps filled (%.1f km²)",
        metadata["area_removed_km2"],
        metadata["gaps_filled"],
        metadata["gap_area_km2"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Census sections and districts redrawn to IGN's municipal boundaries.")
    parser.add_argument("--year", type=int, default=LATEST_YEAR, help=f"census edition (default {LATEST_YEAR})")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="parallel workers (default: all cores)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.year, args.workers)
