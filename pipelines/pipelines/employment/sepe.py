"""
SEPE's monthly municipal series: registered unemployment (paro registrado), job seekers
(demandantes de empleo) and registered contracts, every month since January 2006, by municipality,
aggregated to provinces, autonomous communities and Spain.

Each row of the source is a municipality and month with a total and two breakdowns that each add
up to it: sex × age band (sex × contract type for contracts) and economic sector.

Since 2022 SEPE hides counts from 1 to 4 as "<5". They're imputed so that every breakdown adds up
to its total again:

- A hidden total is taken from the same municipality's nearest months with a known total, kept
  within what its two breakdowns allow (each hidden cell is 1 to 4).
- The hidden cells of a breakdown share what's left of the total (the total minus its known cells),
  each between 1 and 4, in proportion to the municipality's own composition in 2019–2021 (complete
  data), blended with its province's composition that month.

Imputed cells are flagged (`origin = "imputed"`); totals and sums above a municipality are exact
where nothing was hidden.

The yearly CSVs have gaps (2013 after April; December 2020; 2026's paro file is cut short at the
source): those months come from the half-year XLS files.

    python pipelines/employment/sepe.py [--refresh]
"""

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from common.download import download, sha256
from common.paths import DATA_DIR, output_dir
from common.rollup import rollup, write_levels

log = logging.getLogger(__name__)

PIPELINE = "employment"
BASE_URL = "https://sede.sepe.gob.es/es/portaltrabaja/resources/sede/datos_abiertos/datos/"
FIRST_YEAR = 2006
#: Raw files of this retrieval (SEPE replaces its files every month).
RAW_VERSION = "2026-10-25"
#: Months of complete data (before suppression) that give each municipality's composition.
REFERENCE = (201901, 202112)
#: Weight of the province's composition against the municipality's own (in "months" of data).
PROVINCE_WEIGHT = 3.0
#: What "<5" stands for.
HIDDEN_RANGE = (1, 4)


@dataclass(frozen=True)
class Series:
    dataset: str
    #: Prefix of SEPE's file names.
    files: str
    #: The first breakdown: its dimensions and, for each source column after the total, its codes.
    first: tuple[str, str]
    first_cells: list[tuple[str, str]]
    sectors: list[str]


AGE_SEX = [("male", "Y_LT25"), ("male", "Y25T44"), ("male", "Y_GE45"), ("female", "Y_LT25"), ("female", "Y25T44"), ("female", "Y_GE45")]
SERIES = [
    Series("registered_unemployment", "Paro", ("sex", "age_band"), AGE_SEX, ["agriculture", "industry", "construction", "services", "no_previous_job"]),
    Series("job_seekers", "Dtes_empleo", ("sex", "age_band"), AGE_SEX, ["agriculture", "industry", "construction", "services", "no_previous_job"]),
    Series(
        "contracts",
        "Contratos",
        ("sex", "contract_type"),
        [
            ("male", "permanent_initial"),
            ("male", "temporary_initial"),
            ("male", "converted_permanent"),
            ("female", "permanent_initial"),
            ("female", "temporary_initial"),
            ("female", "converted_permanent"),
        ],
        ["agriculture", "industry", "construction", "services"],
    ),
]


def fetch(name: str, raw: Path, refresh: bool) -> Path | None:
    """A SEPE file in the raw folder (downloaded unless already there); None if SEPE doesn't have it."""
    target = raw / name
    if refresh or not target.exists():
        try:
            download(BASE_URL + name, target)
        except Exception as error:  # Not every file exists (a half-year not published yet…).
            log.info("Skipping %s: %s", name, error)
            return None
    return target


def read(path: Path) -> pd.DataFrame:
    """A source file as rows of month, municipality code and the raw cells (strings: "<5" stays)."""
    if path.suffix == ".csv":
        frame = pd.read_csv(path, sep=";", skiprows=1, encoding="latin1", dtype=str)
    else:
        frame = pd.read_excel(path, skiprows=1, dtype=str, engine="calamine")
    frame = frame[frame.iloc[:, 0].str.fullmatch(r"\d{6}(\.0)?", na=False)]
    cells = frame.iloc[:, 8:].apply(lambda column: column.str.strip().str.replace(r"\.0$", "", regex=True))
    cells.columns = range(cells.shape[1])
    cells.insert(0, "code", frame.iloc[:, 6].str.replace(r"\.0$", "", regex=True).str.zfill(5).values)
    cells.insert(0, "period", frame.iloc[:, 0].str[:6].astype(int).values)
    return cells.reset_index(drop=True)


def load(series: Series, raw: Path, refresh: bool) -> tuple[pd.DataFrame, list[Path]]:
    """Every month once: the yearly CSVs, then the half-year XLS files of the months they lack."""
    last_year = date.today().year
    paths = [fetch(f"{series.files}_por_municipios_{year}_csv.csv", raw, refresh) for year in range(FIRST_YEAR, last_year + 1)]
    paths = [path for path in paths if path]
    data = pd.concat([read(path) for path in paths], ignore_index=True)
    # A month cut short (2026's paro CSV stops in January) is taken whole from the XLS instead.
    counts = data.groupby("period").size()
    partial = counts.index[counts < 0.9 * counts.median()]
    if len(partial):
        log.info("%s: incomplete months in the CSVs, read from the XLS instead: %s", series.dataset, list(partial))
        data = data[~data["period"].isin(partial)]
    have = set(data["period"].unique())
    latest = max(have)
    for year in range(FIRST_YEAR, last_year + 1):
        for half, months in (("primer", range(1, 7)), ("segundo", range(7, 13))):
            wanted = {year * 100 + month for month in months}
            if wanted <= have or min(wanted) > latest + 100:
                continue
            path = fetch(f"{series.files}_por_municipios_{half}_semestre_{year}_xls.xls", raw, refresh)
            if not path:
                continue
            frame = read(path)
            frame = frame[~frame["period"].isin(have)]
            if len(frame):
                log.info("%s: %d months from %s", series.dataset, frame["period"].nunique(), path.name)
                data = pd.concat([data, frame], ignore_index=True)
                have |= set(frame["period"].unique())
            paths.append(path)
    duplicated = data.duplicated(["period", "code"])
    if duplicated.any():
        raise ValueError(f"{series.dataset}: {duplicated.sum()} repeated municipality-months")
    return data.sort_values(["code", "period"], ignore_index=True), paths


def allocate(remaining: np.ndarray, weights: np.ndarray, hidden: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Integers for the hidden cells of each row: each between 1 and 4, adding up to `remaining`, as
    close as possible to `weights` (shares). Where that's impossible the bounds give way (0, or more
    than 4). Returns the values and which rows needed that.
    """
    low, high = HIDDEN_RANGE
    count = hidden.sum(axis=1)
    infeasible = (remaining < low * count) | (remaining > high * count)
    floor = np.where(infeasible[:, None] & (remaining < low * count)[:, None], 0, low)
    cap = np.where(infeasible[:, None] & (remaining > high * count)[:, None], np.inf, high)
    values = np.where(hidden, floor, 0).astype(float)
    left = remaining - values.sum(axis=1)
    shares = np.where(hidden, weights, 0.0)
    shares = shares / np.where(shares.sum(axis=1, keepdims=True) > 0, shares.sum(axis=1, keepdims=True), 1)
    shares = np.where(hidden & (shares.sum(axis=1, keepdims=True) == 0), 1.0, shares)
    target = values + shares * np.maximum(left, 0)[:, None]
    # One unit at a time to the hidden cell furthest below its target, among those under the cap.
    for _ in range(int(np.max(left, initial=0))):
        active = left > 0
        if not active.any():
            break
        need = np.where(hidden & (values < cap), target - values, -np.inf)
        best = need.argmax(axis=1)
        rows = np.flatnonzero(active & np.isfinite(need.max(axis=1)))
        values[rows, best[rows]] += 1
        left[rows] -= 1
    return values, infeasible


def impute(series: Series, data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Numbers for every cell (hidden ones imputed), and which cells were imputed."""
    first_count = len(series.first_cells)
    raw = data.iloc[:, 2:].to_numpy(dtype=object)
    hidden = raw == "<5"
    values = np.where(hidden, np.nan, pd.DataFrame(raw).apply(pd.to_numeric, errors="coerce").to_numpy(dtype=float))
    if np.isnan(values[~hidden]).any():
        raise ValueError(f"{series.dataset}: cells that are neither numbers nor <5")
    groups = [slice(1, 1 + first_count), slice(1 + first_count, values.shape[1])]

    # Hidden totals: the municipality's nearest known months, within what both breakdowns allow.
    total_hidden = hidden[:, 0]
    low = np.full(len(values), HIDDEN_RANGE[0], dtype=float)
    high = np.full(len(values), HIDDEN_RANGE[1], dtype=float)
    for group in groups:
        known = np.nansum(values[:, group], axis=1)
        missing = hidden[:, group].sum(axis=1)
        low = np.maximum(low, known + HIDDEN_RANGE[0] * missing)
        high = np.minimum(high, known + HIDDEN_RANGE[1] * missing)
    nearby = pd.Series(values[:, 0]).groupby(data["code"].values).transform(lambda totals: totals.interpolate(limit_direction="both"))
    guess = np.where(nearby.isna(), (low + high) / 2, nearby.to_numpy())
    values[total_hidden, 0] = np.round(np.clip(guess, low, np.maximum(low, high)))[total_hidden]

    # Composition: the municipality's own in the reference years, blended with its province's that month.
    codes = data["code"].to_numpy()
    reference = (data["period"] >= REFERENCE[0]) & (data["period"] <= REFERENCE[1])
    cells = values[:, 1:]
    own = pd.DataFrame(np.where(reference.to_numpy()[:, None], cells, np.nan)).groupby(codes).sum(min_count=1)
    own_months = pd.Series(reference.to_numpy()).groupby(codes).sum()
    own_share = own.div(own.sum(axis=1).replace(0, np.nan), axis=0)
    province = pd.DataFrame(np.where(hidden[:, 1:], np.nan, cells)).groupby([data["code"].str[:2].values, data["period"].values]).sum()
    keys = pd.MultiIndex.from_arrays([data["code"].str[:2].values, data["period"].values])
    province_share = province.reindex(keys).to_numpy()
    own_rows = own_share.reindex(codes).to_numpy()
    months = own_months.reindex(codes).fillna(0).to_numpy()[:, None]

    imputed = hidden.copy()
    stats = {"rows": int(len(values)), "rows_with_hidden_cells": int(hidden.any(axis=1).sum()), "hidden_cells": int(hidden.sum()), "hidden_totals": int(total_hidden.sum())}
    stats["infeasible_rows"] = 0
    for group in groups:
        part = slice(group.start - 1, group.stop - 1)
        group_province = province_share[:, part]
        group_province = group_province / np.where(np.nansum(group_province, axis=1, keepdims=True) > 0, np.nansum(group_province, axis=1, keepdims=True), 1)
        group_own = np.nan_to_num(own_rows[:, part] if own_rows.ndim == 2 else np.zeros_like(group_province))
        group_own = group_own / np.where(group_own.sum(axis=1, keepdims=True) > 0, group_own.sum(axis=1, keepdims=True), 1)
        weights = (months * group_own + PROVINCE_WEIGHT * np.nan_to_num(group_province)) / (months + PROVINCE_WEIGHT)
        group_hidden = hidden[:, group]
        rows = group_hidden.any(axis=1)
        remaining = values[rows, 0] - np.nansum(values[rows, group], axis=1)
        filled, infeasible = allocate(remaining, weights[rows], group_hidden[rows])
        block = values[rows, group]
        block[group_hidden[rows]] = filled[group_hidden[rows]]
        values[rows, group] = block
        stats["infeasible_rows"] += int(infeasible.sum())

    for group in groups:
        off = np.abs(values[:, group].sum(axis=1) - values[:, 0]) > 1e-9
        stats.setdefault("rows_not_adding_up", 0)
        stats["rows_not_adding_up"] += int(off.sum())
    return pd.DataFrame(values), pd.DataFrame(imputed), stats


def interpolate_months(series: Series, data: pd.DataFrame, values: pd.DataFrame, imputed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[int]]:
    """
    Months SEPE never published (December 2020) as the mean of the months around them, cell by
    cell, adjusted so the breakdowns add up to the total; every cell flagged as imputed.
    """
    months = sorted(data["period"].unique())
    calendar = [year * 100 + month for year in range(months[0] // 100, months[-1] // 100 + 1) for month in range(1, 13)]
    missing = [month for month in calendar if months[0] < month < months[-1] and month not in set(months)]
    if not missing:
        return data, values, imputed, missing
    first_count = len(series.first_cells)
    groups = [list(range(1, 1 + first_count)), list(range(1 + first_count, values.shape[1]))]
    indexed = values.set_index(pd.MultiIndex.from_frame(data[["code", "period"]]))
    new_keys, new_values = [], []
    for month in missing:
        before = max(period for period in months if period < month)
        after = min(period for period in months if period > month)
        previous = indexed.xs(before, level="period")
        following = indexed.xs(after, level="period")
        both = previous.index.intersection(following.index)
        mean = np.round((previous.loc[both].to_numpy() + following.loc[both].to_numpy()) / 2)
        for group in groups:
            # The difference goes to the group's largest cell.
            difference = mean[:, 0] - mean[:, group].sum(axis=1)
            largest = np.array(group)[mean[:, group].argmax(axis=1)]
            mean[np.arange(len(mean)), largest] += difference
        new_keys.append(pd.DataFrame({"period": month, "code": both}))
        new_values.append(pd.DataFrame(mean))
        log.info("%s: %s interpolated from %s and %s (%d municipalities)", series.dataset, month, before, after, len(both))
    keys = pd.concat(new_keys, ignore_index=True)
    data = pd.concat([data[["period", "code"]], keys], ignore_index=True)
    values = pd.concat([values, *new_values], ignore_index=True)
    imputed = pd.concat([imputed, pd.DataFrame(True, index=range(len(keys)), columns=imputed.columns)], ignore_index=True)
    return data, values, imputed, missing


def long_format(series: Series, data: pd.DataFrame, values: pd.DataFrame, imputed: pd.DataFrame) -> pd.DataFrame:
    """
    One row per municipality, month and cell, with every margin of the first breakdown (totals by
    sex, by age band…) so that any filter is a sum of rows; sectors only cross with the total.
    """
    first_dimension, second_dimension = series.first
    frames = []
    columns = {}
    for index, (sex, other) in enumerate(series.first_cells, start=1):
        columns[(sex, other, "total")] = [index]
    for index, sector in enumerate(series.sectors, start=1 + len(series.first_cells)):
        columns[("total", "total", sector)] = [index]
    # Margins of the first breakdown.
    for sex in ("male", "female"):
        columns[(sex, "total", "total")] = [index for index, (cell_sex, _) in enumerate(series.first_cells, start=1) if cell_sex == sex]
    for other in dict.fromkeys(other for _, other in series.first_cells):
        columns[("total", other, "total")] = [index for index, (_, cell_other) in enumerate(series.first_cells, start=1) if cell_other == other]
    columns[("total", "total", "total")] = [0]
    for (sex, other, sector), indexes in columns.items():
        frames.append(
            pd.DataFrame(
                {
                    "code": data["code"],
                    "period": data["period"],
                    first_dimension: sex,
                    second_dimension: other,
                    "sector": sector,
                    "value": values[indexes].sum(axis=1),
                    "imputed": imputed[indexes].any(axis=1),
                }
            )
        )
    out = pd.concat(frames, ignore_index=True)
    for dimension in (first_dimension, second_dimension, "sector"):
        out[dimension] = out[dimension].astype("category")
    return out


def run(refresh: bool) -> None:
    raw = DATA_DIR / "raw" / "employment_sepe" / RAW_VERSION
    raw.mkdir(parents=True, exist_ok=True)
    out = output_dir(PIPELINE)
    for series in SERIES:
        data, paths = load(series, raw, refresh)
        months = sorted(data["period"].unique())
        log.info("%s: %d municipality-months, %s to %s (%d months)", series.dataset, len(data), months[0], months[-1], len(months))
        values, imputed, stats = impute(series, data)
        data, values, imputed, interpolated = interpolate_months(series, data, values, imputed)
        stats["interpolated_months"] = interpolated
        log.info("%s: imputation %s", series.dataset, stats)
        base = long_format(series, data, values, imputed)
        dimensions = [*series.first, "sector"]
        levels = rollup(base, "municipality", dimensions)
        flags = base.set_index(["code", "period", *dimensions])["imputed"]
        municipal = levels["municipality"]
        is_imputed = flags.reindex(pd.MultiIndex.from_frame(municipal[["code", "period", *dimensions]])).to_numpy()
        municipal["origin"] = np.where(is_imputed, "imputed", "published")
        counts = write_levels(levels, out / series.dataset)
        metadata = {
            "dataset": series.dataset,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": {"publisher": "SEPE", "url": BASE_URL, "files": [{"name": path.name, "sha256": sha256(path)} for path in paths]},
            "periods": {"first": int(months[0]), "last": int(months[-1]), "count": int(data["period"].nunique()), "not_published": interpolated},
            "imputation": stats,
            "rows": counts,
        }
        (out / series.dataset / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SEPE's monthly municipal unemployment, job seekers and contracts.")
    parser.add_argument("--refresh", action="store_true", help="download every file again")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.refresh)
