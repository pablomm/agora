"""
Code lists for statistical dimensions: stable English codes for INE's Spanish labels.
Totals keep their own code ("total"), so a published total and the sum of its parts sit side by side.
"""

import re

SEX = {"Total": "total", "Hombres": "male", "Mujeres": "female"}

#: Spanish or foreign nationality (INE's "nacionalidad (española/extranjera)").
NATIONALITY_SPANISH_FOREIGN = {"Total": "total", "Española": "spanish", "Extranjera": "foreign"}


def age_group(label: str) -> str:
    """INE's five-year age groups as codes: "De 20 a 24 años" → Y20T24, "100 y más años" → Y_GE100."""
    if label in ("Todas las edades", "Total"):
        return "total"
    if match := re.fullmatch(r"De (\d+) a (\d+) años", label):
        return f"Y{match[1]}T{match[2]}"
    if match := re.fullmatch(r"(\d+) y más años", label):
        return f"Y_GE{match[1]}"
    raise ValueError(f"Unknown age group: {label!r}")


def mapped(labels, codes: dict[str, str], name: str):
    """The codes of `labels`, failing on any label the code list doesn't know."""
    unknown = set(labels) - set(codes)
    if unknown:
        raise ValueError(f"Unknown {name} labels: {sorted(unknown)}")
    return labels.map(codes)
