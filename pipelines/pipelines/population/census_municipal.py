"""
Annual Population Census (INE, since 2021): tables INE publishes only for some municipalities, so
they aren't aggregated up (a province would lack the rest). Residential mobility:

- population_previous_residence: where residents lived before (always here, another municipality,
  abroad, unknown), by sex and age, in municipalities of 500 residents or more (table 70382).
- population_arrival_municipality: when residents who came from another Spanish municipality
  arrived (within the last 1, 2, 3 or 5 years, or earlier), or that they've lived there since birth
  or since they came to Spain, by sex and age, in provincial capitals and main cities (table 70371).
  INE gives calendar years; they're turned into years before each census (1 January), so "within
  the last year" is the year before every period.
- population_residence_year_ago: where residents lived a year before (same municipality, another
  of the province, another province of the community, another community, abroad, not born yet),
  by sex, age and nationality, in the same cities (table 79570).

Education, residents aged 15 and over, in municipalities of 500 residents or more (2021 on):

- population_education_detail: highest level completed in detail (no schooling, primary, lower
  secondary, upper secondary general or vocational, higher vocational, university degrees, master,
  doctorate), nested in the groups published by census section, by sex and origin (born in Spain or
  abroad, Spanish or foreign nationality: tables 66621 and 66622). Its groups are checked against
  population_education, by census section, summed up to municipalities.
- population_studying: studies in progress (by level) or not studying, by sex and origin (tables
  66627 and 66628).
- population_education_age: highest level completed (grouped) by sex and age (table 66620).

Empty cells are structural (adults not born a year before; arrival years after the census) and count
as zero. Every breakdown is checked to add up to the totals INE publishes.

    python pipelines/population/census_municipal.py [dataset ...] [--refresh]
"""

import argparse
import json
import logging
import re
from datetime import date, datetime, timezone

import pandas as pd

from common import codelists, ine
from common.paths import output_dir, raw_dir
from common.rollup import check_against, entity_ids

log = logging.getLogger(__name__)

PIPELINE = "population"
#: How each table's other columns become dimensions: the dimension, and its code list (None: ages).
AGE = ("age", None)
NATIONALITY = ("nationality", codelists.NATIONALITY_SPANISH_FOREIGN)
#: Born in Spain or abroad, or Spanish or foreign nationality, in one dimension (from two tables).
ORIGIN_BORN = ("birth_nationality", {"Total": "total", "España": "born_spain", "Extranjero": "born_abroad"})
ORIGIN_NATIONALITY = ("birth_nationality", {"Total": "total", "Española": "spanish", "Extranjera": "foreign"})
#: The total of the education tables' ages.
ADULTS = "15 y más años"

#: Arrivals from another municipality counted as recent: within the last N years (always exact,
#: since INE gives single years from 2016 and the first census is 2021).
RECENT_YEARS = [1, 2, 3, 5]

DATASETS = {
    "population_previous_residence": {
        "raw": "population_migration",
        "tables": {70382: {"Edad": AGE}},
        "column": "Residencia anterior",
        "codes": codelists.PREVIOUS_RESIDENCE,
        "dimension": "previous_residence",
        "groups": {"came_from_elsewhere": ["other_municipality", "abroad"]},
    },
    "population_arrival_municipality": {
        "raw": "population_migration",
        "tables": {70371: {"Edad": AGE}},
        "column": "Año de llegada a municipio",
        "dimension": "arrival_municipality",
    },
    "population_residence_year_ago": {
        "raw": "population_migration",
        "tables": {79570: {"Edad": AGE, "Nacionalidad": NATIONALITY}},
        "column": "Residencia hace un año",
        "codes": codelists.RESIDENCE_YEAR_AGO,
        "dimension": "residence_year_ago",
        # The deepest first: each group is summed from what's already there.
        "groups": {
            "elsewhere_in_spain": ["same_province", "same_community", "other_community"],
            "moved_in": ["elsewhere_in_spain", "abroad"],
        },
    },
    "population_education_detail": {
        "raw": "population_education",
        "tables": {66621: {"País de nacimiento": ORIGIN_BORN}, 66622: {"Nacionalidad": ORIGIN_NATIONALITY}},
        "column": "Nivel de estudios",
        "codes": codelists.EDUCATION_DETAIL,
        "dimension": "education_level",
        "groups": {
            "primary_or_less": ["no_schooling", "primary"],
            "upper_secondary": ["upper_secondary_general", "upper_secondary_vocational"],
            "university": ["bachelor", "bachelor_long", "master", "doctorate"],
            "tertiary": ["vocational_higher", "university"],
        },
        "partitions": {"birth_nationality": [["born_spain", "born_abroad"], ["spanish", "foreign"]]},
    },
    "population_studying": {
        "raw": "population_education",
        "tables": {66627: {"Lugar de nacimiento": ORIGIN_BORN}, 66628: {"Nacionalidad": ORIGIN_NATIONALITY}},
        "column": "Nivel de estudios en curso",
        "codes": codelists.STUDYING,
        "dimension": "studying",
        "groups": {
            "studying": [
                "studying_primary_or_less",
                "studying_lower_secondary",
                "studying_upper_secondary_general",
                "studying_upper_secondary_vocational",
                "studying_tertiary",
                "studying_unknown",
            ]
        },
        "partitions": {"birth_nationality": [["born_spain", "born_abroad"], ["spanish", "foreign"]]},
    },
    "population_education_age": {
        "raw": "population_education",
        "tables": {66620: {"Edad": AGE}},
        "column": "Nivel de estudios",
        "codes": codelists.EDUCATION_GROUPED,
        "dimension": "education_level",
        "groups": {},
    },
}


def read(path, column: str, others: dict[str, tuple]) -> pd.DataFrame:
    """Rows with code, period, sex, the other columns as dimensions, the column's labels (`label`) and value (empty: 0)."""
    table = ine.read_table(path)
    frame = pd.DataFrame(
        {
            "code": ine.codes(table.iloc[:, 0]),
            "period": table["Periodo"].astype(int),
            "sex": codelists.mapped(table["Sexo"], codelists.SEX, "sex"),
            "label": table[column],
            "value": ine.values(table["Total"]).fillna(0),
        }
    )
    for name, (dimension, codes) in others.items():
        if codes is None:
            frame[dimension] = table[name].map(lambda label: "total" if label == ADULTS else codelists.age_group(label))
        else:
            frame[dimension] = codelists.mapped(table[name], codes, name)
    hidden = table["Total"].str.strip() == "."
    if hidden.any():
        raise ValueError(f"{path.name}: {int(hidden.sum())} hidden cells; this pipeline expects none")
    return frame


def within(years: int) -> str:
    """The code of arrivals within the last `years` years: within_1_year, within_5_years."""
    return f"within_{years}_year{'s' if years > 1 else ''}"


def arrival_bands(frame: pd.DataFrame) -> pd.DataFrame:
    """INE's arrival years turned into years before each census: within the last 1, 2, 3, 5 years, or earlier."""
    keys = [column for column in frame.columns if column not in ("label", "value")]
    year = frame["label"].map(lambda label: int(label) if re.fullmatch(r"\d{4}", label) else None)
    # Arrival years run up to the year before the census (1 January); later ones are empty.
    arrived = frame[year.notna()].assign(ago=lambda part: part["period"] - year[part.index])
    if (arrived.loc[arrived["value"] > 0, "ago"] < 1).any():
        raise ValueError("Arrivals after the census date")
    bands = [arrived[arrived["ago"] <= years].groupby(keys, as_index=False, observed=True)["value"].sum().assign(arrival_municipality=within(years)) for years in RECENT_YEARS]
    recent = max(RECENT_YEARS)
    # Arrived from another municipality before the last 5 years: older single years, and the decades.
    earlier_labels = ["2011-2015", "2001-2010", "1991-2000", "1981-1990", "Antes de 1981"]
    earlier = pd.concat([arrived[arrived["ago"] > recent], frame[frame["label"].isin(earlier_labels)]])
    earlier = earlier.groupby(keys, as_index=False, observed=True)["value"].sum().assign(arrival_municipality=f"more_than_{recent}_years")
    fixed = {
        "Total": "total",
        "No aplicable: siempre ha vivido en el mismo municipio desde que llegó a España": "since_arrival_in_spain",
        "No aplicable: siempre ha vivido en el mismo municipio desde que nació": "since_birth",
    }
    unknown = set(frame["label"]) - set(fixed) - set(earlier_labels) - set(frame.loc[year.notna(), "label"])
    if unknown:
        raise ValueError(f"Unknown arrival labels: {sorted(unknown)}")
    rest = frame[frame["label"].isin(fixed)].assign(arrival_municipality=lambda part: part["label"].map(fixed)).drop(columns="label")
    out = pd.concat([*bands, earlier, rest], ignore_index=True)
    within_recent = out[out["arrival_municipality"] == within(recent)]
    moved = pd.concat([within_recent, earlier]).groupby(keys, as_index=False, observed=True)["value"].sum().assign(arrival_municipality="from_other_municipality")
    return pd.concat([out, moved], ignore_index=True)


def check_by_section(frame: pd.DataFrame) -> dict:
    """The detailed levels' groups, by sex, against population_education (census sections summed up to municipalities)."""
    by_section = pd.read_parquet(output_dir(PIPELINE) / "population_education/municipality.parquet", columns=["code", "period", "sex", "education_level", "value"])
    mine = frame[(frame["birth_nationality"] == "total") & frame["education_level"].isin(["total", "primary_or_less", "lower_secondary", "upper_secondary", "tertiary"])]
    # Sections of small municipalities INE hides are imputed: compare the published ones only.
    imputed = pd.read_parquet(output_dir(PIPELINE) / "population_education/census_section.parquet", columns=["code", "period", "origin"])
    imputed = set(zip(imputed.loc[imputed["origin"] == "imputed", "code"].str[:5], imputed.loc[imputed["origin"] == "imputed", "period"]))
    mine = mine[[unit not in imputed for unit in zip(mine["code"], mine["period"])]]
    return check_against(mine, by_section, "municipality (groups against census sections)", ["sex", "education_level"])


def build(name: str, refresh: bool) -> None:
    spec = DATASETS[name]
    dimension = spec["dimension"]
    raw = raw_dir(spec["raw"], date.today().isoformat())
    frames = [read(ine.fetch_table(table, raw / f"{table}.csv", refresh), spec["column"], others) for table, others in spec["tables"].items()]
    others = ["sex", *dict.fromkeys(dimension for columns in spec["tables"].values() for dimension, _ in columns.values())]
    keys = ["code", "period", *others]
    # Tables merged into one dimension (origin by birth or by nationality) share their totals: once.
    frame = pd.concat(frames, ignore_index=True).drop_duplicates([*keys, "label"])

    if name == "population_arrival_municipality":
        frame = arrival_bands(frame)
        parts = ["from_other_municipality", "since_arrival_in_spain", "since_birth"]
    else:
        frame = frame.assign(**{dimension: codelists.mapped(frame["label"], spec["codes"], spec["column"])}).drop(columns="label")
        for group, members in spec["groups"].items():
            summed = frame[frame[dimension].isin(members)].groupby(keys, as_index=False, observed=True)["value"].sum().assign(**{dimension: group})
            frame = pd.concat([frame, summed], ignore_index=True)
        grouped = {member for members in spec["groups"].values() for member in members}
        parts = [code for code in spec["codes"].values() if code != "total" and code not in grouped] + [group for group in spec["groups"] if group not in grouped]

    # Every breakdown adds up to INE's totals: the categories, each sex, each age group, each nationality.
    checks = []
    published = frame[frame[dimension] == "total"]
    summed = frame[frame[dimension].isin(parts)].groupby(keys, as_index=False, observed=True)["value"].sum()
    checks.append(check_against(published, summed.assign(**{dimension: "total"}), f"municipality ({dimension})", [*others, dimension]))
    for other in others:
        rest = [column for column in keys if column != other]
        for partition in spec.get("partitions", {}).get(other, [None]):
            members = frame[frame[other].isin(partition)] if partition else frame[frame[other] != "total"]
            parts_of = members.groupby([*rest, dimension], as_index=False, observed=True)["value"].sum().assign(**{other: "total"})
            checks.append(check_against(frame[frame[other] == "total"], parts_of, f"municipality ({other}{': ' + ' + '.join(partition) if partition else ''})", [*others, dimension]))
    if name == "population_education_detail":
        checks.append(check_by_section(frame))
    failed = [check for check in checks if check["mismatches"]]
    if failed:
        raise ValueError(f"{name}: breakdowns don't add up to INE's totals: {failed}")

    if "origin" in keys:
        raise ValueError("A dimension can't be called origin: every row's origin says if it's published, aggregated or imputed")
    frame = frame[[*keys, dimension, "value"]].sort_values([*keys, dimension], ignore_index=True)
    frame.insert(0, "entity_id", entity_ids(frame["code"], "municipality"))
    frame["origin"] = "published"
    out = output_dir(PIPELINE) / name
    out.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out / "municipality.parquet", compression="zstd", index=False)
    metadata = {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"operation": "INE Censo de Población (463)", "url": ine.CSV_URL, "tables": list(spec["tables"])},
        "base_level": "municipality",
        "municipalities": int(frame["code"].nunique()),
        "periods": sorted(int(period) for period in frame["period"].unique()),
        "rows_by_level": {"municipality": len(frame)},
        "checks": checks,
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s: %d rows, %d municipalities", out, len(frame), metadata["municipalities"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Annual Population Census tables published for some municipalities: mobility and education.")
    parser.add_argument("datasets", nargs="*", help=f"datasets to build (default: all): {', '.join(DATASETS)}")
    parser.add_argument("--refresh", action="store_true", help="download again even if today's copy exists")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for name in args.datasets or DATASETS:
        build(name, args.refresh)
