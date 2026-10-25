"""Downloads and checksums for raw source files."""

import hashlib
import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)


def download(url: str, target: Path, params: dict | None = None, timeout: tuple[int, int] = (30, 600)) -> None:
    """Streams a response to disk; a failed download leaves no file behind."""
    log.info("Downloading %s", url)
    partial = target.with_suffix(target.suffix + ".part")
    try:
        with requests.get(url, params=params, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with partial.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    file.write(chunk)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(target)
    log.info("Saved %s (%.1f MB)", target, target.stat().st_size / 1e6)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
