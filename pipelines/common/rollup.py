"""
Aggregating statistics up the territorial hierarchy: data is downloaded at its most detailed level
and every level above is the sum of the one below.

INE codes nest (section 2807901001 → district 2807901 → municipality 28079 → province 28), so
parents come from the codes themselves, for any year; provinces map to autonomous communities with
the provinces pipeline's output. Only additive measures (counts) are aggregated: rates and means are
computed afterwards at each level from aggregated components.
"""

import logging
from pathlib import Path

import pandas as pd

from .paths import DATA_DIR

log = logging.getLogger(__name__)

#: Levels from the most detailed up, with how to get a unit's code from a census section code.
LEVELS = ["census_section", "census_district", "municipality", "province", "autonomous_community", "country"]
CODE_LENGTH = {"census_section": 10, "census_district": 7, "municipality": 5, "province": 2}
ID_PREFIX = {
    "census_section": "es:ine:sec:",
    "census_district": "es:ine:dist:",
    "municipality": "es:ine:mun:",
    "province": "es:ine:prov:",
    "autonomous_community": "es:ine:ccaa:",
}
#: Spain as a whole.
COUNTRY_ID = "es:country:es"


def ccaa_by_province() -> pd.Series:
    provinces = pd.read_parquet(DATA_DIR / "processed/provinces/provinces.parquet", columns=["ine_code", "ccaa_code"])
    return provinces.set_index("ine_code")["ccaa_code"]


def parent_codes(codes: pd.Series, level: str, ccaa: pd.Series) -> pd.Series:
    """The codes of `level` that units with these (more detailed) codes belong to."""
    if level in CODE_LENGTH:
        return codes.str[: CODE_LENGTH[level]]
    if level == "autonomous_community":
        mapped = codes.str[:2].map(ccaa)
        if mapped.isna().any():
            raise ValueError(f"Provinces without autonomous community: {sorted(codes[mapped.isna()].str[:2].unique())}")
        return mapped
    if level == "country":
        return pd.Series("es", index=codes.index)
    raise ValueError(f"Unknown level {level}")


def entity_ids(codes: pd.Series, level: str) -> pd.Series:
    return pd.Series(COUNTRY_ID, index=codes.index) if level == "country" else ID_PREFIX[level] + codes


def rollup(base: pd.DataFrame, base_level: str, dimensions: list[str], value: str = "value") -> dict[str, pd.DataFrame]:
    """
    `base` has `code` (at `base_level`), `period`, the dimensions and `value`. Returns one frame per
    level from `base_level` up, each with `entity_id`, `code`, `period`, dimensions, `value` and
    `origin` ("published" for the base level, "aggregated" above).
    """
    ccaa = ccaa_by_province()
    keys = ["period", *dimensions]
    levels = LEVELS[LEVELS.index(base_level) :]
    out = {}
    for level in levels:
        if level == base_level:
            frame = base[["code", *keys, value]].copy()
            origin = "published"
        else:
            grouped = base.assign(code=parent_codes(base["code"], level, ccaa))
            frame = grouped.groupby(["code", *keys], as_index=False, observed=True)[value].sum(min_count=1)
            origin = "aggregated"
        frame.insert(0, "entity_id", entity_ids(frame["code"], level))
        frame["origin"] = origin
        out[level] = frame.sort_values(["entity_id", *keys], ignore_index=True)
        log.info("%s: %d rows (%s)", level, len(frame), origin)
    return out


def check_against(
    published: pd.DataFrame,
    aggregated: pd.DataFrame,
    level: str,
    dimensions: list[str],
    known: dict[tuple[str, int], str] | None = None,
) -> dict:
    """
    Compares the aggregated values of a level with the ones the source publishes for it (same
    `code`, period and dimensions). `known` lists differences already looked into, by (code,
    period), with why: they're reported apart and don't count as mismatches.
    """
    keys = ["code", "period", *dimensions]
    merged = published[[*keys, "value"]].merge(aggregated[[*keys, "value"]], on=keys, suffixes=("_published", "_aggregated"))
    differs = merged["value_published"] != merged["value_aggregated"]
    known = known or {}
    is_known = pd.Series([(code, period) in known for code, period in zip(merged["code"], merged["period"])], index=merged.index, dtype=bool)
    difference = (merged["value_published"] - merged["value_aggregated"]).abs()
    result = {
        "level": level,
        "compared": int(len(merged)),
        "mismatches": int((differs & ~is_known).sum()),
        "max_difference": float(difference[~is_known].max()) if (~is_known).any() else 0.0,
        "known_differences": [
            {"code": code, "period": int(period), "published": float(pub), "aggregated": float(agg), "why": known[(code, period)]}
            for code, period, pub, agg in merged.loc[differs & is_known, ["code", "period", "value_published", "value_aggregated"]].itertuples(index=False)
        ],
    }
    log.info("Check %s against published values: %s", level, result)
    return result


def write_levels(frames: dict[str, pd.DataFrame], folder: Path) -> dict[str, int]:
    """One Parquet file per level: {folder}/{level}.parquet."""
    folder.mkdir(parents=True, exist_ok=True)
    for level, frame in frames.items():
        frame.to_parquet(folder / f"{level}.parquet", compression="zstd", index=False)
    return {level: len(frame) for level, frame in frames.items()}
