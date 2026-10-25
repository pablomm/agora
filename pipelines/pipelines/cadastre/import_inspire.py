"""
Copies one theme out of a local archive of Catastro's INSPIRE downloads into data/raw/, leaving
the archive untouched.

The archive has one zip per municipality and dataset, as served by Catastro's INSPIRE ATOM feeds:
A.ES.SDGC.CP.{code}.zip (cadastral parcels: parcels and zoning) and A.ES.SDGC.BU.{code}.zip
(buildings: buildings, their parts and other constructions). Each theme's files are copied into a
single zip; the other pipelines in this folder read from there.

    python pipelines/cadastre/import_inspire.py THEME ARCHIVE_FOLDER [--snapshot 2023-04]

THEME is zoning, parcels or buildings; ARCHIVE_FOLDER is the folder with data_parcels/ and data_buildings/.
"""

import argparse
import json
import logging
import shutil
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from common.paths import raw_dir

log = logging.getLogger(__name__)

PIPELINE = "cadastre"


@dataclass
class Theme:
    #: Folder of the archive with the theme's zips, and their name pattern.
    folder: str
    pattern: str
    #: Files to copy from each zip (by suffix), one of each.
    suffixes: tuple[str, ...]
    #: Zip written to data/raw/cadastre/{snapshot}/.
    target: str


THEMES = {
    "zoning": Theme("data_parcels", "A.ES.SDGC.CP.*.zip", (".cadastralzoning.gml",), "cadastralzoning.zip"),
    "parcels": Theme("data_parcels", "A.ES.SDGC.CP.*.zip", (".cadastralparcel.gml",), "cadastralparcel.zip"),
    "buildings": Theme("data_buildings", "A.ES.SDGC.BU.*.zip", (".building.gml", ".buildingpart.gml"), "buildings.zip"),
}


def run(theme_name: str, archive_folder: Path, snapshot: str) -> Path:
    theme = THEMES[theme_name]
    archives = sorted((archive_folder / theme.folder).glob(theme.pattern))
    if not archives:
        raise SystemExit(f"No {theme.pattern} files in {archive_folder / theme.folder}")
    target = raw_dir(PIPELINE, snapshot) / theme.target
    partial = target.with_suffix(".zip.part")
    copied, months = 0, Counter()
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as out:
            for index, archive in enumerate(archives, 1):
                with zipfile.ZipFile(archive) as municipality:
                    for suffix in theme.suffixes:
                        members = [info for info in municipality.infolist() if info.filename.endswith(suffix)]
                        if len(members) != 1:
                            raise ValueError(f"{archive.name}: expected one {suffix}, found {len(members)}")
                        member = members[0]
                        months["%04d-%02d" % member.date_time[:2]] += 1
                        entry = zipfile.ZipInfo(member.filename, date_time=member.date_time)
                        entry.compress_type = zipfile.ZIP_DEFLATED
                        # Some files are over 2 GB uncompressed (the big cities' building parts).
                        with municipality.open(member) as reader, out.open(entry, "w", force_zip64=True) as writer:
                            shutil.copyfileobj(reader, writer, 1 << 20)
                copied += 1
                if index % 500 == 0:
                    log.info("%d/%d municipalities", index, len(archives))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(target)

    metadata = {
        "theme": theme_name,
        "source_folder": str(archive_folder / theme.folder),
        "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "municipalities": copied,
        # When Catastro generated the files: the snapshot's real date.
        "file_months": dict(sorted(months.items())),
        "bytes": target.stat().st_size,
    }
    (target.parent / f"{target.stem}.import.json").write_text(json.dumps(metadata, indent=2) + "\n")
    log.info("Wrote %s (%d municipalities, %.0f MB)", target, copied, target.stat().st_size / 1e6)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Copy one theme out of a local archive of Catastro's INSPIRE downloads.")
    parser.add_argument("theme", choices=sorted(THEMES))
    parser.add_argument("archive", type=Path, help="folder with data_parcels/ and data_buildings/")
    parser.add_argument("--snapshot", default="2023-04", help="name of the raw folder: the files' date (default 2023-04)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(args.theme, args.archive, args.snapshot)
