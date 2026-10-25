"""Connections: the catalogue (SQLite, read-only) and DuckDB for the Parquet files."""

import sqlite3
import threading
from contextlib import contextmanager

import duckdb

from agora_api.config import CATALOG_DB

_duckdb = duckdb.connect()
_lock = threading.Lock()


class NotFound(LookupError):
    """Something asked for (an entity, a variable, a period…) doesn't exist."""


@contextmanager
def catalog():
    """A read-only connection to the catalogue, rows as dicts."""
    if not CATALOG_DB.exists():
        raise RuntimeError(f"Missing {CATALOG_DB}: run `python -m agora_api.catalog.build`")
    connection = sqlite3.connect(f"file:{CATALOG_DB}?mode=ro", uri=True, check_same_thread=False)
    connection.row_factory = lambda cursor, row: {column[0]: value for column, value in zip(cursor.description, row)}
    try:
        yield connection
    finally:
        connection.close()


def query(sql: str, parameters: list | None = None) -> list[dict]:
    """A DuckDB query over Parquet files, rows as dicts (each thread gets its own cursor)."""
    with _lock:
        cursor = _duckdb.cursor()
    result = cursor.execute(sql, parameters or [])
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]
