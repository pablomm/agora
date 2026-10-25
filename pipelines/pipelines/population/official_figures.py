"""
Official population figures (INE, Revisión del Padrón Municipal) by municipality and sex, every
year since 1996, aggregated to provinces, autonomous communities and Spain.

Only the municipal table is downloaded; the province table is downloaded too, but only to check
that the aggregation matches what INE publishes.

    python pipelines/population/official_figures.py [--refresh]
"""

import argparse
import json
import logging
from datetime import date, datetime, timezone

from common import codelists, ine
from common.download import sha256
from common.paths import output_dir, raw_dir
from common.rollup import check_against, rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "population"
DATASET = "population_official"
#: Cifras oficiales del padrón por municipio: every municipality, by sex, since 1996.
MUNICIPAL_TABLE = 29005
#: Population by province and sex: only to check the aggregation.
PROVINCE_TABLE = 2852

#: Where INE's own tables disagree: its province total isn't the sum of its municipal figures.
KNOWN_DIFFERENCES = {
    ("04", 1996): "Almería 1996: INE's province table gives 76 more people (501,761) than the sum of its municipalities (501,685).",
}


def run(refresh: bool) -> None:
    raw = raw_dir(PIPELINE, date.today().isoformat())
    municipal = ine.read_table(ine.fetch_table(MUNICIPAL_TABLE, raw / f"{MUNICIPAL_TABLE}.csv", refresh))
    base = municipal.assign(
        code=ine.codes(municipal["Municipios"]),
        period=municipal["Periodo"].astype(int),
        sex=codelists.mapped(municipal["Sexo"], codelists.SEX, "sex"),
        value=ine.values(municipal["Total"]),
    )
    # Empty cells: the municipality didn't exist that year (it was created later, or merged away).
    base = base[base["value"].notna()][["code", "period", "sex", "value"]]
    if not base["code"].str.fullmatch(r"\d{5}").all():
        raise ValueError("Municipal codes that aren't five digits")

    levels = rollup(base, "municipality", ["sex"])

    provinces = ine.read_table(ine.fetch_table(PROVINCE_TABLE, raw / f"{PROVINCE_TABLE}.csv", refresh))
    published = provinces.assign(
        code=ine.codes(provinces["Provincias"]),
        period=provinces["Periodo"].astype(int),
        sex=codelists.mapped(provinces["Sexo"], codelists.SEX, "sex"),
        value=ine.values(provinces["Total"]),
    )
    published = published[published["code"].str.fullmatch(r"\d{2}") & published["value"].notna()]
    check = check_against(published, levels["province"], "province", ["sex"], KNOWN_DIFFERENCES)
    if check["mismatches"]:
        raise ValueError(f"Aggregated provinces don't match INE's: {check}")

    out = output_dir(PIPELINE) / DATASET
    rows = write_levels(levels, out)
    metadata = {
        "dataset": DATASET,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"tables": {"base": MUNICIPAL_TABLE, "check": PROVINCE_TABLE}, "url": ine.CSV_URL},
        "raw": {"path": str(raw / f"{MUNICIPAL_TABLE}.csv"), "sha256": sha256(raw / f"{MUNICIPAL_TABLE}.csv")},
        "periods": [int(base["period"].min()), int(base["period"].max())],
        "rows_by_level": rows,
        "checks": [check],
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s", out, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Official population figures by municipality and sex, aggregated up.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.refresh)
