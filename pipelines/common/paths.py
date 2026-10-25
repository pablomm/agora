"""Where pipelines keep what they download and what they produce."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Everything downloaded or generated; outside git, reproducible from the pipelines.
DATA_DIR = Path(os.environ.get("AGORA_DATA_DIR", ROOT / "data"))


def raw_dir(pipeline: str, version: str) -> Path:
    """Source files as downloaded, one folder per retrieval, never edited."""
    path = DATA_DIR / "raw" / pipeline / version
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(pipeline: str) -> Path:
    """The pipeline's normalised output, ready to load into the catalogue or build tiles from."""
    path = DATA_DIR / "processed" / pipeline
    path.mkdir(parents=True, exist_ok=True)
    return path
