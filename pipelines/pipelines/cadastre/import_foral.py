"""
Copies the foral cadastres' parcel files (Navarra, Álava, Bizkaia, Gipuzkoa: the territories the
state Catastro doesn't cover) out of a local archive into data/raw/, leaving the archive untouched.

    python pipelines/cadastre/import_foral.py ARCHIVE_FOLDER [--snapshot 2023-05]

ARCHIVE_FOLDER has catastro_navarra/, catastro_alava/, Catastro_Bizkaia/ and guipuzcua_catastro/,
as downloaded from each Diputación in April–May 2023.
"""

import argparse
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from common.paths import raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre_foral"

#: Per territory: the archive's folder and the files to copy (glob patterns).
SOURCES = {
    # One GeoPackage with every layer of Navarra's cadastre (only the urban parcels are used).
    "navarra": ("catastro_navarra", ["Catastro.gpkg"]),
    # One zip per municipality, with parcela_urbana.shp among other layers.
    "alava": ("catastro_alava", ["*_CatastroAlava.zip"]),
    # One zip per municipality, with {code}_Parcela.shp and {code}_Subparcela.shp among others.
    "bizkaia": ("Catastro_Bizkaia", ["*_SHP_*.zip"]),
    # One zip for the whole territory, with HIRILUR_URBANO.shp (urban parcels).
    "gipuzkoa": ("guipuzcua_catastro", ["KATASTROA_CATASTRO.zip"]),
}


def run(archive: Path, snapshot: str) -> None:
    target_root = raw_dir(PIPELINE, snapshot)
    summary = {}
    for territory, (folder, patterns) in SOURCES.items():
        files = sorted(path for pattern in patterns for path in (archive / folder).glob(pattern))
        if not files:
            raise SystemExit(f"No files for {territory} in {archive / folder}")
        target = target_root / territory
        target.mkdir(exist_ok=True)
        for path in files:
            shutil.copy2(path, target / path.name)
        summary[territory] = {"source_folder": str(archive / folder), "files": len(files), "bytes": sum(path.stat().st_size for path in files)}
        log.info("%s: copied %d files (%.0f MB)", territory, len(files), summary[territory]["bytes"] / 1e6)
    metadata = {"imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "territories": summary}
    (target_root / "import.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy the foral cadastres' parcel files into data/raw/.")
    parser.add_argument("archive", type=Path, help="folder with catastro_navarra/, catastro_alava/, Catastro_Bizkaia/, guipuzcua_catastro/")
    parser.add_argument("--snapshot", default="2023-05", help="name of the raw folder: the files' date (default 2023-05)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.archive, args.snapshot)
