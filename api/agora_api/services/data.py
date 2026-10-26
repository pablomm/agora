"""
Values of variables, read from the pipelines' Parquet files with DuckDB.

A variable's facet says which dataset it comes from and which slice of it: a numerator filter
(dimension → code, or a list of codes that are summed) and, for ratios, a denominator filter; the
value is numerator / denominator × the variable's scale. Filters only use dimensions the dataset
has, so they can't reach anything but its columns.

A variable can have options: dimensions the user picks (a sex; a range of age groups, summed),
which facets refer to as "$dimension". Options come as {dimension: "code"} or, for ranges,
{dimension: "first..last"}; the ones left out take the variable's default.
"""

import math
import re

from agora_api.services import catalog, entities
from agora_api.services.db import NotFound, query

#: Level of an entity from its id, for units the catalogue has no row for (old census sections…).
ID_LEVELS = {
    "es:ine:sec:": "census_section",
    "es:ine:dist:": "census_district",
    "es:ine:mun:": "municipality",
    "es:ine:prov:": "province",
    "es:ine:ccaa:": "autonomous_community",
    "es:country:": "country",
}


def level_of(entity_id: str) -> str:
    for prefix, level in ID_LEVELS.items():
        if entity_id.startswith(prefix):
            return level
    raise NotFound(f"Unknown kind of entity {entity_id!r}")


def _range_label(codes: list[str], labels: dict[str, str]) -> str:
    """An age range's name ("De 0 a 14 años", "65 años o más"), from the first and last group's codes."""
    if len(codes) == 1:
        return labels[codes[0]]
    first = re.match(r"^Y_?(?:GE)?(\d+)", codes[0])
    last = re.match(r"^Y(?:\d+T(\d+)|_GE(\d+))$", codes[-1])
    if not first or not last:
        return f"{labels[codes[0]]} – {labels[codes[-1]]}"
    start = int(first[1])
    if last[2] is not None:
        return "Todas las edades" if start == 0 else f"{start} años o más"
    return f"De {start} a {last[1]} años"


def resolve_options(spec: dict, options: dict[str, str] | None) -> tuple[dict[str, list[str] | str], dict]:
    """
    The codes each option stands for ({dimension: code or list of codes}), defaults filled in, and
    how to say the choice ({dimension: {codes, label}}).
    """
    options = dict(options or {})
    chosen: dict[str, list[str] | str] = {}
    described = {}
    for option in spec["options"]:
        dimension = option["dimension"]
        codes = [value["code"] for value in option["values"]]
        labels = {value["code"]: value["label"] for value in option["values"]}
        asked = options.pop(dimension, None)
        if asked is None:
            picked = option["default"]
        elif option["range"]:
            first, _, last = asked.partition("..")
            last = last or first
            if first not in codes or last not in codes or codes.index(first) > codes.index(last):
                raise ValueError(f"Option {dimension}: {asked!r} isn't a range of {codes}")
            picked = codes[codes.index(first) : codes.index(last) + 1]
        else:
            if asked not in codes:
                raise ValueError(f"Option {dimension}: {asked!r} isn't one of {codes}")
            picked = asked
        if option["range"]:
            picked = picked if isinstance(picked, list) else [picked]
            picked = codes[codes.index(picked[0]) : codes.index(picked[-1]) + 1]
            described[dimension] = {"codes": picked, "label": _range_label(picked, labels)}
        else:
            described[dimension] = {"codes": [picked], "label": labels[picked]}
        chosen[dimension] = picked
    if options:
        raise ValueError(f"{spec['id']} has no option {', '.join(options)} (its options: {[option['dimension'] for option in spec['options']] or 'none'})")
    return chosen, described


def _apply(facet: dict, chosen: dict) -> dict:
    """The facet with "$dimension" in its filters replaced by the codes chosen."""

    def fill(filter_: dict | None) -> dict | None:
        if not filter_:
            return filter_
        return {key: chosen[code[1:]] if isinstance(code, str) and code.startswith("$") else code for key, code in filter_.items()}

    denominator = facet["denominator"]
    if denominator and "dataset" in denominator:
        denominator = {**denominator, "filter": fill(denominator["filter"])}
    else:
        denominator = fill(denominator)
    return {**facet, "numerator": fill(facet["numerator"]), "denominator": denominator}


def _applied(facet: dict, described: dict) -> dict:
    """The choices a facet applies: a source without a dimension (no age by census section) ignores its option."""
    denominator = facet["denominator"] or {}
    filters = [facet["numerator"], denominator.get("filter", {}) if "dataset" in denominator else denominator]
    used = {code[1:] for filter_ in filters for code in filter_.values() if isinstance(code, str) and code.startswith("$")}
    return {dimension: entry for dimension, entry in described.items() if dimension in used}


def _label(spec: dict, described: dict) -> str:
    """The variable's name with the choice ("Población · Mujeres"); a "total" choice, or a range of every value, adds nothing."""
    whole = {option["dimension"]: len(option["values"]) for option in spec["options"] if option["range"]}
    parts = [entry["label"] for dimension, entry in described.items() if entry["codes"] != ["total"] and len(entry["codes"]) != whole.get(dimension)]
    return " · ".join([spec["label"], *parts])


def _condition(filter_: dict, allowed: list[str], parameters: list) -> str:
    parts = []
    for dimension, codes in filter_.items():
        if dimension not in allowed:
            raise ValueError(f"Dimension {dimension!r} isn't in the dataset")
        codes = codes if isinstance(codes, list) else [codes]
        parts.append(f'"{dimension}" IN ({",".join("?" * len(codes))})')
        parameters.extend(codes)
    return " AND ".join(parts) or "TRUE"


def _within(within: str | None, level: str, parameters: list) -> str:
    """SQL restricting rows to the units of `level` inside `within` (by INE code prefixes)."""
    if not within:
        return "TRUE"
    container = entities.get(within)
    ranks = {entry["id"]: entry["rank"] for entry in catalog.levels()}
    if ranks[container["level"]] <= ranks[level]:
        raise ValueError(f"{within} ({container['level']}) doesn't contain units of level {level}")
    if container["level"] == "country":
        return "TRUE"
    if container["level"] == "autonomous_community":
        # Autonomous community codes don't prefix their provinces': list them.
        provinces = [child["code"] for child in entities.children(within, limit=100)[0]]
        prefixes, length = provinces, 2
    else:
        prefixes, length = [container["code"]], len(container["code"])
    if level == "autonomous_community":
        raise ValueError("Only Spain contains autonomous communities")
    parameters.append(length)
    parameters.extend(prefixes)
    return f"substr(code, 1, ?) IN ({','.join('?' * len(prefixes))})"


def _values(facet: dict, scale: float, level: str, where: str, parameters: list) -> list[dict]:
    """Rows of (entity_id, period, value) for a facet at a level, `where` already filtering rows."""
    source = catalog.dataset(facet["dataset"])
    allowed = source["dimensions"]
    numerator_parameters: list = []
    numerator = _condition(facet["numerator"], allowed, numerator_parameters)
    select = f"sum(value) FILTER (WHERE {numerator}) AS numerator"
    select_parameters = numerator_parameters
    other = facet["denominator"] if facet["denominator"] and "dataset" in facet["denominator"] else None
    if facet["denominator"] and not other:
        denominator_parameters: list = []
        denominator = _condition(facet["denominator"], allowed, denominator_parameters)
        select += f", sum(value) FILTER (WHERE {denominator}) AS denominator"
        select_parameters = numerator_parameters + denominator_parameters
    path = catalog.dataset_path(facet["dataset"], level).replace("'", "''")
    rows = query(
        f"SELECT entity_id, period, {select} FROM read_parquet('{path}') WHERE {where} GROUP BY entity_id, period",
        select_parameters + parameters,
    )
    if other:
        rows = _divide_by_other(rows, other, source["frequency"], level)
    out = []
    for row in rows:
        if facet["denominator"]:
            if not row["denominator"]:
                continue
            value = row["numerator"] / row["denominator"] * scale
        else:
            if row["numerator"] is None:
                continue
            value = row["numerator"] * scale
        out.append({"entity_id": row["entity_id"], "period": int(row["period"]), "value": value})
    return out


def _divide_by_other(rows: list[dict], other: dict, frequency: str, level: str) -> list[dict]:
    """
    Adds each row's denominator from another (yearly) dataset: its value for the row's unit in the
    row's year, or in its latest year for years after it.
    """
    source = catalog.dataset(other["dataset"])
    available = source["coverage"].get(level, [])
    if not available or not rows:
        return []
    wanted = {min(catalog.year_of(row["period"], frequency), max(available)) for row in rows}
    wanted &= set(available)
    if not wanted:
        return []
    parameters: list = []
    condition = _condition(other["filter"], source["dimensions"], parameters)
    entities = {row["entity_id"] for row in rows}
    path = catalog.dataset_path(other["dataset"], level).replace("'", "''")
    where = f"period IN ({','.join('?' * len(wanted))})"
    if len(entities) == 1:
        where += " AND entity_id = ?"
    values = query(
        f"SELECT entity_id, period, sum(value) AS denominator FROM read_parquet('{path}') WHERE {condition} AND {where} GROUP BY entity_id, period",
        parameters + sorted(wanted) + ([next(iter(entities))] if len(entities) == 1 else []),
    )
    by_key = {(row["entity_id"], int(row["period"])): row["denominator"] for row in values}
    latest = max(available)
    return [{**row, "denominator": by_key.get((row["entity_id"], min(catalog.year_of(row["period"], frequency), latest)))} for row in rows]


def _facet_info(facet: dict) -> dict:
    return {
        "id": facet["id"],
        "label": facet["label"],
        "dataset": facet["dataset"],
        "dataset_title": facet["dataset_title"],
        "license": facet["license"],
        "frequency": facet["frequency"],
    }


def _period(facet: dict, level: str, period: int | None) -> int:
    available = facet["coverage"].get(level, [])
    if period is None:
        return max(available)
    if period not in available:
        raise NotFound(f"No data for {period} at level {level} (available: {available[0]}–{available[-1]})")
    return period


#: How a change against the previous year is named in labels.
CHANGE_LABEL = "variación interanual"


def _previous(facet: dict, level: str, period: int) -> int:
    """The same period a year before (the same month, for monthly data), which must have data."""
    previous = period - 100 if facet["frequency"] == "monthly" else period - 1
    if previous not in facet["coverage"].get(level, []):
        raise NotFound(f"No data a year before {period} at level {level} to compare with")
    return previous


def _changes(current: dict[str, float], previous: dict[str, float], spec: dict) -> tuple[dict[str, float], str, str]:
    """
    Each unit's change against the year before: counts and amounts in euros as a percentage (units
    with none the year before left out), the rest as a difference in their unit (a rate in % becomes
    points).
    """
    if spec["kind"] == "count" or spec["unit"] == "€":
        values = {key: (value / previous[key] - 1) * 100 for key, value in current.items() if previous.get(key)}
        return values, "%", "percent"
    values = {key: value - previous[key] for key, value in current.items() if key in previous}
    return values, "puntos" if spec["unit"] == "%" else spec["unit"], "difference"


def _quantiles(values: list[float], parts: int = 5) -> list[float]:
    ordered = sorted(values)
    if not ordered:
        return []
    return [ordered[min(len(ordered) - 1, math.floor(len(ordered) * k / parts))] for k in range(1, parts)]


def observations(
    variable_id: str,
    level: str,
    period: int | None = None,
    facet_id: str | None = None,
    within: str | None = None,
    options: dict[str, str] | None = None,
    change: bool = False,
) -> dict:
    """
    A variable for every unit of a level in a year: what a choropleth needs. With `change`, each
    unit's change against the year before instead (see `_changes`): units are matched by id, so a
    census section redrawn between both years compares different areas.
    """
    if level not in catalog.level_ids():
        raise NotFound(f"Unknown level {level!r}")
    spec = catalog.variable(variable_id)
    chosen, described = resolve_options(spec, options)
    facet = catalog.facet_for(variable_id, level, facet_id)
    described = _applied(facet, described)
    year = _period(facet, level, period)
    parameters: list = [year]
    where = "period = ? AND " + _within(within, level, parameters)
    rows = _values(_apply(facet, chosen), spec["scale"], level, where, parameters)
    values = {row["entity_id"]: row["value"] for row in rows}
    label, unit, compared = _label(spec, described), spec["unit"], None
    if change:
        previous = _previous(facet, level, year)
        parameters = [previous]
        where = "period = ? AND " + _within(within, level, parameters)
        before = {row["entity_id"]: row["value"] for row in _values(_apply(facet, chosen), spec["scale"], level, where, parameters)}
        values, unit, kind = _changes(values, before, spec)
        label, compared = f"{label} · {CHANGE_LABEL}", {"from": previous, "as": kind}
    numbers = list(values.values())
    return {
        "variable": variable_id,
        "label": label,
        "options": described,
        "unit": unit,
        "change": compared,
        "level": level,
        "period": year,
        "facet": _facet_info(facet),
        "within": within,
        "values": values,
        "stats": {
            "count": len(numbers),
            "min": min(numbers) if numbers else None,
            "max": max(numbers) if numbers else None,
            "quantiles": _quantiles(numbers),
        },
    }


def series(entity_id: str, variable_id: str, facet_id: str | None = None, options: dict[str, str] | None = None) -> dict:
    """A unit's values over the years, from every facet that covers its level (or just the one asked for)."""
    level = level_of(entity_id)
    spec = catalog.variable(variable_id)
    chosen, described = resolve_options(spec, options)
    facets = [facet for facet in spec["facets"] if level in facet["coverage"] and (facet_id is None or facet["id"] == facet_id)]
    if not facets:
        raise NotFound(f"{variable_id} isn't available at level {level}")
    out = []
    for facet in facets:
        rows = _values(_apply(facet, chosen), spec["scale"], level, "entity_id = ?", [entity_id])
        if rows:
            out.append({**_facet_info(facet), "values": sorted(({"period": row["period"], "value": row["value"]} for row in rows), key=lambda row: row["period"])})
    default = spec["default_facet"].get(level)
    return {
        "entity_id": entity_id,
        "variable": variable_id,
        "label": _label(spec, described),
        "options": described,
        "unit": spec["unit"],
        "default_facet": default,
        "facets": out,
    }


def value(entity_id: str, variable_id: str, period: int | None = None, facet_id: str | None = None, options: dict[str, str] | None = None) -> dict:
    """One unit's value of a variable in a year (the latest by default)."""
    level = level_of(entity_id)
    spec = catalog.variable(variable_id)
    chosen, described = resolve_options(spec, options)
    facet = catalog.facet_for(variable_id, level, facet_id)
    described = _applied(facet, described)
    year = _period(facet, level, period)
    rows = _values(_apply(facet, chosen), spec["scale"], level, "entity_id = ? AND period = ?", [entity_id, year])
    if not rows:
        raise NotFound(f"No value of {variable_id} for {entity_id} in {year}")
    return {"entity_id": entity_id, "variable": variable_id, "label": _label(spec, described), "options": described, "unit": spec["unit"], "period": year, "value": rows[0]["value"], "facet": _facet_info(facet)}


def breakdown(entity_id: str, dataset_id: str, period: int | None = None) -> dict:
    """Every cell of a dataset for one unit and year (a population pyramid, nationality split…), with labels."""
    level = level_of(entity_id)
    source = catalog.dataset(dataset_id)
    available = source["coverage"].get(level)
    if not available:
        raise NotFound(f"{dataset_id} has no data at level {level}")
    year = max(available) if period is None else period
    if year not in available:
        raise NotFound(f"No data for {year} at level {level} (available: {available[0]}–{available[-1]})")
    columns = ", ".join(f'"{dimension}"' for dimension in source["dimensions"])
    path = catalog.dataset_path(dataset_id, level).replace("'", "''")
    rows = query(f"SELECT {columns}, value FROM read_parquet('{path}') WHERE entity_id = ? AND period = ?", [entity_id, year])
    if not rows:
        raise NotFound(f"No {dataset_id} data for {entity_id} in {year}")
    dimensions = catalog.dimensions()
    return {
        "entity_id": entity_id,
        "dataset": dataset_id,
        "dataset_title": source["title"],
        "license": source["license"],
        "period": year,
        "periods": available,
        "dimensions": [dimensions[dimension] for dimension in source["dimensions"]],
        "rows": rows,
    }


def rank(
    variable_id: str,
    level: str,
    period: int | None = None,
    within: str | None = None,
    top: int = 10,
    ascending: bool = False,
    facet_id: str | None = None,
    options: dict[str, str] | None = None,
    change: bool = False,
) -> dict:
    """The units of a level with the highest (or lowest) value, optionally inside another unit (or change against the year before)."""
    result = observations(variable_id, level, period, facet_id, within, options, change)
    ordered = sorted(result["values"].items(), key=lambda item: item[1], reverse=not ascending)[: max(1, min(top, 200))]
    labels = entities.names([entity_id for entity_id, _ in ordered])
    return {
        **{key: result[key] for key in ("variable", "label", "options", "unit", "change", "level", "period", "facet", "within")},
        "total_units": result["stats"]["count"],
        "order": "ascending" if ascending else "descending",
        "items": [{"rank": index + 1, "entity_id": entity_id, "name": labels.get(entity_id, entity_id), "value": number} for index, (entity_id, number) in enumerate(ordered)],
    }
