"""
INE's national statistical classifications, as tables for joining data later (not geographic):

- cnae2025, cnae2009: economic activities (section, division, group, class).
- cno11: occupations (major group, letter group, sub-major group, minor group, unit group).
- cned2014_a, cned2014_f: education, levels attained and fields of study.
- cpa22: products by activity (section to subcategory).

Each classification is one table of items: code, label, level, level name, parent code and position
(INE's order). Codes are as INE writes them, except CNAE and CPA's dots, dropped so both CNAE
versions write classes alike (0111). Parents come from the codes (CNAE, CPA, CNED-F) or from INE's
order (CNO-11 and CNED-A interleave digits and letters: 1 > A > 11 > 111 > 1111).

Correspondences, one table: CNAE-2009 <-> CNAE-2025 (both ways, as INE publishes them), CNO-11 ->
CIUO-08 (ISCO-08), CNED-A 2014 -> CINE-A 2011 (ISCED-A), and the census education levels used
across the platform (`education_level`) -> CNED-A.

    python pipelines/classifications/classifications.py [--refresh]
"""

import argparse
import json
import logging
import re
from datetime import date, datetime, timezone

import pandas as pd

from common.download import download, sha256
from common.paths import output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "classifications"
BASE = "https://www.ine.es/"
FILES = {
    "cnae2025": "daco/daco42/clasificaciones/cnae25/Estructura_CNAE2025.xlsx",
    "cnae2009": "daco/daco42/clasificaciones/cnae09/estructura_cnae2009.xls",
    "cnae2009_cnae2025": "daco/daco42/clasificaciones/cnae25/Correspondencia_CNAE09_CNAE25.xlsx",
    "cnae2025_cnae2009": "daco/daco42/clasificaciones/cnae25/Correspondencia_CNAE25_CNAE09.xlsx",
    "cno11": "daco/daco42/clasificaciones/cno11_estructura.xls",
    "cno11_ciuo08": "daco/daco42/clasificaciones/corr_cno11_ciuo08.xls",
    "cned2014_a": "daco/daco42/clasificaciones/cned14/CNED14_A_estr.xls",
    "cned2014_f": "daco/daco42/clasificaciones/cned14/CNED_F_estr.xlsx",
    "cned2014_a_cine2011_a": "daco/daco42/clasificaciones/cned14/CORR_CNED14_CINE11_A.xls",
    "cpa22": "clasifi/CPA_22_estructura.xlsx",
}

LEVEL_NAMES = {
    "cnae2025": ["Sección", "División", "Grupo", "Clase"],
    "cnae2009": ["Sección", "División", "Grupo", "Clase"],
    "cno11": ["Gran grupo", "Grupo principal", "Subgrupo principal", "Subgrupo", "Grupo primario"],
    "cned2014_a": ["Agregado", "Nivel de formación", "Grupo", "Nivel detallado"],
    "cned2014_f": ["Sector amplio", "Sector específico", "Sector detallado"],
    "cpa22": ["Sección", "División", "Grupo", "Clase", "Categoría", "Subcategoría"],
}

#: The census education levels (`education_level`, see the population pipeline) as CNED-A groups.
CENSUS_EDUCATION = {
    "primary_or_less": ["0", "1"],
    "no_schooling": ["AA"],
    "primary": ["AB"],
    "lower_secondary": ["2"],
    "upper_secondary": ["B"],
    "upper_secondary_general": ["BE"],
    "upper_secondary_vocational": ["BF", "BG", "BH"],
    "tertiary": ["C"],
    "vocational_higher": ["CI"],
    "university": ["6", "7", "8"],
    "bachelor": ["CJ"],
    "bachelor_long": ["CK"],
    "master": ["CL"],
    "doctorate": ["CM"],
}


def read(path, sheet=0) -> pd.DataFrame:
    """A sheet as text, without headers."""
    return pd.read_excel(path, sheet_name=sheet, header=None, dtype=str, engine="calamine")


def clean(text) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def items(codes: list[str], labels: list[str], levels: list[int], parents: list[str | None], classification: str) -> pd.DataFrame:
    names = LEVEL_NAMES[classification]
    return pd.DataFrame(
        {
            "classification": classification,
            "code": codes,
            "label": [clean(label) for label in labels],
            "level": levels,
            "level_name": [names[level - 1] for level in levels],
            "parent": parents,
            "position": range(len(codes)),
        }
    )


def by_order(codes: list[str], level_of) -> tuple[list[int], list[str | None]]:
    """Levels from `level_of`, and each code's parent: the last code seen one level up."""
    last: dict[int, str] = {}
    levels, parents = [], []
    for code in codes:
        level = level_of(code)
        levels.append(level)
        parents.append(last.get(level - 1))
        last[level] = code
    return levels, parents


def cnae(path, classification: str) -> pd.DataFrame:
    """CNAE: a section's letter, then divisions (2 digits), groups (3) and classes (4); dots dropped."""
    frame = read(path, 1 if classification == "cnae2025" else 0)
    frame = frame[frame[0].notna()].iloc[1:]
    codes = [code.replace(".", "").strip() for code in frame[0]]
    labels = list(frame[2] if classification == "cnae2009" else frame[1])
    levels, parents = by_order(codes, lambda code: 1 if code.isalpha() else len(code))
    return items(codes, labels, levels, parents, classification)


def cno11(path) -> pd.DataFrame:
    """CNO-11: major group (1 digit), letter group, sub-major (2 digits), minor (3), unit group (4)."""
    frame = read(path)
    frame = frame[frame[0].notna()]
    codes = [code.strip() for code in frame[0]]
    levels, parents = by_order(codes, lambda code: 2 if code.isalpha() else (1 if len(code) == 1 else len(code) + 1))
    return items(codes, list(frame[1]), levels, parents, "cno11")


def cned_a(path) -> pd.DataFrame:
    """CNED-A: aggregate (A, B, C), level (1 digit), group (2 letters), detailed level (2 digits)."""
    frame = read(path)
    frame = frame.iloc[4:]
    frame = frame[frame[0].notna()]
    codes = [code.strip() for code in frame[0]]
    level_of = lambda code: (1 if len(code) == 1 else 3) if code.isalpha() else (2 if len(code) == 1 else 4)
    levels, parents = by_order(codes, level_of)
    return items(codes, list(frame[1]), levels, parents, "cned2014_a")


def cned_f(path) -> pd.DataFrame:
    """CNED-F: broad (2 digits), narrow (3) and detailed (4) fields, each cell "code label"; parents by prefix."""
    frame = read(path).iloc[2:]
    # Row by row, broad to detailed: each field comes before the ones it holds.
    cells = [clean(cell).split(" ", 1) for row in frame.itertuples(index=False) for cell in row[:3] if isinstance(cell, str)]
    codes = [code for code, _ in cells]
    return items(codes, [label for _, label in cells], [len(code) - 1 for code in codes], [code[:-1] if len(code) > 2 else None for code in codes], "cned2014_f")


def cpa22(path) -> pd.DataFrame:
    """CPA 2.2: a section's letter, then divisions, groups, classes, categories and subcategories (dots dropped)."""
    frame = read(path, 1).iloc[2:]
    frame = frame[frame[0].notna()]
    codes = [code.replace(".", "").strip() for code in frame[0]]
    level_of = lambda code: 1 if code.isalpha() else {2: 2, 3: 3, 4: 4, 5: 5, 6: 6}[len(code)]
    levels, parents = by_order(codes, level_of)
    return items(codes, list(frame[1]), levels, parents, "cpa22")


def correspondences(paths: dict) -> pd.DataFrame:
    """Every correspondence, one row per pair: from (classification, code) to (classification, code, label)."""
    rows = []
    for name, (source, target) in {"cnae2009_cnae2025": ("cnae2009", "cnae2025"), "cnae2025_cnae2009": ("cnae2025", "cnae2009")}.items():
        frame = read(paths[name], 1).iloc[1:]
        for from_code, to_code, to_label in zip(frame[0], frame[2], frame[3]):
            rows.append((source, from_code.replace(".", "").strip(), target, to_code.replace(".", "").strip(), clean(to_label), None))
    frame = read(paths["cno11_ciuo08"]).iloc[3:]
    # Rows without a CNO-11 code are ISCO-08 occupations with no Spanish one ("No aplicable a España").
    for from_code, to_code, to_label, note in zip(frame[0], frame[3], frame[4], frame[6]):
        if isinstance(from_code, str) and isinstance(to_code, str):
            rows.append(("cno11", from_code.strip(), "ciuo08", to_code.strip(), clean(to_label), clean(note) if isinstance(note, str) else None))
    frame = read(paths["cned2014_a_cine2011_a"]).iloc[5:]
    for to_code, from_code in zip(frame[0], frame[1]):
        if isinstance(from_code, str):
            rows.append(("cned2014_a", from_code.strip(), "cine2011_a", to_code.strip(), None, None))
    for level, groups in CENSUS_EDUCATION.items():
        rows.extend(("education_level", level, "cned2014_a", group, None, None) for group in groups)
    return pd.DataFrame(rows, columns=["from_classification", "from_code", "to_classification", "to_code", "to_label", "note"])


def run(refresh: bool) -> None:
    raw = raw_dir(PIPELINE, date.today().isoformat())
    paths = {}
    for name, path in FILES.items():
        target = raw / path.split("/")[-1]
        if refresh or not target.exists():
            download(BASE + path, target)
        paths[name] = target

    tables = {
        "cnae2025": cnae(paths["cnae2025"], "cnae2025"),
        "cnae2009": cnae(paths["cnae2009"], "cnae2009"),
        "cno11": cno11(paths["cno11"]),
        "cned2014_a": cned_a(paths["cned2014_a"]),
        "cned2014_f": cned_f(paths["cned2014_f"]),
        "cpa22": cpa22(paths["cpa22"]),
    }
    pairs = correspondences(paths)

    # Every parent is a code of its classification, and every correspondence's codes exist.
    for name, table in tables.items():
        missing = set(table["parent"].dropna()) - set(table["code"])
        if missing or table["code"].duplicated().any():
            raise ValueError(f"{name}: parents not in the classification {sorted(missing)[:5]}, or repeated codes")
    for side in ("from", "to"):
        for name, codes in pairs.groupby(f"{side}_classification")[f"{side}_code"]:
            if name in tables:
                unknown = set(codes) - set(tables[name]["code"])
                if unknown:
                    raise ValueError(f"Correspondences name {name} codes it doesn't have: {sorted(unknown)[:10]}")

    out = output_dir(PIPELINE)
    items_table = pd.concat(tables.values(), ignore_index=True)
    items_table.to_parquet(out / "items.parquet", index=False)
    pairs.to_parquet(out / "correspondences.parquet", index=False)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": {name: {"url": BASE + path, "sha256": sha256(paths[name])} for name, path in FILES.items()},
        "items": {name: {"count": len(table), "by_level": table["level"].value_counts().sort_index().to_dict()} for name, table in tables.items()},
        "correspondences": pairs.groupby(["from_classification", "to_classification"]).size().rename("pairs").reset_index().to_dict("records"),
    }
    (out / "meta.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False, default=int) + "\n")
    log.info("Wrote %s: %s", out, {name: len(table) for name, table in tables.items()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="INE's national statistical classifications and their correspondences.")
    parser.add_argument("--refresh", action="store_true", help="download the files again")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.refresh)
