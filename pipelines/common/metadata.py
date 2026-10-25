"""The run details written next to each output: what was downloaded, when, and what came out."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .download import sha256


def write_run_metadata(path: Path, dataset: str, retrieved: str, source: dict, raw: Path, rows: int) -> None:
    metadata = {
        "dataset": dataset,
        "retrieved_at": retrieved,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": source,
        "raw": {"path": str(raw), "bytes": raw.stat().st_size, "sha256": sha256(raw)},
        "rows": rows,
    }
    path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")
