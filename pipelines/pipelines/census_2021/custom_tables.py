"""
Census 2021 tables by census section from INE's custom tables tool ("Crear tablas",
https://www.ine.es/Censo2021/Inicio.do): the only source for dwellings by year of construction or
building type, household structure, family nuclei… by section. Downloads only; census_2021.py reads
them.

The tool builds one table per request (rows: municipality → district → section; columns: one
variable; one measure) and exports it as PC-Axis. A whole province is too big for the largest ones
(Madrid, Barcelona…), so each request covers a group of municipalities of up to `CHUNK` sections.
Each table takes a fresh session (the tool keeps the geography and collective in it) and is checked
to be about the municipalities asked for.

INE hides small municipalities in the tool (their sections don't come back) and perturbs its cells
slightly (statistical disclosure control): census_2021.py fits them to the published totals.

    python pipelines/census_2021/custom_tables.py [table ...] [--provinces 28 08]
"""

import argparse
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from common.paths import output_dir, raw_dir

log = logging.getLogger(__name__)

PIPELINE = "census_2021"
BASE = "https://www.ine.es/Censo2021/"
ROWS = ["L_[RESIDENCIA].[DESC_RESIDENCIA_N3]", "L_[RESIDENCIA].[DESC_RESIDENCIA_N4]", "L_[RESIDENCIA].[DESC_RESIDENCIA_N5]"]
#: Sections per request: Madrid's municipality (2,443) works, its province (4,400) is too big.
CHUNK = 2500
#: Seconds between requests, to go easy on INE's server.
PAUSE = 2
COLLECTIVES = {"dwellings": 5, "households": 6, "nuclei": 7}
COUNTS = {"dwellings": "[Measures].[SVIVIENDASSUM]", "households": "[Measures].[SHOGARESSUM]", "nuclei": "[Measures].[SNUCLEOSSUM]"}
#: The tables: collective, the tool's variable (columns) and measure.
TABLES = {
    "dwellings_year": ("dwellings", "L_[ANO_CONS_GR11].[DESC_ANO_CONS_GR11]", COUNTS["dwellings"]),
    "dwellings_building": ("dwellings", "L_[TIPO_EDIF_VIV].[DESC_TIPO_EDIF_VIV]", COUNTS["dwellings"]),
    "dwellings_floor_area": ("dwellings", "L_[SUP_VIV].[DESC_SUP_VIV]", COUNTS["dwellings"]),
    "dwellings_floors": ("dwellings", "L_[NPLANTAS_SOBRE_EDIF].[DESC_NPLANTAS_SOBRE_EDIF]", COUNTS["dwellings"]),
    "dwellings_mean_age": ("dwellings", "L_[TIPO_VIV_USO].[DESC_TIPO_VIV_USO]", "[Measures].[MEDIA_SANTIGUEDADSUM]"),
    "households_structure": ("households", "L_[ESTRUC_HOG_2].[DESC_ESTRUC_HOG_2]", COUNTS["households"]),
    "households_type": ("households", "L_[TIPO_HOG_1].[DESC_TIPO_HOG_1]", COUNTS["households"]),
    "households_nuclei": ("households", "L_[NUC_HOG].[DESC_NUC_HOG]", COUNTS["households"]),
    "households_families": ("households", "L_[FAM_HOG].[DESC_FAM_HOG]", COUNTS["households"]),
    "households_aged_0_4": ("households", "L_[TAMEDAD04].[DESC_TAMEDAD04]", COUNTS["households"]),
    "households_aged_5_15": ("households", "L_[TAMEDAD515].[DESC_TAMEDAD515]", COUNTS["households"]),
    "households_aged_65_84": ("households", "L_[TAMEDAD6584].[DESC_TAMEDAD6584]", COUNTS["households"]),
    "households_aged_85_plus": ("households", "L_[TAMEDAD85m].[DESC_TAMEDAD85m]", COUNTS["households"]),
    "households_working": ("households", "L_[ACTI_HOG_1].[DESC_ACTI_HOG_1]", COUNTS["households"]),
    "households_unemployed": ("households", "L_[ACTI_HOG_2].[DESC_ACTI_HOG_2]", COUNTS["households"]),
    "nuclei_type": ("nuclei", "L_[TIPO_NUC_1].[DESC_TIPO_NUC_1]", COUNTS["nuclei"]),
    "nuclei_couple_kind": ("nuclei", "L_[TIPO_PAR_NUC_1].[DESC_TIPO_PAR_NUC_1]", COUNTS["nuclei"]),
    "nuclei_couple_sexes": ("nuclei", "L_[TIPO_PAR_NUC_2].[DESC_TIPO_PAR_NUC_2]", COUNTS["nuclei"]),
    "nuclei_children": ("nuclei", "L_[NHIJOS_NUC].[DESC_NHIJOS_NUC]", COUNTS["nuclei"]),
    "nuclei_mean_children": ("nuclei", "L_[TIPO_NUC_1].[DESC_TIPO_NUC_1]", "[Measures].[MEDIA_SHIJOS_NUCLEOSUM]"),
}


#: The tool's name of each variable, as PC-Axis tables head their columns.
VARIABLES = {
    "L_[ANO_CONS_GR11].[DESC_ANO_CONS_GR11]": "Año de construcción (agregado)",
    "L_[TIPO_EDIF_VIV].[DESC_TIPO_EDIF_VIV]": "Tipo de viviendas según tipo de edificio",
    "L_[SUP_VIV].[DESC_SUP_VIV]": "Superficie",
    "L_[NPLANTAS_SOBRE_EDIF].[DESC_NPLANTAS_SOBRE_EDIF]": "Número plantas sobre rasante",
    "L_[TIPO_VIV_USO].[DESC_TIPO_VIV_USO]": "Tipo de vivienda según uso",
    "L_[ESTRUC_HOG_2].[DESC_ESTRUC_HOG_2]": "Estructura del hogar",
    "L_[TIPO_HOG_1].[DESC_TIPO_HOG_1]": "Tipo de Hogar (detalle)",
    "L_[NUC_HOG].[DESC_NUC_HOG]": "Número núcleos en el hogar",
    "L_[FAM_HOG].[DESC_FAM_HOG]": "Número familias en el hogar",
    "L_[TAMEDAD04].[DESC_TAMEDAD04]": "Número de miembros de 0 a 4 años",
    "L_[TAMEDAD515].[DESC_TAMEDAD515]": "Número de miembros de 5 a 15 años",
    "L_[TAMEDAD6584].[DESC_TAMEDAD6584]": "Número de miembros de 65 a 84 años",
    "L_[TAMEDAD85m].[DESC_TAMEDAD85m]": "Número de miembros de 85 años o más",
    "L_[ACTI_HOG_1].[DESC_ACTI_HOG_1]": "Número de miembros de 16 a 64 años que están trabajando",
    "L_[ACTI_HOG_2].[DESC_ACTI_HOG_2]": "Número de miembros de 16 a 64 años que están parados",
    "L_[TIPO_NUC_1].[DESC_TIPO_NUC_1]": "Tipo de núcleo",
    "L_[TIPO_PAR_NUC_1].[DESC_TIPO_PAR_NUC_1]": "Tipo de pareja (de hecho o de derecho)",
    "L_[TIPO_PAR_NUC_2].[DESC_TIPO_PAR_NUC_2]": "Tipo de pareja (mismo sexo, distinto sexo)",
    "L_[NHIJOS_NUC].[DESC_NHIJOS_NUC]": "Número de hijos",
}


def session() -> requests.Session:
    out = requests.Session()
    out.headers["User-Agent"] = "Agora data pipeline (census 2021 tables)"
    out.get(BASE + "Inicio.do", timeout=60).raise_for_status()
    return out


def read_px(path_or_text) -> pd.DataFrame:
    """A table as rows (municipality, district, section: None where it's a total) × categories."""
    text = path_or_text if isinstance(path_or_text, str) else path_or_text.read_text(encoding="iso-8859-1")
    values = lambda name: re.findall(r'"([^"]*)"', re.search(r'VALUES\("' + re.escape(name) + r'"\)=(.*?);', text, re.S).group(1))
    stub = re.search(r'STUB="([^"]*)"', text).group(1)
    variable = re.findall(r'"([^"]*)"', re.search(r"HEADING=(.*?);", text, re.S).group(1))[0]
    rows, columns = values(stub), values(variable)
    data = np.array(text[text.index("DATA=") + 5 :].replace(";", " ").split(), dtype=float)
    if len(data) != len(rows) * len(columns):
        raise ValueError(f"{len(data)} values for {len(rows)} rows × {len(columns)} columns")
    frame = pd.DataFrame(data.reshape(len(rows), len(columns)), columns=[column.strip() for column in columns])
    parts = pd.Series(rows).str.split("-->", expand=True)
    frame["municipality"] = parts[0].str.extract(r"^(\d{5}) ", expand=False)
    frame["district"] = parts[1].str.extract(r"(\d{7})", expand=False)
    frame["section"] = parts[2].str.extract(r"(\d{10})", expand=False)
    # Sections come twice (under "TOTAL" districts too): the ones under their district.
    duplicated = frame["section"].notna() & frame["district"].isna()
    return frame[~duplicated].reset_index(drop=True)


def official() -> dict[str, pd.Series]:
    """Each section's dwellings and households (census_2021.py), to tell a mixed-up table."""
    out = {}
    for name, dataset, dimension in (("dwellings", "dwellings_2021", "dwelling"), ("households", "households_2021", "household_size")):
        frame = pd.read_parquet(output_dir(PIPELINE) / dataset / "census_section.parquet")
        out[name] = frame[frame[dimension] == "total"].set_index("code")["value"]
    return out


def plausible(text: str, chunk: dict, name: str, totals: dict) -> None:
    """
    Counts add up to about each section's official total (dwellings, households), or keep near
    their households (nuclei); means are in range. A table whose values belong to another fails.
    """
    collective, _, measure = TABLES[name]
    frame = read_px(text)
    sections = frame[frame["section"].notna()].set_index("section")
    if "MEDIA" in measure:
        values = sections.drop(columns=["municipality", "district"]).to_numpy()
        top = 150 if collective == "dwellings" else 8
        if np.nanmax(values, initial=0) > top or (values < 0).any():
            raise ValueError(f"{chunk['id']}: means out of range")
        return
    if sections.empty:
        return
    if collective == "nuclei":
        # A household holds at most a nucleus or so: the ratio stays near 0.75 wherever the values are a section's
        ratio = sections["TOTAL"] / totals["households"].reindex(sections.index)
        if (~ratio.between(0.4, 1.2)).mean() > 0.1:
            raise ValueError(f"{chunk['id']}: nuclei that don't follow the sections' households")
        return
    reference = totals[collective].reindex(sections.index)
    off = ((sections["TOTAL"] - reference).abs() > 5 + 0.05 * reference).mean()
    if off > 0.05:
        raise ValueError(f"{chunk['id']}: {off:.0%} of sections off their official total")


def municipalities() -> pd.DataFrame:
    """The tool's municipalities (its identifiers), with their province and number of 2021 sections."""
    page = session().get(BASE + "Wizard.do?WIZARD=5&reqCode=pasoSeleccionGeografia", timeout=120).text
    found = re.findall(r'<option value="(\[RESIDENCIA\]\.\[Todo RESIDENCIA\]\.\[[^"]+\]\.(\[(\d{2}) [^"]+\])\.\[(\d{5}) [^"]+\])"', page)
    frame = pd.DataFrame(found, columns=["value", "province_value", "province", "code"])
    sections = pd.read_csv(raw_dir(PIPELINE, "2026-10-26") / "C2021_Indicadores.csv", dtype=str, usecols=["cpro", "cmun"])
    counts = (sections["cpro"] + sections["cmun"]).value_counts()
    return frame.assign(sections=frame["code"].map(counts).fillna(1).astype(int))


def chunks(towns: pd.DataFrame) -> list[dict]:
    """Groups of a province's municipalities of up to CHUNK sections (a bigger one alone)."""
    out = []
    for province, group in towns.groupby("province"):
        parts, current, size = [], [], 0
        for town in group.sort_values("sections", ascending=False).itertuples():
            if current and size + town.sections > CHUNK:
                parts.append(current)
                current, size = [], 0
            current.append(town)
            size += town.sections
        parts.append(current)
        out += [{"id": f"{province}_{n}", "province": province, "values": [town.value for town in part], "codes": [town.code for town in part]} for n, part in enumerate(parts)]
    return out


def request(chunk: dict, collective: int, variable: str, measure: str) -> bytes:
    """One table as PC-Axis, for one group of municipalities, in a fresh session."""
    client = session()
    geography = [value + ".Children.Children" for value in chunk["values"]]
    province_value = chunk["values"][0].rsplit(".[", 1)[0]
    client.post(BASE + "Wizard.do", data={"reqCode": "pasoSeleccionGeografia", "WIZARD": "6", "areaOrigen": "distritos", "idProvincia": province_value, "municipios": geography, "idMunicipio": geography}, timeout=300).raise_for_status()
    client.get(BASE + f"Wizard.do?WIZARD={collective}&reqCode=pasoSeleccionColectivo", timeout=300).raise_for_status()
    report = client.post(BASE + "Informe.do", data={"reqCode": "iniciar", "WIZARD": "2", "pagina4": "6", "tipoInforme": "LIBRE", "idFila": ROWS, "idColumna": [variable], "medidas": [measure]}, timeout=900)
    report.raise_for_status()
    if "Debido al tama" in report.text:
        raise ValueError(f"{chunk['id']}: too big for the tool")
    export = client.post(BASE + "Informe.do?reqCode=pcAxis", data={"reqCode": "pasoDisenhoTabla_Elementos", "WIZARD": "1", "numDec": "-1", "tipoInforme": "LIBRE"}, timeout=900)
    export.raise_for_status()
    return export.content


def check(content: bytes, chunk: dict, variable: str) -> int:
    """
    The table is the one asked for: about the chunk's municipalities (some may be hidden), with the
    variable asked for, and as many values as rows × columns. INE's server mixes up concurrent
    requests (one table's rows with another's values): requests go one at a time, and this checks.
    Returns the table's sections.
    """
    text = content.decode("iso-8859-1")
    if "DATA=" not in text:
        raise ValueError(f"{chunk['id']}: not a PC-Axis table")
    stub = re.search(r'VALUES\("Municipio de residencia-->Distrito -->Secci[^"]*"\)=(.*?);', text, re.S)
    labels = re.findall(r'"([^"]*)"', stub.group(1)) if stub else []
    heading = re.findall(r'"([^"]*)"', re.search(r"HEADING=(.*?);", text, re.S).group(1))[0]
    columns = re.findall(r'"([^"]*)"', re.search(r'VALUES\("' + re.escape(heading) + r'"\)=(.*?);', text, re.S).group(1))
    values = len(text[text.index("DATA=") + 5 :].replace(";", " ").split())
    if values != len(labels) * len(columns):
        raise ValueError(f"{chunk['id']}: {values} values for {len(labels)} rows × {len(columns)} columns")
    expected = VARIABLES.get(variable)
    if expected and heading.strip().lower() != expected.lower():
        raise ValueError(f"{chunk['id']}: a table of {heading!r}, not {expected!r}")
    towns = {label[:5] for label in labels if label[:5].isdigit()}
    if not towns <= set(chunk["codes"]):
        raise ValueError(f"{chunk['id']}: municipalities that weren't asked for: {sorted(towns - set(chunk['codes']))[:5]}")
    return sum("Sección" in label and "-->TOTAL-->" in label for label in labels)


def download(names: list[str], provinces: list[str] | None, day: str) -> None:
    folder = raw_dir(PIPELINE, day) / "custom"
    folder.mkdir(exist_ok=True)
    towns = municipalities()
    groups = [chunk for chunk in chunks(towns) if not provinces or chunk["province"] in provinces]
    totals = official()
    (folder / "chunks.json").write_text(json.dumps(groups, ensure_ascii=False, indent=1))
    log.info("%d tables × %d requests", len(names), len(groups))
    for name in names:
        collective, variable, measure = TABLES[name]
        (folder / name).mkdir(exist_ok=True)
        for chunk in groups:
            target = folder / name / f"{chunk['id']}.px"
            if target.exists():
                continue
            for attempt in range(4):
                try:
                    started = time.time()
                    content = request(chunk, COLLECTIVES[collective], variable, measure)
                    sections = check(content, chunk, variable)
                    plausible(content.decode("iso-8859-1"), chunk, name, totals)
                    target.write_bytes(content)
                    log.info("%s %s: %d sections in %.0f s", name, chunk["id"], sections, time.time() - started)
                    break
                except (requests.RequestException, ValueError) as error:
                    log.warning("%s %s, attempt %d: %s", name, chunk["id"], attempt + 1, error)
                    time.sleep(30 * (attempt + 1))
            else:
                log.error("%s %s: gave up", name, chunk["id"])
            time.sleep(PAUSE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Census 2021 tables by section from INE's custom tables tool.")
    parser.add_argument("tables", nargs="*", help=f"tables to download (default: all): {', '.join(TABLES)}")
    parser.add_argument("--provinces", nargs="*", help="only these provinces (INE codes)")
    parser.add_argument("--date", default=date.today().isoformat(), help="raw folder to fill (resumes a download begun another day)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    download(args.tables or list(TABLES), args.provinces, args.date)
