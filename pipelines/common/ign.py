"""
IGN's WFS INSPIRE administrative units (autonomous communities, provinces, municipalities):
the request for one level of the hierarchy, its download, and its features as plain units.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

from .download import download

log = logging.getLogger(__name__)

SOURCE_URL = "https://www.ign.es/wfs-inspire/unidades-administrativas"
METADATA_URL = (
    "https://www.idee.es/csw-inspire-idee/srv/spa/csw?SERVICE=CSW&VERSION=2.0.2&REQUEST=GetRecordById"
    "&outputSchema=http://www.isotc211.org/2005/gmd&ElementSetName=full&ID=spaignLLM"
)
LICENSE = {"id": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/", "attribution": "CC BY 4.0 ign.es"}

# INSPIRE's hierarchy levels as IGN uses them.
AUTONOMOUS_COMMUNITY = "2ndOrder"
PROVINCE = "3rdOrder"
MUNICIPALITY = "4thOrder"


def request_params(level: str) -> dict[str, str]:
    """GetFeature for one level, as GeoJSON in EPSG:4326."""
    # The WFS can't filter on the level's text; it filters on the link to INSPIRE's code list.
    level_filter = (
        '<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0" '
        'xmlns:au="http://inspire.ec.europa.eu/schemas/au/4.0" xmlns:xlink="http://www.w3.org/1999/xlink">'
        "<fes:PropertyIsEqualTo><fes:ValueReference>au:nationalLevel/@xlink:href</fes:ValueReference>"
        f"<fes:Literal>https://inspire.ec.europa.eu/codelist/AdministrativeHierarchyLevel/{level}</fes:Literal>"
        "</fes:PropertyIsEqualTo></fes:Filter>"
    )
    return {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": "au:AdministrativeUnit",
        "outputFormat": "application/geo+json",
        "srsName": "EPSG:4326",
        "FILTER": level_filter,
    }


def fetch(level: str, target: Path, refresh: bool = False) -> None:
    """Downloads the level unless `target` already exists (one download per day: see paths.raw_dir)."""
    if target.exists() and not refresh:
        log.info("Using today's download %s", target)
        return
    # Boundaries come at full resolution: over 100 MB for provinces.
    download(SOURCE_URL, target, params=request_params(level))


@dataclass
class AdminUnit:
    #: IGN's national code: "34" (Spain), then the INE codes of each level down to this one, then zeros.
    national_code: str
    #: Official name; bilingual where that's the official form (e.g. "Alacant/Alicante").
    name: str
    #: Valid polygonal geometry in EPSG:4326.
    geometry: BaseGeometry


def read_units(raw: Path) -> list[AdminUnit]:
    """The downloaded features, with invalid geometry repaired; fails on non-polygonal geometry."""
    units = []
    for feature in json.loads(raw.read_text())["features"]:
        properties = feature["properties"]
        geometry = shape(feature["geometry"])
        if not geometry.is_valid:
            geometry = shapely.make_valid(geometry)
        if geometry.geom_type not in ("Polygon", "MultiPolygon"):
            raise ValueError(f"{properties['nationalCode']} has non-polygonal geometry ({geometry.geom_type})")
        name = properties["name"]["GeographicalName"]["spelling"]["SpellingOfName"]["text"]
        units.append(AdminUnit(properties["nationalCode"], name, geometry))
    return units
