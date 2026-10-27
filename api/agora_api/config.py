"""Where the API reads from: the pipelines' outputs and the catalogue built from them."""

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The pipelines' data folder (same variable the pipelines use); outputs are under processed/.
DATA_DIR = Path(os.environ.get("AGORA_DATA_DIR", REPO / "pipelines" / "data"))
PROCESSED_DIR = DATA_DIR / "processed"

#: Each pipeline's catalog.json: what it provides.
PIPELINES_DIR = REPO / "pipelines" / "pipelines"

#: The catalogue database, built by `python -m agora_api.catalog.build`.
CATALOG_DB = Path(os.environ.get("AGORA_CATALOG_DB", REPO / "api" / "data" / "catalog.sqlite"))

#: Where the API is reached from outside: download links handed to agents point here.
PUBLIC_URL = os.environ.get("AGORA_PUBLIC_URL", "http://localhost:8000").rstrip("/")
