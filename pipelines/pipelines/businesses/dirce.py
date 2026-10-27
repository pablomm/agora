"""
Companies (INE, Directorio Central de Empresas, DIRCE) by municipality and main activity, every year
since 2012, with provinces, autonomous communities and Spain.

One table, 4721 ("Empresas por municipio y actividad principal"), has every level. Companies count
where their registered seat is, on 1 January. INE publishes:

- every municipality's total, but hides the small ones (".", statistical secrecy);
- four activity groups (industry, construction, trade, transport and hospitality, other services)
  for about 3,100 municipalities, and other services split in six for about 1,300; the rest have no
  breakdown ("", not published);
- every group for provinces and Spain.

Hidden totals take what their province has beyond its published municipalities, shared out by
population (official figures, same year). Hidden groups of a municipality with a breakdown take what
its total (or other services) has beyond its published groups, shared out by the province's mix.
Communities are summed from provinces.

    python pipelines/businesses/dirce.py [--refresh]
"""

import argparse
import json
import logging
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from common import codelists, ine
from common.download import sha256
from common.imputation import share_out
from common.paths import DATA_DIR, output_dir, raw_dir
from common.rollup import ccaa_by_province, check_against, entity_ids, parent_codes, write_levels

log = logging.getLogger(__name__)

PIPELINE = "businesses"
DATASET = "companies"
TABLE = 4721
ACTIVITY = {
    "Total": "total",
    "Industria": "industry",
    "F Construcción": "construction",
    "Comercio, transporte y hostelería": "trade_transport_hospitality",
    "Total servicios": "other_services",
    "J Información y comunicaciones": "information_communication",
    "K Actividades financieras y de seguros": "finance_insurance",
    "L Actividades inmobiliarias": "real_estate",
    "MN Actividades profesionales y técnicas": "professional_technical",
    "Educación, sanidad y servicios sociales": "education_health_social",
    "Otros servicios personales": "other_personal_services",
}
#: Groups that add up to their parent ("Total servicios" is the services other than trade, transport and hospitality).
BREAKDOWNS = {
    "total": ["industry", "construction", "trade_transport_hospitality", "other_services"],
    "other_services": [
        "information_communication",
        "finance_insurance",
        "real_estate",
        "professional_technical",
        "education_health_social",
        "other_personal_services",
    ],
}
#: Hidden by statistical secrecy; an empty cell isn't published (no breakdown, or no municipality that year).
HIDDEN = "."
#: The most a hidden municipal total can be: INE publishes totals from 4 companies.
HIDDEN_TOTAL_MAX = 3
#: Why a province's total can be more than its municipalities': INE's figures disagree.
BEYOND = "INE's province total is more than its published municipalities plus what the hidden ones can hold (3 each)"


def read(raw, refresh: bool) -> pd.DataFrame:
    """Every cell: level, code, period, activity_group, value, hidden (empty cells left out)."""
    data = ine.read_table(ine.fetch_table(TABLE, raw / f"{TABLE}.csv", refresh))
    frame = pd.DataFrame(
        {
            "level": "country",
            "code": "es",
            "period": data["Periodo"].astype(int),
            "activity_group": codelists.mapped(data["Grupos CNAE"], ACTIVITY, "activity"),
            "value": ine.values(data["Total"]),
            "hidden": data["Total"] == HIDDEN,
        }
    )
    for level, column in (("province", "Provincias"), ("municipality", "Municipios")):
        codes = ine.codes(data[column])
        frame.loc[codes != "", "code"], frame.loc[codes != "", "level"] = codes[codes != ""], level
    if not frame.loc[frame["level"] == "municipality", "code"].str.fullmatch(r"\d{5}").all():
        raise ValueError("Municipal codes that aren't five digits")
    if frame.loc[frame["level"] != "municipality", "hidden"].any() or frame.loc[frame["level"] != "municipality", "value"].isna().any():
        raise ValueError("Provinces or Spain with hidden or empty cells")
    if frame.loc[~frame["hidden"] & (data["Total"] != ""), "value"].isna().any():
        raise ValueError("Cells that are neither numbers, '.' nor empty")
    return frame[frame["hidden"] | frame["value"].notna()].reset_index(drop=True)


def population_weights() -> pd.Series:
    """Each municipality's official population, by code and period (a weight for its total)."""
    population = pd.read_parquet(DATA_DIR / "processed/population/population_official/municipality.parquet")
    population = population[population["sex"] == "total"]
    return population.assign(activity_group="total").set_index(["code", "period", "activity_group"])["value"]


def impute_totals(municipal: pd.DataFrame, provinces: pd.DataFrame) -> tuple[pd.Series, dict]:
    """
    Hidden municipal totals: their province's total beyond its published municipalities, shared out
    by population, none above HIDDEN_TOTAL_MAX. Also returns, by (province, period), what the
    province has beyond what its municipalities can hold (INE's figures disagreeing).
    """
    totals = municipal[municipal["activity_group"] == "total"].assign(province=lambda frame: frame["code"].str[:2])
    published = totals[~totals["hidden"]].groupby(["province", "period"])["value"].sum()
    province_totals = provinces[provinces["activity_group"] == "total"].set_index(["code", "period"])["value"].rename_axis(["province", "period"])
    residual = province_totals - published.reindex(province_totals.index, fill_value=0)
    if (residual < 0).any():
        raise ValueError(f"Municipalities with more companies than their province: {residual[residual < 0].to_dict()}")
    hidden = totals[totals["hidden"]]
    weights = population_weights().reindex(pd.MultiIndex.from_frame(hidden[["code", "period", "activity_group"]])).fillna(0).to_numpy()
    values = pd.Series(0.0, index=hidden.index)
    for key, rows in hidden.groupby(["province", "period"]).groups.items():
        values[rows] = capped_shares(residual[key], weights[hidden.index.get_indexer(rows)], HIDDEN_TOTAL_MAX)
    held = values.groupby([hidden["province"], hidden["period"]]).sum().reindex(residual.index, fill_value=0)
    beyond = (residual - held)[lambda left: left > 0]
    return values, {key: float(left) for key, left in beyond.items()}


def capped_shares(total: float, weights: np.ndarray, cap: int) -> np.ndarray:
    """Integers adding up to `total` (at most `cap` each, so at most `cap` times as many) in proportion to `weights`."""
    weights = weights if weights.sum() > 0 else np.ones(len(weights))
    total = min(round(total), cap * len(weights))
    shares = np.zeros(len(weights))
    free = np.ones(len(weights), dtype=bool)
    # Units that would go over the cap are held at it, and what they can't take goes to the rest.
    while free.any():
        left = total - shares.sum()
        exact = left * np.where(free, weights, 0) / weights[free].sum() if weights[free].sum() > 0 else left * free / free.sum()
        over = free & (shares + exact > cap)
        if not over.any():
            shares += exact
            break
        shares[over] = cap
        free &= ~over
    values = np.floor(shares + 1e-9)
    # The largest remainders get one more until the total is reached.
    values[np.argsort(values - shares)[: int(total - values.sum())]] += 1
    return values


def impute_groups(municipal: pd.DataFrame, provinces: pd.DataFrame, parent: str) -> pd.Series:
    """
    Hidden groups of `parent` (its value already known) in municipalities that have its breakdown:
    what the parent has beyond the published groups, shared out by the province's groups.
    """
    groups = BREAKDOWNS[parent]
    cells = municipal[municipal["activity_group"].isin(groups)]
    hidden = cells[cells["hidden"]].assign(municipality=lambda frame: frame["code"])
    if hidden.empty:
        return pd.Series(dtype=float)
    parents = municipal[municipal["activity_group"] == parent].set_index(["code", "period"])["value"]
    published = cells[~cells["hidden"]].groupby(["code", "period"])["value"].sum()
    with_hidden = hidden[["code", "period"]].drop_duplicates().set_index(["code", "period"]).index
    residual = (parents.reindex(with_hidden) - published.reindex(with_hidden, fill_value=0)).rename("residual")
    residual = residual.rename_axis(["municipality", "period"]).reset_index()
    province = provinces.set_index(["code", "period", "activity_group"])["value"]
    keys = pd.MultiIndex.from_arrays([hidden["code"].str[:2], hidden["period"], hidden["activity_group"]])
    weights = pd.Series(province.reindex(keys).to_numpy(), index=pd.MultiIndex.from_frame(hidden[["code", "period", "activity_group"]]))
    return share_out(residual, hidden, weights, "municipality", [], by="activity_group")


def summed(child: pd.DataFrame, level: str, ccaa: pd.Series) -> pd.DataFrame:
    """`child` summed into `level`."""
    return child.assign(code=parent_codes(child["code"], level, ccaa)).groupby(["code", "period", "activity_group"], as_index=False)["value"].sum()


def check_breakdowns(frame: pd.DataFrame, level: str) -> dict:
    """Where a unit has a breakdown, its groups add up to their parent."""
    wide = frame.pivot_table(index=["code", "period"], columns="activity_group", values="value")
    result = {"level": level}
    for parent, groups in BREAKDOWNS.items():
        rows = wide[groups].notna().any(axis=1)
        difference = (wide.loc[rows, groups].sum(axis=1) - wide.loc[rows, parent]).abs()
        result[parent] = {"units": int(rows.sum()), "mismatches": int((difference > 0).sum()), "max_difference": float(difference.max()) if rows.any() else 0.0}
    log.info("Check breakdowns of %s: %s", level, result)
    return result


def run(refresh: bool) -> None:
    raw = raw_dir(PIPELINE, date.today().isoformat())
    cells = read(raw, refresh)
    levels = {level: frame.drop(columns="level").reset_index(drop=True) for level, frame in cells.groupby("level")}
    municipal, provinces = levels["municipality"], levels["province"]

    hidden_totals = municipal["hidden"] & (municipal["activity_group"] == "total")
    hidden_groups = municipal["hidden"] & ~hidden_totals
    values, beyond = impute_totals(municipal, provinces)
    municipal.loc[values.index, "value"] = values
    for parent in BREAKDOWNS:
        imputed = impute_groups(municipal, provinces, parent)
        municipal.loc[imputed.index, "value"] = imputed
    if municipal["value"].isna().any():
        raise ValueError("Municipal cells left without a value")
    imputation = {
        "hidden_totals": int(hidden_totals.sum()),
        "hidden_groups": int(hidden_groups.sum()),
        "by_period": municipal[municipal["hidden"]].groupby("period").size().to_dict(),
        "province_beyond_municipalities": {f"{province} {period}": left for (province, period), left in beyond.items()},
    }
    log.info("Imputed: %s", imputation)

    ccaa = ccaa_by_province()
    communities = summed(provinces, "autonomous_community", ccaa)
    totals = municipal[municipal["activity_group"] == "total"]
    checks = [
        check_against(provinces, summed(totals, "province", ccaa), "province", ["activity_group"], {key: BEYOND for key in beyond}),
        check_against(levels["country"], summed(provinces, "country", ccaa), "country", ["activity_group"]),
    ]
    breakdowns = [check_breakdowns(frame, level) for level, frame in (("municipality", municipal), ("province", provinces), ("country", levels["country"]))]
    if any(check["mismatches"] for check in checks) or any(check[parent]["mismatches"] for check in breakdowns for parent in BREAKDOWNS):
        raise ValueError(f"Values that don't add up: {checks + breakdowns}")

    frames = {}
    for level, frame, origin in (
        ("municipality", municipal, municipal["hidden"].map({True: "imputed", False: "published"})),
        ("province", provinces, "published"),
        ("autonomous_community", communities, "aggregated"),
        ("country", levels["country"], "published"),
    ):
        out = frame[["code", "period", "activity_group", "value"]].copy()
        out.insert(0, "entity_id", entity_ids(out["code"], level))
        out["origin"] = origin
        frames[level] = out.sort_values(["entity_id", "period", "activity_group"], ignore_index=True)

    out = output_dir(PIPELINE) / DATASET
    rows = write_levels(frames, out)
    metadata = {
        "dataset": DATASET,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"table": TABLE, "url": ine.CSV_URL},
        "raw": {"path": str(raw / f"{TABLE}.csv"), "sha256": sha256(raw / f"{TABLE}.csv")},
        "periods": [int(cells["period"].min()), int(cells["period"].max())],
        "rows_by_level": rows,
        "imputation": imputation,
        "checks": checks + breakdowns,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %s", out, rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Companies by municipality and main activity (DIRCE), with provinces, communities and Spain.")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.refresh)
