"""
INE tables (INEbase, Tempus): download as CSV and read them into tidy frames.

The CSV export ("csv_bdsc": semicolon-separated, thousands with dots) writes each territory as
"{code} {name}" (5200101001 Melilla sección 01001), which is what joins it to the catalogue.
"""

import logging
from pathlib import Path

import pandas as pd

from .download import download

log = logging.getLogger(__name__)

CSV_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bdsc/{table}.csv"


def fetch_table(table: int, target: Path, refresh: bool = False) -> Path:
    if target.exists() and not refresh:
        log.info("Using today's download %s", target)
    else:
        download(CSV_URL.format(table=table), target)
    return target


def read_table(path: Path) -> pd.DataFrame:
    """Every column as text, values included (parse them with `values`)."""
    return pd.read_csv(path, sep=";", dtype=str, keep_default_na=False, encoding="utf-8-sig")


def codes(column: pd.Series) -> pd.Series:
    """The code in front of each "{code} {name}" (empty where the column is empty)."""
    return column.str.extract(r"^(\S+)\s", expand=False).fillna("")


def values(column: pd.Series) -> pd.Series:
    """INE numbers ("1.234.567", "12,5") as floats; empty or symbols ("..", "-") as missing."""
    cleaned = column.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")
